"""Servidor TCP EscBematech e visualizador HTTP com histórico SQLite."""
import argparse
import errno
import ipaddress
import json
import socket
import socketserver
import sqlite3
import sys
import threading
import time
import webbrowser
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from escpos import Parser

ROOT = Path(__file__).resolve().parent
# Os recursos do .exe ficam em uma pasta temporária; o histórico precisa
# permanecer ao lado do executável para sobreviver a cada nova execução.
DATA_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
VERSION = "1.1.0"
SERVER_NAME = "EmuladorEscBematech"
IDLE_SECONDS = 60
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/paper.js": ("paper.js", "application/javascript; charset=utf-8"),
          "/qrcode.js": ("qrcode.js", "application/javascript; charset=utf-8")}


def job_events(job):
    return [dict(event, description=f"Abertura da gaveta {event['drawer']} · pulso de {event['pulse_ms']} ms")
            for event in job["events"] if event["type"] == "drawer"]


def job_summary(job):
    preview = " ".join(s["text"] for line in job["lines"] for s in line["spans"]).strip()[:90]
    if not preview:
        preview = "; ".join(e["description"] for e in job_events(job))
    return job["created_at"], job["reason"], preview


class History:
    def __init__(self, path):
        self.path = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            # O resumo em colunas evita decodificar todos os payloads a cada atualização da lista.
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, payload TEXT NOT NULL,"
                       " created_at TEXT NOT NULL, reason TEXT NOT NULL, preview TEXT NOT NULL)")
            # Com a tabela já criada, um banco somente leitura abre sem erro e só
            # falharia ao gravar a primeira impressão, depois que ela foi recebida.
            # Um comando de escrita que não afeta linhas já revela isso.
            db.execute("DELETE FROM jobs WHERE 0")

    def save(self, job):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO jobs(payload, created_at, reason, preview) VALUES (?, ?, ?, ?)",
                       (json.dumps(job), *job_summary(job)))

    def clear(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute("DELETE FROM jobs").rowcount

    def version(self):
        # A numeração recomeça depois de limpar o histórico; a data da última
        # impressão distingue a lista nova de uma antiga com o mesmo número.
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT id, created_at FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
        return f'"{row[0]}-{row[1]}"' if row else '"vazio"'

    def list(self):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT id, created_at, reason, preview FROM jobs ORDER BY id DESC").fetchall()
        return [dict(id=job_id, created_at=created_at, reason=reason, preview=preview)
                for job_id, created_at, reason, preview in rows]

    def get(self, job_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = json.loads(row[0])
        job["events"] = job_events(job)
        return dict(id=job_id, **job)


class PrinterHandler(socketserver.BaseRequestHandler):
    def handle(self):
        parser = Parser(self.server.history.save)
        received, reason = 0, "disconnect"
        try:
            # Timeout curto permite encerrar mesmo quando o select do Windows
            # não acorda imediatamente após shutdown feito por outra thread.
            self.request.settimeout(0.5)
            last_received = time.monotonic()
            while not self.server.stopping:
                try:
                    data = self.request.recv(4096)
                except socket.timeout:
                    if time.monotonic() - last_received >= IDLE_SECONDS:
                        reason = "idle"
                        break
                    continue
                if not data:
                    break
                last_received = time.monotonic()
                received += len(data)
                if received > 10 * 1024 * 1024:
                    parser.warnings.add("Limite de 10 MiB por conexão atingido; impressão truncada.")
                    break
                parser.feed(data)
        except (OSError, TimeoutError):
            pass
        finally:
            parser.close(reason)


class PortInUseError(OSError):
    def __init__(self, port):
        super().__init__(f"A porta {port} já está em uso por outro programa. "
                         "Escolha outra com --port ou --web-port.")


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


class WebServer(ExclusivePortMixin, ThreadingHTTPServer):
    pass


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
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.send_error(403)
                return
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(403)
                return
            self.send_json(dict(deleted=history.clear()))

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in STATIC:
                name, content_type = STATIC[path]
                body = (ROOT / "web" / name).read_bytes().replace(b"{{VERSION}}", VERSION.encode())
                self.send_body(body, content_type)
            elif path == "/api/jobs":
                tag = history.version()
                if self.headers.get("If-None-Match") == tag:
                    self.send_response(304)
                    self.send_header("ETag", tag)
                    self.end_headers()
                else:
                    self.send_json(history.list(), etag=tag)
            elif path.startswith("/api/jobs/"):
                try:
                    job = history.get(int(path.rsplit("/", 1)[1]))
                except ValueError:
                    job = None
                if job is None:
                    self.send_error(404)
                else:
                    self.send_json(job)
            else:
                self.send_error(404)

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
    history = History(config.db)
    with PrinterServer((config.host, config.port), PrinterHandler) as tcp:
        tcp.history = history
        with WebServer((config.host, config.web_port), web_handler(history)) as web:
            threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (tcp, web)]
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
        # O contexto TCP espera os handlers gravarem as impressões pendentes.


def running_emulator(url):
    try:
        with urlopen(url, timeout=2) as response:
            return response.headers.get("Server", "").startswith(SERVER_NAME)
    except OSError:
        return False


def port_number(value):
    try:
        port = int(value)
    except ValueError:
        port = -1
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"porta inválida: {value} (use um número de 0 a 65535)")
    return port


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        if sys.stderr is None and sys.platform == "win32":
            from tray import show_error
            show_error(f"{message}\n\nUse --help para ver as opções.")
            raise SystemExit(2)
        super().error(message)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if sys.platform == "win32" and sys.stdout is None and any(
            flag in argv for flag in ("--console", "--licenses", "--version", "--help", "-h")):
        from tray import ensure_console
        # O terminal não espera um programa de janela: o emulador ficaria rodando
        # escondido e sem receber Ctrl+C. Ele ganha uma janela própria.
        ensure_console(own_window="--console" in argv)
    args = ArgumentParser(description="Emulador EscBematech com histórico persistente", add_help=False)
    args.add_argument("-h", "--help", action="help", help="Mostra esta ajuda e sai")
    args.add_argument("--host", default="127.0.0.1",
                      help="Endereço de escuta; 0.0.0.0 aceita outros computadores (padrão: 127.0.0.1)")
    args.add_argument("--port", type=port_number, default=9100, help="Porta da impressora (padrão: 9100)")
    args.add_argument("--web-port", type=port_number, default=9101, help="Porta do histórico no navegador (padrão: 9101)")
    args.add_argument("--db", type=Path, default=DATA_ROOT / "data" / "history.sqlite3",
                      help="Arquivo do histórico (padrão: data/history.sqlite3 ao lado do programa)")
    args.add_argument("--version", action="version", version=f"Emulador EscBematech {VERSION}",
                      help="Mostra a versão e sai")
    args.add_argument("--licenses", action="store_true", help="Exibe licenças das bibliotecas incluídas")
    mode = args.add_mutually_exclusive_group()
    mode.add_argument("--tray", dest="tray", action="store_true", help="Executa na bandeja do Windows")
    mode.add_argument("--console", dest="tray", action="store_false", help="Executa no terminal")
    args.set_defaults(tray=getattr(sys, "frozen", False) and sys.platform == "win32")
    config = args.parse_args(argv)
    if config.licenses:
        print((ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8"))
        return

    def fail(message):
        if config.tray and sys.platform == "win32":
            from tray import show_error
            show_error(message)
            return 1
        args.error(message)

    browser_host = "127.0.0.1" if config.host == "0.0.0.0" else config.host
    try:
        if config.tray and sys.platform != "win32":
            raise RuntimeError("O modo bandeja está disponível apenas no Windows.")
        with running_servers(config) as (tcp, web):
            url = f"http://{browser_host}:{web.server_port}"
            if config.tray:
                from tray import run_tray
                run_tray(url, port=tcp.server_address[1])
            else:
                print(f"Impressora: {config.host}:{tcp.server_address[1]}")
                print(f"Histórico: {url}")
                print("Protocolo: EscBematech — 48 colunas")
                print(f"Banco: {config.db.resolve()} — Ctrl+C para sair", flush=True)
                threading.Event().wait()
    except KeyboardInterrupt:
        pass
    except PortInUseError as error:
        # Abrir o programa de novo só mostra o histórico da instância em execução.
        url = f"http://{browser_host}:{config.web_port}"
        if not running_emulator(url):
            return fail(str(error))
        if config.tray:
            webbrowser.open(url)
        else:
            print(f"O emulador já está em execução. Histórico: {url}")
    except sqlite3.Error as error:
        return fail(f"Não foi possível usar o histórico em {config.db.resolve()}: {error}. "
                    "Escolha outro arquivo com --db.")
    except (OSError, RuntimeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
