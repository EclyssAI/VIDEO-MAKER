"""Salva 1 frame da live para medir a posição da webcam: python live/cam_probe.py <url>"""
import subprocess, sys, pathlib
o = pathlib.Path(__file__).resolve().parent.parent/"work/cam_probe.jpg"
subprocess.run(f"streamlink -O {sys.argv[1]} best | ffmpeg -y -v error -i - -frames:v 1 {o}", shell=True); print(o)
