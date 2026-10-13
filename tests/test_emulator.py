import base64
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from escpos import Parser
from tools.send_demo import build_demo, qr_command
from server import VERSION, History, PrinterServer, PrinterHandler, WebServer, web_handler


class EmulatorTests(unittest.TestCase):
    def parse(self, job):
        saved = []
        parser = Parser(saved.append)
        for byte in job:
            parser.feed(bytes([byte]))
        parser.close()
        return saved

    def test_demo_native_commands_fragmented(self):
        job = build_demo(qr=True)
        printed = self.parse(job)[0]
        self.assertEqual(printed["warnings"], [])
        self.assertEqual(printed["protocol"], "bematech")
        first = printed["lines"][0]
        self.assertEqual(first["align"], "center")
        self.assertEqual(first["spans"][0]["text"], "CAFÉ EXEMPLO")
        self.assertTrue(first["spans"][0]["bold"])
        self.assertEqual((first["spans"][0]["width"], first["spans"][0]["height"]), (2, 2))
        self.assertEqual(base64.b64decode(printed["raw_base64"]), job)
        self.assertEqual(printed["reason"], "cut")

    def test_whole_job_matches_fragmented_job(self):
        job = build_demo(qr=True) + b"\x1bEA\tB\x07C\n\x1bm"
        parser_output = []
        parser = Parser(parser_output.append)
        parser.feed(job)
        parser.close()
        for whole, fragmented in zip(parser_output, self.parse(job), strict=True):
            whole.pop("created_at"), fragmented.pop("created_at")
            self.assertEqual(whole, fragmented)

    def test_bold_commands_do_not_swallow_first_character(self):
        spans = self.parse(b"\x1bETitulo\x1bFCorpo\n\x1bw")[0]["lines"][0]["spans"]
        self.assertEqual([s["text"] for s in spans], ["Titulo", "Corpo"])
        self.assertEqual([s["bold"] for s in spans], [True, False])

    def test_native_fonts_and_independent_size(self):
        job = b"\x1b4\x1b\x0f\x1b-\x01A\x1b5\x1bH\x1b-\x00B\x1bd\x01C\x1bW\x01D\x1b!\x00E\n"
        spans = self.parse(job)[0]["lines"][0]["spans"]
        self.assertEqual([s["text"] for s in spans], list("ABCDE"))
        self.assertTrue(spans[0]["italic"] and spans[0]["underline"])
        self.assertEqual(spans[0]["font"], "B")
        self.assertFalse(spans[1]["italic"] or spans[1]["underline"])
        self.assertEqual(spans[1]["font"], "A")
        self.assertEqual([(s["width"], s["height"]) for s in spans[2:]], [(1, 2), (2, 2), (1, 1)])

    def test_codepages_and_default_spacing(self):
        for n, codec in ((2, "cp850"), (3, "cp437"), (4, "cp860"), (8, "utf-8")):
            with self.subTest(codec=codec):
                text = "Café açúcar" if codec == "cp437" else "Café ação"
                printed = self.parse(b"\x1b2\x1bt" + bytes([n]) + (text + "\n").encode(codec))[0]
                self.assertEqual(printed["warnings"], [])
                self.assertEqual(printed["lines"][0]["spans"][0]["text"], text)

    def test_qr_binary_data_is_not_interpreted_as_commands(self):
        payload = b"A\x00\x1d\n\x1b@\xffB"
        printed = self.parse(qr_command(payload) + b"Texto\n\x1bm")[0]
        self.assertEqual(printed["warnings"], [])
        self.assertEqual(base64.b64decode(printed["lines"][0]["data_base64"]), payload)
        self.assertEqual(printed["lines"][1]["spans"][0]["text"], "Texto")

    def test_qr_levels_default_module_and_alignment(self):
        for error, level in enumerate("LMQH"):
            qr = self.parse(b"\x1ba\x01Antes" + qr_command(b"https://example.com", error, 0))[0]["lines"][1]
            self.assertEqual((qr["align"], qr["module_size"], qr["error_level"]), ("center", 4, level))
            self.assertEqual(base64.b64decode(qr["data_base64"]), b"https://example.com")

    def test_qr_length_high_byte_and_following_text(self):
        payload = b"https://example.com/" + b"a" * 300
        printed = self.parse(qr_command(payload) + b"Depois\n")[0]
        self.assertEqual(printed["warnings"], [])
        self.assertEqual(base64.b64decode(printed["lines"][0]["data_base64"]), payload)
        self.assertEqual(printed["lines"][1]["spans"][0]["text"], "Depois")

    def test_invalid_qr_does_not_prevent_text(self):
        for packet in (qr_command(b""), qr_command(b"x", error=4)):
            printed = self.parse(packet + b"Texto\n")[0]
            self.assertEqual(printed["lines"][0]["spans"][0]["text"], "Texto")
            self.assertEqual(len(printed["warnings"]), 1)

    def test_non_rendered_binary_blocks_and_physical_commands(self):
        job = (b"\x1b(A\x04\x00\x01\x02\x01\x00\x1bv\x00\x1b\x80\x01"
               b"\x1b*\x21\x01\x00\x1b\x00\x0a\x1cp\x01\x00"
               b"\x1dk\x04ABC\x00\x1dk\x49\x03\x1b\x00\x0aTexto\n")
        printed = self.parse(job)[0]
        self.assertEqual(printed["lines"][0]["spans"][0]["text"], "Texto")
        self.assertEqual(len(printed["warnings"]), 3)

    def test_cut_preserves_printer_state_across_jobs(self):
        first, second = self.parse(b"\x1bEPrimeiro\n\x1bwSegundo\n\x1bm")
        self.assertTrue(second["lines"][0]["spans"][0]["bold"])
        self.assertEqual((first["reason"], second["reason"]), ("cut", "cut"))
        reset = self.parse(b"\x1bE\x1b@Normal\n")[0]
        self.assertFalse(reset["lines"][0]["spans"][0]["bold"])

    def test_incomplete_command_and_stray_gs(self):
        job = b"A\x1d\n\nB\n\x1dkQ\x01"
        printed = self.parse(job)[0]
        self.assertEqual(["".join(s["text"] for s in l["spans"]) for l in printed["lines"]], ["A", "", "B"])
        self.assertEqual(printed["warnings"], ["Comando incompleto ao encerrar a conexão."])
        self.assertEqual(base64.b64decode(printed["raw_base64"]), job)

    def test_status_does_not_create_jobs(self):
        self.assertEqual(self.parse(b"\x10\x04\x01\x1d\xf8\x31"), [])

    def test_drawer_events_fragmented_and_separated_by_cuts(self):
        first, second = self.parse(b"\x1bv\xc8Texto\n\x1bw\x1b\x80\x64\x1bm")
        self.assertEqual(first["events"], [dict(type="drawer", drawer=1, pulse_ms=200)])
        self.assertEqual(second["events"], [dict(type="drawer", drawer=2, pulse_ms=100)])
        self.assertEqual(first["lines"][0]["spans"][0]["text"], "Texto")
        self.assertEqual(first["warnings"], [])

    def test_list_version_changes_after_clear_with_same_number(self):
        with tempfile.TemporaryDirectory() as folder:
            history = History(Path(folder) / "history.sqlite3")
            self.assertEqual(history.version(), '"vazio"')
            history.save(self.parse(b"Primeiro\n")[0])
            first = history.version()
            self.assertEqual(history.version(), first)
            history.clear()
            history.save(self.parse(b"Outro\n")[0])
            self.assertTrue(history.version().startswith('"1-'))
            self.assertNotEqual(history.version(), first)

    def test_drawer_preview_and_binary_payload_keep_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            history = History(Path(folder) / "history.sqlite3")
            drawer = self.parse(b"\x1d\xf9\x20\x00\x1b2\x1bt\x02\x1bv\xc8")[0]
            binary = self.parse(qr_command(b"A\x1bv\xc8B"))[0]
            for printed in (drawer, binary):
                history.save(printed)
            self.assertEqual(history.list()[1]["preview"], "Abertura da gaveta 1 · pulso de 200 ms")
            self.assertEqual(history.get(1)["events"][0]["drawer"], 1)
            self.assertEqual(history.get(1)["lines"], [])
            self.assertEqual(history.get(2)["events"], [])
            with closing(sqlite3.connect(history.path)) as db:
                original = json.loads(db.execute("SELECT payload FROM jobs WHERE id=1").fetchone()[0])
            self.assertEqual(original, drawer)

    def test_history_keeps_state_after_cut_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.sqlite3"
            parser = Parser(History(path).save)
            parser.feed(b"\x1bEA\x1bwB\x1bm")
            parser.close()
            restored = History(path)
            self.assertEqual(len(restored.list()), 2)
            self.assertTrue(restored.get(2)["lines"][0]["spans"][0]["bold"])

    def test_second_instance_cannot_share_ports(self):
        for server_class, handler in ((PrinterServer, PrinterHandler), (WebServer, web_handler(None))):
            with self.subTest(server=server_class.__name__), server_class(("127.0.0.1", 0), handler) as first:
                with self.assertRaises(OSError):
                    server_class(first.server_address, handler).server_close()

    def test_tcp_http_history_and_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            history = History(Path(folder) / "history.sqlite3")
            with PrinterServer(("127.0.0.1", 0), PrinterHandler) as tcp:
                tcp.history = history
                with WebServer(("127.0.0.1", 0), web_handler(history)) as web:
                    threading.Thread(target=tcp.serve_forever, daemon=True).start()
                    threading.Thread(target=web.serve_forever, daemon=True).start()
                    try:
                        with socket.create_connection(tcp.server_address, timeout=3) as client:
                            client.sendall(b"Primeiro\n\x1bwSegundo\n")
                            client.shutdown(socket.SHUT_WR)
                            self.assertEqual(client.recv(1), b"")
                        self.assertEqual(len(History(Path(history.path)).list()), 2)
                        url = f"http://127.0.0.1:{web.server_port}"
                        with urlopen(url + "/api/jobs/1") as r:
                            self.assertEqual(json.load(r)["lines"][0]["spans"][0]["text"], "Primeiro")
                        with urlopen(url) as r:
                            page = r.read()
                            self.assertIn(f"EscBematech {VERSION} ·".encode(), page)
                            self.assertNotIn(b"{{VERSION}}", page)
                            self.assertEqual(r.headers["Server"].split()[0], f"EmuladorEscBematech/{VERSION}")
                        with urlopen(url + "/paper.js") as r:
                            self.assertIn(b"layoutPaper", r.read())
                        with urlopen(url + "/qrcode.js") as r:
                            self.assertIn(b"QR Code Generator", r.read())
                        with urlopen(url + "/api/jobs") as r:
                            tag = r.headers["ETag"]
                        with self.assertRaises(HTTPError) as unchanged:
                            urlopen(Request(url + "/api/jobs", headers={"If-None-Match": tag}))
                        self.assertEqual((unchanged.exception.code, unchanged.exception.read()), (304, b""))
                        unchanged.exception.close()
                        with self.assertRaises(HTTPError) as denied:
                            urlopen(Request(url + "/api/jobs", method="DELETE", headers={"Origin": "https://example.com"}))
                        self.assertEqual(denied.exception.code, 403)
                        denied.exception.close()
                        # Página com DNS rebinding: Origin e Host coincidem, mas o nome não é IP.
                        rebound = f"http://evil.example:{web.server_port}"
                        for method in ("GET", "DELETE"):
                            with self.subTest(method=method), self.assertRaises(HTTPError) as denied:
                                urlopen(Request(url + "/api/jobs", method=method,
                                                headers={"Host": rebound[7:], "Origin": rebound}))
                            self.assertEqual(denied.exception.code, 403)
                            denied.exception.close()
                        with urlopen(Request(url + "/api/jobs", headers={"Host": f"localhost:{web.server_port}"})) as r:
                            self.assertEqual(len(json.load(r)), 2)
                        self.assertEqual(len(history.list()), 2)
                        with urlopen(Request(url + "/api/jobs", method="DELETE")) as r:
                            self.assertEqual(json.load(r)["deleted"], 2)
                        self.assertEqual(history.list(), [])
                        self.assertIsNone(history.get(1))
                        with socket.create_connection(tcp.server_address, timeout=3) as client:
                            client.sendall(b"Novo\n\x1bw")
                            client.shutdown(socket.SHUT_WR)
                            self.assertEqual(client.recv(1), b"")
                        with urlopen(url + "/api/jobs") as r:
                            self.assertEqual(json.load(r)[0]["preview"], "Novo")
                    finally:
                        tcp.shutdown()
                        web.shutdown()


if __name__ == "__main__":
    unittest.main()
