"""Aceite versionado dos documentos jurídicos (Termos de Uso + Política de Privacidade).

Guardamos o mínimo para provar o aceite: conta, versão de cada documento, data/hora (UTC) e o contexto (cadastro ou
reaceite). Não guardamos IP nem user-agent aqui (minimização, LGPD art. 6º, III). Base legal: execução de contrato
(LGPD art. 7º, V) e exercício regular de direitos (art. 7º, VI). Quando a versão vigente muda, ações que dependem do
contrato (processar vídeo, monitorar live, criar token de API) ficam bloqueadas até o novo aceite (HTTP 428).
As versões são as datas de vigência publicadas no topo de cada documento em web/static/legal/."""
from . import db

TERMS_VERSION = "2026-11-19"
PRIVACY_VERSION = "2026-11-19"
DOCS = {"termos": "Termos de Uso", "privacidade": "Política de Privacidade", "cancelamento": "Cancelamento, Arrependimento e Reembolso",
        "conteudo": "Conteúdo e Direitos de Terceiros", "cookies": "Política de Cookies", "regras-live-ia": "Regras do Live Monitor, IA e Integrações",
        "contato": "Contato, Suporte e Exclusão de Dados"}


class TermsRequired(Exception):
    pass


def last(c, uid):
    return c.execute("SELECT terms_version, privacy_version, accepted_at, context FROM terms_acceptances WHERE user_id=? "
                     "ORDER BY accepted_at DESC, id DESC LIMIT 1", (uid,)).fetchone()


def status(c, uid):
    r = last(c, uid)
    ok = bool(r) and r["terms_version"] == TERMS_VERSION and r["privacy_version"] == PRIVACY_VERSION
    return {"required": not ok, "terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION,
            "accepted": dict(r) if r else None}


def accept(c, uid, context):
    if context not in ("signup", "reaccept"): raise ValueError("contexto inválido")
    c.execute("INSERT INTO terms_acceptances(user_id, terms_version, privacy_version, accepted_at, context) VALUES(?,?,?,?,?)",
              (uid, TERMS_VERSION, PRIVACY_VERSION, db.now(), context))
    return status(c, uid)


def require(c, uid):
    if status(c, uid)["required"]: raise TermsRequired()


def history(c, uid):
    return [dict(r) for r in c.execute("SELECT terms_version, privacy_version, accepted_at, context FROM terms_acceptances "
                                       "WHERE user_id=? ORDER BY accepted_at", (uid,))]
