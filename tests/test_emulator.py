import base64
import json
import os
import socket
import sqlite3
import stat
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from emulator.escpos import Parser
from emulator.server import VERSION, History, PrinterHandler, PrinterServer, WebServer, web_handler
from tools.send_demo import build_demo, qr_command


def parse(data):
    """Entrega os bytes um a um, como o pior caso de fragmentação TCP."""
    jobs = []
    parser = Parser(jobs.append)

    for byte in data:
        parser.feed(bytes([byte]))
    parser.close()

    return jobs


def line_text(line):
    return "".join(span["text"] for span in line["spans"])


class ParserTests(unittest.TestCase):
    def test_demo_native_commands_fragmented(self):
        data = build_demo(qr=True)

        job = parse(data)[0]
        title = job["lines"][0]["spans"][0]

        self.assertEqual(job["warnings"], [])
        self.assertEqual(job["protocol"], "bematech")
        self.assertEqual(job["reason"], "cut")
        self.assertEqual(job["lines"][0]["align"], "center")
        self.assertEqual(title["text"], "CAFÉ EXEMPLO")
        self.assertTrue(title["bold"])
        self.assertEqual((title["width"], title["height"]), (2, 2))
        self.assertEqual(base64.b64decode(job["raw_base64"]), data)

    def test_whole_job_matches_fragmented_job(self):
        data = build_demo(qr=True) + b"\x1bEA\tB\x07C\n\x1bm"

        whole_jobs = []
        parser = Parser(whole_jobs.append)
        parser.feed(data)
        parser.close()

        for whole, fragmented in zip(whole_jobs, parse(data), strict=True):
            whole.pop("created_at")
            fragmented.pop("created_at")
            self.assertEqual(whole, fragmented)

    def test_bold_commands_do_not_swallow_first_character(self):
        spans = parse(b"\x1bETitulo\x1bFCorpo\n\x1bw")[0]["lines"][0]["spans"]

        self.assertEqual([span["text"] for span in spans], ["Titulo", "Corpo"])
        self.assertEqual([span["bold"] for span in spans], [True, False])

    def test_native_fonts_and_independent_size(self):
        data = b"\x1b4\x1b\x0f\x1b-\x01A\x1b5\x1bH\x1b-\x00B\x1bd\x01C\x1bW\x01D\x1b!\x00E\n"

        spans = parse(data)[0]["lines"][0]["spans"]

        self.assertEqual([span["text"] for span in spans], list("ABCDE"))
        self.assertTrue(spans[0]["italic"] and spans[0]["underline"])
        self.assertEqual(spans[0]["font"], "B")
        self.assertFalse(spans[1]["italic"] or spans[1]["underline"])
        self.assertEqual(spans[1]["font"], "A")
        self.assertEqual([(span["width"], span["height"]) for span in spans[2:]], [(1, 2), (2, 2), (1, 1)])

    def test_code_pages_and_default_spacing(self):
        for code_page, codec in ((2, "cp850"), (3, "cp437"), (4, "cp860"), (8, "utf-8")):
            with self.subTest(codec=codec):
                text = "Café açúcar" if codec == "cp437" else "Café ação"

                job = parse(b"\x1b2\x1bt" + bytes([code_page]) + (text + "\n").encode(codec))[0]

                self.assertEqual(job["warnings"], [])
                self.assertEqual(line_text(job["lines"][0]), text)

    def test_qr_binary_data_is_not_interpreted_as_commands(self):
        payload = b"A\x00\x1d\n\x1b@\xffB"

        job = parse(qr_command(payload) + b"Texto\n\x1bm")[0]

        self.assertEqual(job["warnings"], [])
        self.assertEqual(base64.b64decode(job["lines"][0]["data_base64"]), payload)
        self.assertEqual(line_text(job["lines"][1]), "Texto")

    def test_qr_levels_default_module_and_alignment(self):
        for error, level in enumerate("LMQH"):
            with self.subTest(level=level):
                qr = parse(b"\x1ba\x01Antes" + qr_command(b"https://example.com", error, 0))[0]["lines"][1]

                self.assertEqual((qr["align"], qr["module_size"], qr["error_level"]), ("center", 4, level))
                self.assertEqual(base64.b64decode(qr["data_base64"]), b"https://example.com")

    def test_qr_length_high_byte_and_following_text(self):
        payload = b"https://example.com/" + b"a" * 300

        job = parse(qr_command(payload) + b"Depois\n")[0]

        self.assertEqual(job["warnings"], [])
        self.assertEqual(base64.b64decode(job["lines"][0]["data_base64"]), payload)
        self.assertEqual(line_text(job["lines"][1]), "Depois")

    def test_invalid_qr_does_not_prevent_text(self):
        for packet in (qr_command(b""), qr_command(b"x", error=4)):
            with self.subTest(packet=packet):
                job = parse(packet + b"Texto\n")[0]

                self.assertEqual(line_text(job["lines"][0]), "Texto")
                self.assertEqual(len(job["warnings"]), 1)

    def test_non_rendered_binary_blocks_and_physical_commands(self):
        data = (
            b"\x1b(A\x04\x00\x01\x02\x01\x00\x1bv\x00\x1b\x80\x01"
            b"\x1b*\x21\x01\x00\x1b\x00\x0a\x1cp\x01\x00"
            b"\x1dk\x04ABC\x00\x1dk\x49\x03\x1b\x00\x0aTexto\n"
        )

        job = parse(data)[0]

        self.assertEqual(line_text(job["lines"][0]), "Texto")
        self.assertEqual(len(job["warnings"]), 3)

    def test_cut_preserves_printer_state_across_jobs(self):
        first, second = parse(b"\x1bEPrimeiro\n\x1bwSegundo\n\x1bm")
        reset = parse(b"\x1bE\x1b@Normal\n")[0]

        self.assertTrue(second["lines"][0]["spans"][0]["bold"])
        self.assertEqual((first["reason"], second["reason"]), ("cut", "cut"))
        self.assertFalse(reset["lines"][0]["spans"][0]["bold"])

    def test_incomplete_command_and_stray_gs(self):
        data = b"A\x1d\n\nB\n\x1dkQ\x01"

        job = parse(data)[0]

        self.assertEqual([line_text(line) for line in job["lines"]], ["A", "", "B"])
        self.assertEqual(job["warnings"], ["Comando incompleto ao encerrar a conexão."])
        self.assertEqual(base64.b64decode(job["raw_base64"]), data)

    def test_status_does_not_create_jobs(self):
        self.assertEqual(parse(b"\x10\x04\x01\x1d\xf8\x31"), [])

    def test_bytes_after_cut_do_not_create_empty_job(self):
        self.assertEqual([job["reason"] for job in parse(b"Texto\n\x1bw\x1b@\n \n")], ["cut"])
        self.assertEqual(parse(b"\x1b@\x1ba\x01\n\n\x1bw"), [])

        image = parse(b"\x1b*\x21\x01\x00abc")
        self.assertEqual(image[0]["warnings"], ["Imagem ESC * não renderizada."])

    def test_drawer_events_fragmented_and_separated_by_cuts(self):
        first, second = parse(b"\x1bv\xc8Texto\n\x1bw\x1b\x80\x64\x1bm")

        self.assertEqual(first["events"], [dict(type="drawer", drawer=1, pulse_ms=200)])
        self.assertEqual(second["events"], [dict(type="drawer", drawer=2, pulse_ms=100)])
        self.assertEqual(line_text(first["lines"][0]), "Texto")
        self.assertEqual(first["warnings"], [])


class HistoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "history.sqlite3"
        self.history = History(self.path)

    def test_list_version_changes_after_clear_with_same_number(self):
        self.assertEqual(self.history.version(), '"empty"')

        self.history.save(parse(b"Primeiro\n")[0])
        first = self.history.version()
        self.assertEqual(self.history.version(), first)

        self.history.clear()
        self.history.save(parse(b"Outro\n")[0])
        self.assertTrue(self.history.version().startswith('"1-'))
        self.assertNotEqual(self.history.version(), first)

    def test_drawer_preview_and_binary_payload_keep_storage(self):
        drawer = parse(b"\x1d\xf9\x20\x00\x1b2\x1bt\x02\x1bv\xc8")[0]
        binary = parse(qr_command(b"A\x1bv\xc8B"))[0]

        self.history.save(drawer)
        self.history.save(binary)

        self.assertEqual(self.history.list()[1]["preview"], "Abertura da gaveta 1 · pulso de 200 ms")
        self.assertEqual(self.history.get(1)["events"][0]["drawer"], 1)
        self.assertEqual(self.history.get(1)["lines"], [])
        self.assertEqual(self.history.get(2)["events"], [])

        with closing(sqlite3.connect(self.history.path)) as connection:
            stored = json.loads(connection.execute("SELECT payload FROM jobs WHERE id=1").fetchone()[0])
        self.assertEqual(stored, drawer)

    def test_history_keeps_state_after_cut_and_restart(self):
        parser = Parser(self.history.save)
        parser.feed(b"\x1bEA\x1bwB\x1bm")
        parser.close()

        restored = History(self.path)

        self.assertEqual(len(restored.list()), 2)
        self.assertTrue(restored.get(2)["lines"][0]["spans"][0]["bold"])

    def test_keeps_only_the_most_recent_jobs(self):
        history = History(self.path, keep=2)

        for text in (b"Um\n", b"Dois\n", b"Tres\n"):
            history.save(parse(text)[0])

        self.assertEqual([job["preview"] for job in history.list()], ["Tres", "Dois"])

    def test_lower_limit_applies_on_open_and_zero_keeps_everything(self):
        for text in (b"Um\n", b"Dois\n", b"Tres\n"):
            self.history.save(parse(text)[0])

        self.assertEqual(len(History(self.path, keep=0).list()), 3)
        self.assertEqual([job["id"] for job in History(self.path, keep=1).list()], [3])

    def test_read_only_database_fails_on_open(self):
        os.chmod(self.path, stat.S_IREAD)
        self.addCleanup(os.chmod, self.path, stat.S_IREAD | stat.S_IWRITE)

        with self.assertRaises(sqlite3.Error):
            History(self.path)


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
        with self.assertLogs("emulator.server", "INFO") as logs:
            self.send(b"Primeiro\n\x1bwSegundo\n")

        message = logs.output[-1]
        self.assertIn("Conexão de 127.0.0.1 finalizada por conexão encerrada", message)
        self.assertIn("impressões salvas: 2", message)
        self.assertNotIn("Primeiro", message)

    def test_idle_connection_is_saved_as_idle(self):
        with mock.patch("emulator.server.IDLE_SECONDS", 0.6):
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
