"""Planos e limites (config/plans.yaml) + checagem de acesso ativo."""
import os, yaml
from . import db

PLANS = yaml.safe_load((db.ROOT / "config/plans.yaml").read_text())["plans"]
GRACE_S = 3 * 86400  # tolerância após vencimento/atraso antes de bloquear


def effective_plan(user):
    """Plano efetivo do usuário agora: assinatura ativa (Cakto) > beta (se habilitado) > nenhum."""
    if user["plan"] in ("creator", "studio") and user["plan_status"] in ("active", "past_due", "canceled") \
            and user["plan_until"] + (GRACE_S if user["plan_status"] == "past_due" else 0) > db.now():
        return user["plan"]
    if os.environ.get("BETA_SIGNUP", "0") == "1": return "beta"
    return None


def limits(plan): return PLANS.get(plan) if plan else None


def usage(c, uid):
    r = c.execute("SELECT projects, minutes FROM usage WHERE user_id=? AND month=?", (uid, db.month())).fetchone()
    return {"projects": r["projects"] if r else 0, "minutes": round(r["minutes"], 1) if r else 0.0}


def check_new_project(c, user, size_bytes=None, duration_s=None):
    """Retorna (ok, mensagem). Chamado antes de aceitar upload e de novo após medir a duração."""
    plan = effective_plan(user); L = limits(plan)
    if not L: return False, "Sua conta não tem um plano ativo. Assine o Creator ou o Creator Studio para processar vídeos."
    u = usage(c, user["id"])
    if u["projects"] >= L["projects_per_month"]:
        return False, f"Limite do plano {L['label']} atingido: {L['projects_per_month']} projetos por mês."
    if size_bytes is not None and size_bytes > L["max_upload_mb"] * 1024 * 1024:
        return False, f"Arquivo maior que o limite do plano {L['label']} ({L['max_upload_mb']} MB)."
    if duration_s is not None:
        if duration_s > L["max_video_minutes"] * 60:
            return False, f"Vídeo com mais de {L['max_video_minutes']} minutos (limite do plano {L['label']})."
        if u["minutes"] + duration_s / 60 > L["minutes_per_month"]:
            return False, f"Este vídeo ultrapassa seus {L['minutes_per_month']} minutos mensais do plano {L['label']}."
    return True, ""


def charge(c, uid, duration_s):
    c.execute("INSERT INTO usage(user_id, month, projects, minutes) VALUES(?,?,1,?) "
              "ON CONFLICT(user_id, month) DO UPDATE SET projects=projects+1, minutes=minutes+excluded.minutes",
              (uid, db.month(), duration_s / 60))
