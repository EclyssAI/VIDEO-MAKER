# ClipeiAki (ex-VIDEO-MAKER): mesma imagem para web, worker de render e Live Agent (comando diferente).
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-inter fontconfig \
    && rm -rf /var/lib/apt/lists/* && fc-cache -f
WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
# baixa o modelo do Whisper no build (evita download no primeiro job)
RUN python -c "from faster_whisper import WhisperModel; [WhisperModel(m, compute_type='int8') for m in ('small', 'base')]"
COPY . .
ENV VM_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
# Proxy confiável: defina FORWARDED_ALLOW_IPS com o IP do proxy reverso (padrão do uvicorn: só 127.0.0.1)
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
