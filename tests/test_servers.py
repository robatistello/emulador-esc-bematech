import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from emulator import VERSION
from emulator.history import History
from emulator.servers import PrinterHandler, PrinterServer, WebServer, web_handler
from support import line_text


class ServerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.history = History(Path(folder.name) / "history.sqlite3")

        self.tcp = PrinterServer(("127.0.0.1", 0), PrinterHandler)
        self.tcp.history = self.history
        self.web = WebServer(("127.0.0.1", 0), web_handler(self.history))
        self.url = f"http://127.0.0.1:{self.web.server_port}"

        for server in (self.tcp, self.web):
            # O intervalo curto faz o shutdown de cada teste levar milissegundos, não meio segundo.
            threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=0.05), daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

    def send(self, data):
        with socket.create_connection(self.tcp.server_address, timeout=3) as client:
            client.sendall(data)
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(client.recv(1), b"", "o servidor deve fechar depois de gravar")

    def request(self, path, method="GET", headers=None):
        return urlopen(Request(self.url + path, method=method, headers=headers or {}))

    def get_json(self, path, headers=None):
        with self.request(path, headers=headers) as response:
            return json.load(response)

    def assert_status(self, status, path, method="GET", headers=None):
        with self.assertRaises(HTTPError) as error:
            self.request(path, method, headers)

        self.assertEqual(error.exception.code, status)
        error.exception.close()

    def test_received_jobs_are_listed_and_served(self):
        self.send(b"Primeiro\n\x1bwSegundo\n")

        self.assertEqual([job["preview"] for job in self.get_json("/api/jobs")], ["Segundo", "Primeiro"])
        self.assertEqual(line_text(self.get_json("/api/jobs/1")["lines"][0]), "Primeiro")
        self.assert_status(404, "/api/jobs/99")
        self.assert_status(404, "/api/jobs/abc")

    def test_page_and_static_files(self):
        with self.request("/") as response:
            page = response.read()
            self.assertIn(f"EscBematech {VERSION} ·".encode(), page)
            self.assertNotIn(b"{{VERSION}}", page)
            self.assertEqual(response.headers["Server"].split()[0], f"EmuladorEscBematech/{VERSION}")

        with self.request("/style.css") as response:
            self.assertEqual(response.headers["Content-Type"], "text/css; charset=utf-8")
            self.assertIn(b"--accent", response.read())

        for path, marker in (
            ("/app.js", b"function refresh"),
            ("/paper.js", b"layoutPaper"),
            ("/qrcode.js", b"QR Code"),
        ):
            with self.subTest(path=path), self.request(path) as response:
                self.assertIn(marker, response.read())

        for path in ("/fonts/roboto.woff2", "/fonts/roboto-mono.woff2"):
            with self.subTest(path=path), self.request(path) as response:
                self.assertEqual(response.headers["Content-Type"], "font/woff2")
                self.assertEqual(response.read(4), b"wOF2")

    def test_unchanged_list_answers_not_modified(self):
        self.send(b"Texto\n")

        with self.request("/api/jobs") as response:
            tag = response.headers["ETag"]

        with self.assertRaises(HTTPError) as unchanged:
            self.request("/api/jobs", headers={"If-None-Match": tag})
        self.assertEqual((unchanged.exception.code, unchanged.exception.read()), (304, b""))
        unchanged.exception.close()

    def test_cross_origin_delete_is_denied(self):
        self.send(b"Texto\n")

        self.assert_status(403, "/api/jobs", "DELETE", {"Origin": "https://example.com"})
        self.assertEqual(len(self.history.list()), 1)

    def test_dns_rebinding_is_denied(self):
        # Página com DNS rebinding: Origin e Host coincidem, mas o nome não é IP.
        host = f"evil.example:{self.web.server_port}"

        for method in ("GET", "DELETE"):
            with self.subTest(method=method):
                self.assert_status(403, "/api/jobs", method, {"Host": host, "Origin": "http://" + host})

        self.assertEqual(self.get_json("/api/jobs", {"Host": f"localhost:{self.web.server_port}"}), [])

    def test_clear_restarts_numbering(self):
        self.send(b"Primeiro\n\x1bwSegundo\n")

        with self.request("/api/jobs", method="DELETE") as response:
            self.assertEqual(json.load(response)["deleted"], 2)
        self.assertEqual(self.history.list(), [])

        self.send(b"Novo\n\x1bw")
        self.assertEqual([(job["id"], job["preview"]) for job in self.get_json("/api/jobs")], [(1, "Novo")])

    def test_connection_is_logged_without_print_content(self):
        with self.assertLogs("emulator.servers", "INFO") as logs:
            self.send(b"Primeiro\n\x1bwSegundo\n")

        message = logs.output[-1]
        self.assertIn("Conexão de 127.0.0.1 finalizada por conexão encerrada", message)
        self.assertIn("impressões salvas: 2", message)
        self.assertNotIn("Primeiro", message)

    def test_idle_connection_is_saved_as_idle(self):
        with mock.patch("emulator.servers.IDLE_SECONDS", 0.6):
            with socket.create_connection(self.tcp.server_address, timeout=3) as client:
                client.sendall(b"Sem corte\n")
                self.assertEqual(client.recv(1), b"")

        self.assertEqual(self.history.list()[0]["reason"], "idle")


class PortTests(unittest.TestCase):
    def test_second_instance_cannot_share_ports(self):
        for server_class, handler in ((PrinterServer, PrinterHandler), (WebServer, web_handler(None))):
            with self.subTest(server=server_class.__name__), server_class(("127.0.0.1", 0), handler) as first:
                with self.assertRaises(OSError):
                    server_class(first.server_address, handler).server_close()


if __name__ == "__main__":
    unittest.main()
