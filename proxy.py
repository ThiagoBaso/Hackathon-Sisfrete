#!/usr/bin/env python3
"""Proxy local para o mapas-frete.html.

Serve o HTML em http://127.0.0.1:8000 e encaminha /os/* ao cluster da Sisfrete,
injetando o Basic Auth no servidor (a senha nunca vai para o navegador) e
resolvendo CORS. Só deixa passar buscas de leitura nos índices quotations-*/pedidos-*.

Uso:
    python proxy.py
"""
import base64
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("SISFRETE_URL", "https://api.opensearch.sisfrete.com.br").rstrip("/")
SISFRETE_USER = os.environ.get("SISFRETE_USER", "unimar-grupo-15")
SISFRETE_PASS = os.environ.get("SISFRETE_PASS", "O4pOC6TTFdb24OjzE2LQ")
AUTH = "Basic " + base64.b64encode(
    f"{SISFRETE_USER}:{SISFRETE_PASS}".encode()
).decode()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PERMITIDO_INDICE = re.compile(r"^/(quotations|pedidos)-[\w.*-]+/(_search|_count|_mapping|_field_caps|_msearch)$")
PERMITIDO_CAT = re.compile(r"^/_cat/indices/(quotations|pedidos)-[\w.*-]+$")
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapas-frete.html")
LIMITE_CORPO = 1_000_000


class Handler(BaseHTTPRequestHandler):
    def _responder(self, codigo, corpo, tipo="application/json"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _permitido(self, caminho):
        alvo = caminho[3:] if caminho.startswith("/os/") else caminho
        return bool(PERMITIDO_INDICE.match(alvo) or PERMITIDO_CAT.match(alvo))

    def _encaminhar(self, metodo):
        caminho, _, query = self.path.partition("?")
        if not caminho.startswith("/os/") or not self._permitido(caminho):
            return self._responder(403, b'{"error":"caminho nao permitido"}')
        tamanho = int(self.headers.get("Content-Length", 0))
        if tamanho > LIMITE_CORPO:
            return self._responder(413, b'{"error":"corpo grande demais"}')
        corpo = self.rfile.read(tamanho) if tamanho else None
        url = UPSTREAM + caminho[3:] + ("?" + query if query else "")
        headers = {"Authorization": AUTH}
        if corpo is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=corpo, method=metodo, headers=headers)
        try:
            with OPENER.open(req, timeout=120) as r:
                codigo, dados = r.status, r.read()
        except urllib.error.HTTPError as e:
            codigo, dados = e.code, e.read()
        except Exception as e:  # rede, TLS, timeout
            codigo, dados = 502, ('{"error":{"reason":"%s"}}' % str(e).replace('"', "'")).encode()
        self._responder(codigo, dados)

    def do_OPTIONS(self):
        self._responder(204, b"")

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            with open(HTML, "rb") as f:
                self._responder(200, f.read(), "text/html; charset=utf-8")
        elif self.path.startswith("/os/"):
            self._encaminhar("GET")
        else:
            self._responder(404, b'{"error":"nao encontrado"}')

    def do_POST(self):
        self._encaminhar("POST")

    def log_message(self, fmt, *args):
        print("%s %s" % (self.command, self.path.split("?")[0]), args[1] if len(args) > 1 else "")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
