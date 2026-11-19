"""Gera a landing (web/static/site/index.html) e as páginas jurídicas a partir das fontes:
  web/site_src/index.html  +  config/plans.yaml (mesma fonte que o backend usa para aplicar os limites)  +  web/legal_build.py
Uso: python -m web.site_build      (rodar sempre que mudar plans.yaml, a landing ou os documentos)"""
import html, pathlib, yaml
from . import legal_build

ROOT = pathlib.Path(__file__).resolve().parent
SRC, OUT = ROOT / "site_src/index.html", ROOT / "static/site/index.html"


def brl(v): return f"R$ {v:.2f}".replace(".", ",")
def usd(v): return f"US$ {v:.2f}".replace(".", ",")
def n(v): return f"{v:,}".replace(",", ".")


def cards(P):
    out = []
    for k, featured in (("creator", False), ("studio", True)):
        L = P[k]
        items = [f"<strong>{L['live_slots']}</strong> lives ao mesmo tempo",
                 f"{L['live_hours_per_month']} h e {L['live_clips_per_month']} cortes de live por mês",
                 f"{L['projects_per_month']} vídeos enviados por mês",
                 *(["Zoom e efeitos sonoros"] if L["premium_assets"] else [])]
        out.append(f"""<article class="plan reveal{' featured' if featured else ''}" aria-labelledby="pl-{k}">
      {'<span class="tag">Para quem acompanha vários canais</span>' if featured else ''}
      <h3 id="pl-{k}">{html.escape(L['label'])}</h3>
      <div class="price">{brl(L['price_brl'])} <small>/mês</small></div>
      <ul>{''.join(f'<li>{i}</li>' for i in items)}</ul>
      <a class="btn{' primary' if featured else ''} lg" href="/criar-conta" data-plan="{k}" data-label="{html.escape(L['label'])}">Criar conta · assinaturas em breve</a>
      </article>""")
    return '<div class="plans">' + "".join(out) + "</div>"


def table(P):
    c, s = P["creator"], P["studio"]
    yes = "Incluído"
    rows = [
        ("Preço", f"{brl(c['price_brl'])}/mês", f"{brl(s['price_brl'])}/mês"),
        ("Transmissões simultâneas", str(c["live_slots"]), str(s["live_slots"])),
        ("Horas de monitoramento por mês", f"{c['live_hours_per_month']} h", f"{s['live_hours_per_month']} h"),
        ("Cortes de live por mês", str(c["live_clips_per_month"]), str(s["live_clips_per_month"])),
        ("Duração máxima por sessão", f"{c['live_max_minutes'] / 60:g} h", f"{s['live_max_minutes'] / 60:g} h"),
        ("Teto mensal de gasto com IA (quando ativada)", usd(c["live_ai_usd_per_month"]), usd(s["live_ai_usd_per_month"])),
        ("Vídeos enviados por mês", f"{c['projects_per_month']} · {n(c['minutes_per_month'])} min", f"{s['projects_per_month']} · {n(s['minutes_per_month'])} min"),
        ("Duração e tamanho por vídeo", f"{c['max_video_minutes']} min · {c['max_upload_mb'] // 1024} GB", f"{s['max_video_minutes']} min · {s['max_upload_mb'] // 1024} GB"),
        ("Cortes sugeridos por vídeo enviado", str(c["clips_per_project"]), str(s["clips_per_project"])),
        ("Legenda karaokê, webcam e moldura com @", yes, yes),
        ("Zoom no pico e efeitos sonoros", "Incluído" if c["premium_assets"] else "—", "Incluído" if s["premium_assets"] else "—"),
        ("Exportação", "MP4 1080×1920, 30 fps", "MP4 1080×1920, 30 fps"),
        ("Preview, Biblioteca e downloads", yes, yes),
        ("Integração MCP (beta)", yes, yes),
        ("Cancelamento", "A qualquer momento, sem multa", "A qualquer momento, sem multa"),
    ]
    body = "".join(f'<tr><th scope="row">{a}</th><td>{b}</td><td class="hi">{d}</td></tr>' for a, b, d in rows)
    return (f'<table class="cmp"><caption>Comparação completa</caption><thead><tr><th scope="col">Recurso</th>'
            f'<th scope="col">{html.escape(c["label"])}</th><th scope="col">{html.escape(s["label"])}</th></tr></thead><tbody>{body}</tbody></table>')


def build():
    P = yaml.safe_load((ROOT.parent / "config/plans.yaml").read_text())["plans"]
    s = SRC.read_text()
    for k, v in {"{{PLANS_CARDS}}": cards(P), "{{PLANS_TABLE}}": table(P), "{{CREATOR_SLOTS}}": str(P["creator"]["live_slots"]),
                 "{{STUDIO_SLOTS}}": str(P["studio"]["live_slots"])}.items():
        s = s.replace(k, v)
    assert "{{" not in s, "placeholder sem valor na landing"
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(s)
    return OUT, legal_build.build()


if __name__ == "__main__":
    print(build())
