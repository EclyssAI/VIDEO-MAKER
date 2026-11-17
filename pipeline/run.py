"""Orquestra: prepare -> (Claude traduz + /viralizei gera work/<id>/edit.json) -> check -> render
  python pipeline/run.py prepare
  python pipeline/run.py render      # checa score e renderiza todos work/*/edit.json"""
import sys, glob, subprocess
R = __file__.rsplit("/", 1)[0]
if sys.argv[1] == "prepare": subprocess.run([sys.executable, f"{R}/prepare.py"], check=True)
elif sys.argv[1] == "render":
    eds = glob.glob(f"{R}/../work/*/edit.json")
    subprocess.run([sys.executable, f"{R}/viralizei_check.py", *eds], check=True)
    subprocess.run([sys.executable, f"{R}/render.py", *eds], check=True)
