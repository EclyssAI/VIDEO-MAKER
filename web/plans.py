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
    r = c.execute("SELECT projects, minutes, live_s, live_clips, ai_usd FROM usage WHERE user_id=? AND month=?", (uid, db.month())).fetchone()
    return {"projects": r["projects"] if r else 0, "minutes": round(r["minutes"], 1) if r else 0.0,
            "live_hours": round(r["live_s"] / 3600, 2) if r else 0.0, "live_clips": r["live_clips"] if r else 0,
            "ai_usd": round(r["ai_usd"], 4) if r else 0.0}


def charge_ai(c, uid, usd):
    """Gasto real com a API do Claude no mês (somado quando a API responde)."""
    c.execute("INSERT INTO usage(user_id, month, ai_usd) VALUES(?,?,?) ON CONFLICT(user_id, month) DO UPDATE SET ai_usd=ai_usd+excluded.ai_usd",
              (uid, db.month(), usd))


def ai_left(c, user):
    """Teto mensal da IA NO SERVIDOR (caminho opcional, desligado por padrão: a análise é feita pelo Claude do cliente via MCP).
    Sem valor no plano, vale LIVE_AI_USD_PER_MONTH do operador; sem ela, só o orçamento por sessão limita."""
    L = limits(effective_plan(user))
    if not L: return 0.0
    cap = L.get("live_ai_usd_per_month", float(os.environ.get("LIVE_AI_USD_PER_MONTH", "inf")))
    return max(0.0, cap - usage(c, user["id"])["ai_usd"])


def charge_live(c, uid, seconds):
    """Franquia do Live Monitor: soma o tempo gravado à medida que cada bloco é processado (não só ao encerrar)."""
    c.execute("INSERT INTO usage(user_id, month, live_s) VALUES(?,?,?) ON CONFLICT(user_id, month) DO UPDATE SET live_s=live_s+excluded.live_s",
              (uid, db.month(), seconds))


def count_live_clip(c, uid):
    c.execute("INSERT INTO usage(user_id, month, live_clips) VALUES(?,?,1) ON CONFLICT(user_id, month) DO UPDATE SET live_clips=live_clips+1",
              (uid, db.month()))


def live_quota_left(c, user):
    """(horas, cortes) restantes no mês para o Live Monitor, ou None sem plano."""
    L = limits(effective_plan(user))
    if not L: return None
    u = usage(c, user["id"])
    return max(0.0, L["live_hours_per_month"] - u["live_hours"]), max(0, L["live_clips_per_month"] - u["live_clips"])


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
