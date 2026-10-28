import socket
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from emulator import VERSION
from emulator.cli import main
from emulator.history import DEFAULT_KEEP, History
from emulator.servers import running_servers


def server_config(folder, port=0, web_port=0):
    return SimpleNamespace(
        host="127.0.0.1", port=port, web_port=web_port, db=Path(folder) / "history.sqlite3", keep=DEFAULT_KEEP
    )


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = folder.name

    def run_main(self, *argv):
        output = StringIO()
        errors = StringIO()

        with redirect_stdout(output), redirect_stderr(errors):
            try:
                code = main(list(argv))
            except SystemExit as exit:
                code = exit.code

        return code, output.getvalue(), errors.getvalue()

    def test_shutdown_saves_pending_job_and_releases_ports(self):
        config = server_config(self.folder)

        with running_servers(config) as (tcp, web):
            tcp_port = tcp.server_address[1]
            web_port = web.server_address[1]

            client = socket.create_connection(tcp.server_address, timeout=3)
            self.addCleanup(client.close)
            client.sendall(b"Impressao em andamento\n")

            # Uma abertura de gaveta só será salva quando o envio acabar.
            # O corte anterior confirma que o handler já recebeu os bytes.
            client.sendall(b"\x1bwPendente\n\x1bv\xc8")
            deadline = time.monotonic() + 3
            while not History(config.db).list() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(len(History(config.db).list()), 1)

            stopping_at = time.monotonic()

        self.assertLess(time.monotonic() - stopping_at, 3, "Sair demorou com conexão ativa")

        restored = History(config.db)
        self.assertEqual(len(restored.list()), 2)
        self.assertEqual(restored.get(2)["lines"][0]["spans"][0]["text"], "Pendente")
        self.assertEqual(restored.get(2)["events"][0]["pulse_ms"], 200)

        with running_servers(server_config(self.folder, tcp_port, web_port)):
            pass

    def test_web_bind_failure_releases_printer_port(self):
        with socket.socket() as occupied, socket.socket() as probe:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            probe.bind(("127.0.0.1", 0))
            printer_port = probe.getsockname()[1]
            probe.close()

            occupied_port = occupied.getsockname()[1]

            with self.assertRaises(OSError), running_servers(server_config(self.folder, printer_port, occupied_port)):
                self.fail("A porta HTTP ocupada deveria impedir a inicialização.")

        with socket.socket() as free:
            free.bind(("127.0.0.1", printer_port))

    def test_second_start_points_to_running_emulator(self):
        config = server_config(self.folder)

        with running_servers(config) as (tcp, web):
            code, output, _ = self.run_main(
                "--console",
                "--port",
                str(tcp.server_address[1]),
                "--web-port",
                str(web.server_port),
                "--db",
                str(config.db),
            )

        self.assertEqual(code, 0)
        self.assertIn(f"já está em execução. Histórico: http://127.0.0.1:{web.server_port}", output)

    def test_version_option(self):
        code, output, _ = self.run_main("--version")

        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), f"Emulador EscBematech {VERSION}")

    def test_port_used_by_other_program_names_the_port(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]

            code, _, errors = self.run_main(
                "--console", "--port", str(port), "--web-port", "0", "--db", str(Path(self.folder) / "history.sqlite3")
            )

        self.assertEqual(code, 2)
        self.assertIn(f"A porta {port} já está em uso por outro programa", errors)

    def test_invalid_port_and_unusable_database_are_reported(self):
        cases = (
            (["--port", "99999"], "porta inválida: 99999"),
            (["--web-port", "abc"], "porta inválida: abc"),
            (["--keep", "-1"], "limite inválido: -1"),
            (["--port", "0", "--web-port", "0", "--db", self.folder], "Não foi possível usar o histórico"),
        )

        for argv, message in cases:
            with self.subTest(argv=argv):
                code, _, errors = self.run_main("--console", *argv)

                self.assertEqual(code, 2)
                self.assertIn(message, errors)


if __name__ == "__main__":
    unittest.main()
