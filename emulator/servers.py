"""Servidor TCP da impressora e servidor HTTP do histórico."""

import errno
import ipaddress
import json
import logging
import socket
import socketserver
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from emulator import VERSION
from emulator.escpos import Parser
from emulator.history import History

SERVER_NAME = "EmuladorEscBematech"

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"

IDLE_SECONDS = 60
RECEIVE_TIMEOUT_SECONDS = 0.5
MAX_CONNECTION_BYTES = 10 * 1024 * 1024
END_REASONS = {"disconnect": "conexão encerrada", "idle": f"{IDLE_SECONDS} segundos sem dados"}

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/paper.js": ("paper.js", "application/javascript; charset=utf-8"),
    "/qrcode.js": ("qrcode.js", "application/javascript; charset=utf-8"),
    "/fonts/roboto.woff2": ("fonts/roboto.woff2", "font/woff2"),
    "/fonts/roboto-mono.woff2": ("fonts/roboto-mono.woff2", "font/woff2"),
}


class PrinterHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self.client = self.client_address[0]
        self.received = 0
        self.saved = 0

    def save(self, job):
        self.server.history.save(job)
        self.saved += 1

    def handle(self):
        parser = Parser(self.save)
        reason = "disconnect"

        try:
            reason = self.receive(parser)
        except OSError as error:
            logger.warning("Conexão de %s interrompida: %s", self.client, error)
        finally:
            parser.close(reason)
            logger.info(
                "Conexão de %s finalizada por %s: %d bytes, impressões salvas: %d.",
                self.client,
                END_REASONS[reason],
                self.received,
                self.saved,
            )

    def receive(self, parser):
        # Timeout curto permite encerrar mesmo quando o select do Windows
        # não acorda imediatamente após shutdown feito por outra thread.
        self.request.settimeout(RECEIVE_TIMEOUT_SECONDS)
        last_received = time.monotonic()

        while not self.server.stopping:
            try:
                data = self.request.recv(4096)
            except TimeoutError:
                if time.monotonic() - last_received >= IDLE_SECONDS:
                    return "idle"
                continue

            if not data:
                break

            last_received = time.monotonic()
            self.received += len(data)
            if self.received > MAX_CONNECTION_BYTES:
                parser.warnings.add("Limite de 10 MiB por conexão atingido; impressão truncada.")
                logger.warning("Conexão de %s passou de 10 MiB; impressão truncada.", self.client)
                break

            parser.feed(data)

        return "disconnect"


class PortInUseError(OSError):
    def __init__(self, port):
        super().__init__(f"A porta {port} já está em uso por outro programa. Escolha outra com --port ou --web-port.")


class ExclusivePortMixin:
    # No Windows, SO_REUSEADDR deixa uma segunda instância ocupar a mesma porta
    # em silêncio; o uso exclusivo faz o bind falhar com "porta ocupada".
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)

        try:
            super().server_bind()
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise PortInUseError(self.server_address[1]) from error
            raise


class PrinterServer(ExclusivePortMixin, socketserver.ThreadingTCPServer):
    # Ao fechar, o servidor espera cada conexão aberta gravar a impressão pendente.
    daemon_threads = False

    def __init__(self, *args, **kwargs):
        self.connections = set()
        self.connection_lock = threading.Lock()
        self.stopping = False
        super().__init__(*args, **kwargs)

    def process_request_thread(self, request, client_address):
        with self.connection_lock:
            if self.stopping:
                self.shutdown_request(request)
                return
            self.connections.add(request)

        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.connection_lock:
                self.connections.discard(request)

    def close_connections(self):
        with self.connection_lock:
            self.stopping = True
            for connection in self.connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle_error(self, request, client_address):
        logger.exception("Erro ao processar a impressão de %s.", client_address[0])


class WebServer(ExclusivePortMixin, ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # O navegador fecha a conexão no meio da resposta ao trocar de página ou fechar a aba.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return

        logger.exception("Erro ao atender o histórico para %s.", client_address[0])


def trusted_host(host):
    # DNS rebinding depende de um nome de domínio apontado para este IP;
    # o histórico só é servido quando acessado por IP ou localhost.
    try:
        name = urlsplit("//" + host).hostname
    except ValueError:
        return False

    if name == "localhost":
        return True

    try:
        ipaddress.ip_address(name or "")
    except ValueError:
        return False
    return True


def web_handler(history):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{SERVER_NAME}/{VERSION}"

        def parse_request(self):
            if not super().parse_request():
                return False

            if not trusted_host(self.headers.get("Host", "")):
                self.send_error(403)
                return False

            return True

        def do_DELETE(self):
            if self.path != "/api/jobs":
                self.send_error(404)
                return

            origin = self.headers.get("Origin")
            same_origin = not origin or origin == "http://" + self.headers.get("Host", "")
            if not same_origin or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(403)
                return

            self.send_json({"deleted": history.clear()})

        def do_GET(self):
            path = self.path.split("?", 1)[0]

            if path in STATIC:
                self.send_static(*STATIC[path])
            elif path == "/api/jobs":
                self.send_job_list()
            elif path.startswith("/api/jobs/"):
                self.send_job(path.rsplit("/", 1)[1])
            else:
                self.send_error(404)

        def send_static(self, name, content_type):
            body = (WEB_DIR / name).read_bytes()
            if content_type.startswith("text/html"):
                body = body.replace(b"{{VERSION}}", VERSION.encode())

            self.send_body(body, content_type)

        def send_job_list(self):
            tag = history.version()

            if self.headers.get("If-None-Match") == tag:
                self.send_response(304)
                self.send_header("ETag", tag)
                self.end_headers()
                return

            self.send_json(history.list(), etag=tag)

        def send_job(self, job_id):
            job = history.get(int(job_id)) if job_id.isdigit() else None

            if job is None:
                self.send_error(404)
                return

            self.send_json(job)

        def send_json(self, value, etag=None):
            self.send_body(json.dumps(value).encode(), "application/json; charset=utf-8", etag)

        def send_body(self, body, content_type, etag=None):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    return Handler


@contextmanager
def running_servers(config):
    history = History(config.db, config.keep)

    with PrinterServer((config.host, config.port), PrinterHandler) as tcp:
        tcp.history = history

        with WebServer((config.host, config.web_port), web_handler(history)) as web:
            threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (tcp, web)]
            for thread in threads:
                thread.start()

            try:
                yield tcp, web
            finally:
                tcp.close_connections()
                tcp.shutdown()
                web.shutdown()
                for thread in threads:
                    thread.join()
