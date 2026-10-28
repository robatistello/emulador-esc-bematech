import base64
import unittest

from emulator.escpos import Parser
from support import line_text, parse
from tools.send_demo import build_demo, qr_command


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


if __name__ == "__main__":
    unittest.main()
