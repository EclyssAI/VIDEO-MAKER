"""Integração Cakto (não havia integração no código do João; implementada do zero, desligada por padrão).
Autenticação do webhook (docs.cakto.com.br/conceitos/webhooks):
  - preferida: header X-Cakto-Signature "v1=<hmac_sha256(secret, f'{X-Cakto-Timestamp}.{corpo bruto}')>" (tolerância 5 min)
  - alternativa: campo "secret" no corpo, comparado em tempo constante.
Idempotência por data.id+event. Plano decidido pelo offer.id (CAKTO_OFFER_CREATOR / CAKTO_OFFER_STUDIO).
Sem data de próxima cobrança documentada no payload: cada aprovação/renovação libera PERIOD_DAYS."""
import hashlib, hmac, json, os, time
from . import db

PERIOD_DAYS = int(os.environ.get("CAKTO_PERIOD_DAYS", "32"))
GRANT = {"purchase_approved", "subscription_created", "subscription_renewed", "subscription_late_recovered", "subscription_resumed"}
LATE = {"subscription_renewal_refused", "subscription_late"}
CANCEL = {"subscription_canceled"}          # mantém acesso até o fim do período pago
REVOKE = {"refund", "chargeback"}            # corta o acesso na hora
RANK = {"creator": 1, "studio": 2}


def enabled(): return os.environ.get("CAKTO_ENABLED", "0") == "1" and bool(os.environ.get("CAKTO_WEBHOOK_SECRET"))


def checkout_urls():
    if not enabled(): return {}
    return {k: v for k, v in {"creator": os.environ.get("CAKTO_CHECKOUT_CREATOR"),
                              "studio": os.environ.get("CAKTO_CHECKOUT_STUDIO")}.items() if v}


def verify(raw: bytes, headers, body: dict) -> bool:
    secret = os.environ.get("CAKTO_WEBHOOK_SECRET", "")
    if not secret: return False
    sig, ts = headers.get("x-cakto-signature", ""), headers.get("x-cakto-timestamp", "")
    if sig and ts:
        try:
            if abs(time.time() - float(ts)) > 300: return False
        except ValueError:
            return False
        mac = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.removeprefix("v1="), mac)
    got = body.get("secret")
    return isinstance(got, str) and hmac.compare_digest(got, secret)


def plan_for_offer(offer_id):
    return {os.environ.get("CAKTO_OFFER_CREATOR"): "creator", os.environ.get("CAKTO_OFFER_STUDIO"): "studio"}.get(offer_id)


def _set(c, email, plan, status, until):
    t = db.now()
    c.execute("INSERT INTO entitlements(email,plan,status,until,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
              "plan=excluded.plan,status=excluded.status,until=excluded.until,updated_at=excluded.updated_at", (email, plan, status, until, t))
    # só contas com e-mail verificado recebem o plano: sem isso, quem cadastrasse o e-mail do comprador antes levaria a assinatura
    c.execute("UPDATE users SET plan=?, plan_status=?, plan_until=? WHERE email=? AND email_verified=1", (plan, status, until, email))


def minimal(body: dict):
    """Minimização (LGPD art. 6º, III): do payload da Cakto guardamos só o necessário para auditar a liberação de acesso.
    CPF, telefone, endereço, nome e dados de cartão NÃO são armazenados aqui (ficam com a Cakto)."""
    d = body.get("data") or {}
    keep = {k: d.get(k) for k in ("id", "refId", "status", "amount", "baseAmount", "paymentMethod", "createdAt", "paidAt", "canceledAt",
                                  "refundedAt", "chargedbackAt", "installments") if k in d}
    return {"event": body.get("event"), "data": {**keep, "offer": {"id": (d.get("offer") or {}).get("id")},
                                                  "product": {"id": (d.get("product") or {}).get("id")}}}


def handle(c, body: dict):
    """Aplica o evento. Retorna dict com o resultado (para log/teste)."""
    ev, data = body.get("event"), body.get("data") or {}
    email = ((data.get("customer") or {}).get("email") or "").strip().lower()
    offer = (data.get("offer") or {}).get("id")
    eid = f"{data.get('id') or data.get('refId') or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}:{ev}"
    if c.execute("SELECT 1 FROM billing_events WHERE id=?", (eid,)).fetchone():
        return {"duplicate": True}
    plan = plan_for_offer(offer)
    cur = c.execute("SELECT * FROM entitlements WHERE email=?", (email,)).fetchone()
    applied, t = 0, db.now()
    if email and ev in GRANT and plan:
        until = max(t, cur["until"] if cur and cur["plan"] == plan else t) + PERIOD_DAYS * 86400
        if cur and cur["status"] == "active" and cur["until"] > t and RANK.get(cur["plan"], 0) > RANK[plan]:
            plan, until = cur["plan"], cur["until"]  # renovação do plano menor não rebaixa um plano maior ainda vigente
        _set(c, email, plan, "active", until); applied = 1
    elif email and ev in LATE and cur and (not plan or cur["plan"] == plan):
        _set(c, email, cur["plan"], "past_due", cur["until"]); applied = 1
    elif email and ev in CANCEL and cur and (not plan or cur["plan"] == plan):
        _set(c, email, cur["plan"], "canceled", cur["until"]); applied = 1
    elif email and ev in REVOKE and cur and (not plan or cur["plan"] == plan):
        _set(c, email, cur["plan"], "revoked", t); applied = 1
    c.execute("INSERT INTO billing_events(id,event,email,offer_id,plan,applied,raw,received_at) VALUES(?,?,?,?,?,?,?,?)",
              (eid, ev or "", email, offer, plan, applied, json.dumps(minimal(body)), t))
    return {"applied": bool(applied), "plan": plan, "event": ev}


def apply_pending(c, email):
    """Ao criar conta, aplica uma assinatura comprada antes do cadastro."""
    e = c.execute("SELECT * FROM entitlements WHERE email=?", (email,)).fetchone()
    if e: c.execute("UPDATE users SET plan=?, plan_status=?, plan_until=? WHERE email=? AND email_verified=1",
                    (e["plan"], e["status"], e["until"], email))
