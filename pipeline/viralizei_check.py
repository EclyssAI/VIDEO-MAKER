"""Checklist /viralizei: valida edit.json e dá score 0-100. Uso: python pipeline/viralizei_check.py work/<id>/edit.json"""
import json, sys
def score(e):
    s, notes = 100, []
    dur = e["end"] - e["start"]
    def pen(c, n, p):
        nonlocal s
        if c: s -= p; notes.append(n)
    pen(dur > 59, "duração > 59s", 25)
    pen(dur < 8, "duração < 8s", 15)
    pen(len(e["title"]) > 60, "título > 60 chars", 10)
    pen(not e.get("hook") or len(e["hook"].split()) > 7, "hook ausente ou > 7 palavras", 20)
    pen(e["start"] < 0, "start inválido", 10)
    pen(len(e.get("hashtags", [])) < 3, "poucas hashtags", 5)
    pen(not e["description"].split("\n")[0].strip(), "descrição sem 1ª linha-gancho", 10)
    pen(not e.get("captions"), "sem legendas", 20)
    pen(not any(ch in e["title"] for ch in "?!") and not any(k in e["title"].lower() for k in ("gta","impossível","ninguém","absurdo")), "título sem gatilho de curiosidade", 5)
    return max(s, 0), notes
if __name__ == "__main__":
    for p in sys.argv[1:]:
        e = json.load(open(p)); sc, n = score(e); e["score"] = sc; json.dump(e, open(p, "w"), ensure_ascii=False, indent=1)
        print(p, sc, n or "OK")
