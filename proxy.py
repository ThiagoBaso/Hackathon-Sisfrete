#!/usr/bin/env python3

import base64
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def carregar_env():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(caminho):
        return
    with open(caminho, encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, valor = linha.split("=", 1)
            os.environ.setdefault(nome.strip(), valor.strip().strip("\"'"))


carregar_env()
UPSTREAM = os.environ.get("SISFRETE_URL", "https://api.opensearch.sisfrete.com.br").rstrip("/")
SISFRETE_USER = os.environ.get("SISFRETE_USER", "")
SISFRETE_PASS = os.environ.get("SISFRETE_PASS", "")
if not SISFRETE_USER or not SISFRETE_PASS:
    raise RuntimeError("Configure SISFRETE_USER e SISFRETE_PASS no arquivo .env ou no ambiente.")
AUTH = "Basic " + base64.b64encode(
    f"{SISFRETE_USER}:{SISFRETE_PASS}".encode()
).decode()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PERMITIDO_INDICE = re.compile(r"^/(quotations|pedidos)-[\w.*-]+/(_search|_count|_mapping|_field_caps|_msearch)$")
PERMITIDO_CAT = re.compile(r"^/_cat/indices/(quotations|pedidos)-[\w.*-]+$")
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapas-frete.html")
LIMITE_CORPO = 1_000_000


def _filtrar_consulta(consulta, cliente):
    consulta_query = consulta.get("query")
    filtro_cliente = {"term": {"nf.cliente": cliente}}
    if isinstance(consulta_query, dict) and isinstance(consulta_query.get("bool"), dict):
        bool_query = consulta_query["bool"]
        filtros = bool_query.setdefault("filter", [])
        if not isinstance(filtros, list):
            filtros = [filtros]
            bool_query["filter"] = filtros
        filtros.append(filtro_cliente)
    else:
        consulta["query"] = {"bool": {"must": [consulta_query or {"match_all": {}}], "filter": [filtro_cliente]}}
    return consulta


def _cliente_da_consulta(valor):
    if isinstance(valor, dict):
        termo = valor.get("term")
        if isinstance(termo, dict) and "nf.cliente" in termo:
            try:
                cliente = int(termo["nf.cliente"])
                return cliente if cliente > 0 else None
            except (TypeError, ValueError):
                return None
        for item in valor.values():
            cliente = _cliente_da_consulta(item)
            if cliente:
                return cliente
    elif isinstance(valor, list):
        for item in valor:
            cliente = _cliente_da_consulta(item)
            if cliente:
                return cliente
    return None


class Handler(BaseHTTPRequestHandler):
    def _responder(self, codigo, corpo, tipo="application/json"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Sisfrete-Cliente")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _permitido(self, caminho):
        alvo = caminho[3:] if caminho.startswith("/os/") else caminho
        return bool(PERMITIDO_INDICE.match(alvo) or PERMITIDO_CAT.match(alvo))

    def _encaminhar(self, metodo):
        caminho, _, url_query = self.path.partition("?")
        if not caminho.startswith("/os/") or not self._permitido(caminho):
            return self._responder(403, b'{"error":"caminho nao permitido"}')
        tamanho = int(self.headers.get("Content-Length", 0))
        if tamanho > LIMITE_CORPO:
            return self._responder(413, b'{"error":"corpo grande demais"}')
        corpo = self.rfile.read(tamanho) if tamanho else None
        if metodo == "POST" and caminho.endswith(("/_search", "/_count", "/_msearch")):
            try:
                cabecalho_cliente = self.headers.get("X-Sisfrete-Cliente", "")
                cliente = int(cabecalho_cliente) if cabecalho_cliente else None
                if caminho.endswith("/_msearch"):
                    linhas = (corpo or b"").decode().splitlines()
                    if len(linhas) % 2:
                        raise ValueError
                    saida = []
                    for pos in range(0, len(linhas), 2):
                        consulta = json.loads(linhas[pos + 1])
                        cliente_consulta = cliente or _cliente_da_consulta(consulta)
                        if not cliente_consulta:
                            raise ValueError
                        saida.append(linhas[pos])
                        saida.append(json.dumps(_filtrar_consulta(consulta, cliente_consulta), separators=(",", ":")))
                    corpo = ("\n".join(saida) + "\n").encode()
                else:
                    consulta = json.loads(corpo or b"{}")
                    cliente_consulta = cliente or _cliente_da_consulta(consulta)
                    if not cliente_consulta:
                        raise ValueError
                    corpo = json.dumps(_filtrar_consulta(consulta, cliente_consulta), separators=(",", ":")).encode()
            except (TypeError, ValueError, json.JSONDecodeError):
                return self._responder(400, b'{"error":"consulta deve conter um nf.cliente inteiro positivo"}')
        url = UPSTREAM + caminho[3:] + ("?" + url_query if url_query else "")
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
        if self.path.split("?")[0] in ("/", "/index.html", "/mapas-frete.html"):
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
