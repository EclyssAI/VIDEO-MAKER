"""Fila de postagem: aprovar -> agenda no próximo horário livre -> posta em todas as plataformas ativas.
  python publish/scheduler.py approve <lote> 1 3 5
  python publish/scheduler.py post            # posta o que já venceu (o ciclo chama sozinho)
  python publish/scheduler.py post --now      # posta tudo aprovado agora
  python publish/scheduler.py status"""
import sys, json, datetime as dt, pathlib, importlib, yaml
R = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(R))
C = yaml.safe_load((R/"config/publish.yaml").read_text()); SEC = R/"config/secrets"; Q = R/"logs/queue.json"
BR = dt.timezone(dt.timedelta(hours=-3))
def load(): return json.loads(Q.read_text()) if Q.exists() else []
def save(q): Q.write_text(json.dumps(q, ensure_ascii=False, indent=1))

def next_slots(q, n):
    taken = {i["when"] for i in q}; now = dt.datetime.now(BR); out = []
    for day in range(30):
        d = (now + dt.timedelta(days=day)).date()
        per_day = sum(1 for t in taken | set(out) if t.startswith(str(d)))
        for s in C["slots"]:
            t = dt.datetime.combine(d, dt.time.fromisoformat(s), BR)
            if t > now and t.isoformat() not in taken and len(out) < n and per_day < C["max_posts_per_day"]:
                out.append(t.isoformat()); per_day += 1
        if len(out) == n: return out
    return out

def approve(batch, nums):
    q = load(); base = R/"output"/batch
    dirs = [d for d in sorted(base.iterdir()) if d.is_dir() and int(d.name[:2]) in nums]
    for d, when in zip(dirs, next_slots(q, len(dirs))):
        m = json.loads((d/"meta.json").read_text()); m["status"] = "agendado"; (d/"meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
        q.append({"dir": str(d.relative_to(R)), "when": when, "done": {}}); print(f"{d.name} -> {when[:16]}")
    for d in base.iterdir():
        if d.is_dir() and int(d.name[:2]) not in nums:
            m = json.loads((d/"meta.json").read_text()); m["status"] = "reprovado"; (d/"meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
    save(q)

def post(now_all=False):
    q = load(); now = dt.datetime.now(BR)
    for it in q:
        if not now_all and dt.datetime.fromisoformat(it["when"]) > now: continue
        d = R/it["dir"]; m = json.loads((d/"meta.json").read_text())
        for name, cfg in C["platforms"].items():
            if not cfg.get("enabled") or name in it["done"]: continue
            if not any(SEC.glob(f"{name}*")): print("[sem credencial]", name, d.name); continue
            try:
                kw = {"privacy": cfg["privacy"]} if name == "tiktok" else {}
                it["done"][name] = importlib.import_module(f"publish.{name}").post(d/"video.mp4", m["title"], m["description"], SEC, **kw)
                print("[postado]", name, d.name, it["done"][name])
            except Exception as e: print("[erro]", name, d.name, str(e)[:300])
        m["status"] = "postado" if any(k in it["done"] for k in C["platforms"]) else m["status"]; m["links"] = it["done"]
        (d/"meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
    save(q)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "approve": approve(a[1], {int(x) for x in a[2:]})
    elif a[0] == "post": post("--now" in a)
    else: [print(i["when"][:16], i["dir"], i["done"]) for i in load()]
