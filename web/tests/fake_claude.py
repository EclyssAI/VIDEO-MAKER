"""SIMULADO — servidor HTTP local que imita POST /v1/messages da Claude API.
Uso exclusivo dos testes marcados como `sim`: prova o NOSSO caminho (montagem da requisição, frames enviados, validação
da resposta, custo, orçamento, falhas), não a qualidade da análise do Claude. Nunca é usado pelo app em produção."""
import base64, hashlib, json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeClaude:
    def __init__(self, usage=(2500, 500), fail_first=0, decision="clip"):
        self.requests, self.usage, self.fail_left, self.decision = [], usage, fail_first, decision
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                imgs = [b["source"]["data"] for b in body["messages"][0]["content"] if b["type"] == "image"]
                text = "\n".join(b["text"] for b in body["messages"][0]["content"] if b["type"] == "text")
                fake.requests.append({"path": self.path, "headers": dict(self.headers), "body": body,
                                      "image_sha256": [hashlib.sha256(base64.b64decode(d)).hexdigest() for d in imgs], "text": text})
                if fake.fail_left > 0:
                    fake.fail_left -= 1
                    self.send_response(500); self.send_header("content-type", "application/json"); self.end_headers()
                    self.wfile.write(b'{"type":"error","error":{"type":"api_error","message":"falha simulada"}}'); return
                m = re.search(r"Janela candidata: t=([\d.]+)s até t=([\d.]+)s", text); a, b = float(m.group(1)), float(m.group(2))
                ts = [float(x) for x in re.findall(r"Frame \d+: t=([\d.]+)s", text)]
                out = {"decision": fake.decision, "confidence": 0.9, "start_t": a + 1, "end_t": b, "screen_title": "TESTE SIMULADO",
                       "title": "Teste simulado", "reason": f"[SIMULADO] pico em t={ts[len(ts) // 2]:.1f}s",
                       "summary": "[SIMULADO] resposta gerada pelo servidor de teste", "events": [{"t": t, "description": "frame"} for t in ts]}
                resp = {"id": "msg_sim", "type": "message", "role": "assistant", "model": "SIMULADO-sem-claude",  # aparece na interface
                        "content": [{"type": "text", "text": json.dumps(out)}], "stop_reason": "end_turn", "stop_sequence": None,
                        "usage": {"input_tokens": fake.usage[0], "output_tokens": fake.usage[1]}}
                raw = json.dumps(resp).encode()
                self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("request-id", "req_sim")
                self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self): self.server.shutdown()
