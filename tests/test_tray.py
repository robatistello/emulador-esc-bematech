import ctypes
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from ctypes import wintypes as w
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from urllib.request import urlopen
from server import VERSION, History, main, running_servers


class LifecycleTests(unittest.TestCase):
    def test_shutdown_saves_pending_job_and_releases_ports(self):
        with tempfile.TemporaryDirectory() as folder:
            config = SimpleNamespace(host="127.0.0.1", port=0, web_port=0, db=Path(folder) / "history.sqlite3")
            client = None
            try:
                with running_servers(config) as (tcp, web):
                    tcp_address = tcp.server_address
                    web_address = web.server_address
                    client = socket.create_connection(tcp_address, timeout=3)
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
                reopened = SimpleNamespace(host="127.0.0.1", port=tcp_address[1], web_port=web_address[1], db=config.db)
                with running_servers(reopened):
                    pass
            finally:
                if client:
                    client.close()

    def test_web_bind_failure_releases_printer_port(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as occupied, socket.socket() as probe:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            probe.bind(("127.0.0.1", 0))
            printer_address = probe.getsockname()
            probe.close()
            config = SimpleNamespace(
                host="127.0.0.1",
                port=printer_address[1],
                web_port=occupied.getsockname()[1],
                db=Path(folder) / "history.sqlite3",
            )
            with self.assertRaises(OSError):
                with running_servers(config):
                    self.fail("A porta HTTP ocupada deveria impedir a inicialização.")
            with socket.socket() as free:
                free.bind(printer_address)

    def test_second_start_points_to_running_emulator(self):
        with tempfile.TemporaryDirectory() as folder:
            config = SimpleNamespace(host="127.0.0.1", port=0, web_port=0, db=Path(folder) / "history.sqlite3")
            with running_servers(config) as (tcp, web):
                output = StringIO()
                with redirect_stdout(output):
                    code = main(
                        [
                            "--console",
                            "--port",
                            str(tcp.server_address[1]),
                            "--web-port",
                            str(web.server_port),
                            "--db",
                            str(config.db),
                        ]
                    )
                self.assertEqual(code, 0)
                self.assertIn(f"já está em execução. Histórico: http://127.0.0.1:{web.server_port}", output.getvalue())

    def test_version_option(self):
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exit:
            main(["--version"])
        self.assertEqual(exit.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"Emulador EscBematech {VERSION}")

    def test_port_used_by_other_program_names_the_port(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            errors = StringIO()
            with redirect_stderr(errors), self.assertRaises(SystemExit):
                main(
                    ["--console", "--port", str(port), "--web-port", "0", "--db", str(Path(folder) / "history.sqlite3")]
                )
            self.assertIn(f"A porta {port} já está em uso por outro programa", errors.getvalue())

    def test_invalid_port_and_unusable_database_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            for argv, message in (
                (["--port", "99999"], "porta inválida: 99999"),
                (["--web-port", "abc"], "porta inválida: abc"),
                (["--port", "0", "--web-port", "0", "--db", folder], "Não foi possível usar o histórico"),
            ):
                with self.subTest(argv=argv):
                    errors = StringIO()
                    with redirect_stderr(errors), self.assertRaises(SystemExit) as exit:
                        main(["--console", *argv])
                    self.assertEqual(exit.exception.code, 2)
                    self.assertIn(message, errors.getvalue())


@unittest.skipUnless(sys.platform == "win32", "Bandeja nativa do Windows")
@unittest.skipIf(os.environ.get("GITHUB_ACTIONS"), "GitHub Actions não tem área de trabalho interativa")
class TrayTests(unittest.TestCase):
    def test_native_icon_open_history_and_exit(self):
        from tray import run_tray, api, user32, shell32, CLASS_PREFIX, WM_COMMAND, OPEN_HISTORY, EXIT, PostMessage

        find_window = api(user32, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)

        class Identifier(ctypes.Structure):
            _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("guidItem", ctypes.c_byte * 16)]

        get_rect = api(
            shell32, "Shell_NotifyIconGetRect", ctypes.c_long, ctypes.POINTER(Identifier), ctypes.POINTER(w.RECT)
        )
        opened, errors = [], []
        with tempfile.TemporaryDirectory() as folder:
            config = SimpleNamespace(host="127.0.0.1", port=0, web_port=0, db=Path(folder) / "history.sqlite3")
            shared, ready = {}, threading.Event()

            def worker():
                try:
                    with running_servers(config) as (tcp, web):
                        shared.update(tcp=tcp, web=web, url=f"http://127.0.0.1:{web.server_port}")
                        ready.set()
                        run_tray(
                            shared["url"],
                            port=tcp.server_address[1],
                            open_browser=lambda url: opened.append(url) or True,
                        )
                except Exception as error:
                    errors.append(error)
                    ready.set()

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            hwnd = None
            try:
                self.assertTrue(ready.wait(5))
                deadline = time.monotonic() + 5
                while thread.is_alive() and time.monotonic() < deadline:
                    hwnd = find_window(CLASS_PREFIX + str(os.getpid()), None)
                    if hwnd:
                        identifier = Identifier(cbSize=ctypes.sizeof(Identifier), hWnd=hwnd, uID=1)
                        if get_rect(ctypes.byref(identifier), ctypes.byref(w.RECT())) == 0:
                            break
                    time.sleep(0.02)
                self.assertEqual(errors, [])
                self.assertTrue(hwnd, "Janela do ícone não encontrada")
                self.assertEqual(
                    get_rect(ctypes.byref(identifier), ctypes.byref(w.RECT())), 0, "Ícone não registrado na bandeja"
                )
                with urlopen(shared["url"], timeout=3) as response:
                    self.assertEqual(response.status, 200)
                # Ícone e menu renderizados na escala real da tela.
                context = api(user32, "GetThreadDpiAwarenessContext", w.HANDLE)
                awareness = api(user32, "GetAwarenessFromDpiAwarenessContext", ctypes.c_int, w.HANDLE)
                self.assertEqual(awareness(context()), 2)
                self.assertTrue(PostMessage(hwnd, WM_COMMAND, OPEN_HISTORY, 0))
                deadline = time.monotonic() + 3
                while not opened and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertEqual(opened, [shared["url"]])
                self.assertTrue(PostMessage(hwnd, WM_COMMAND, EXIT, 0))
                thread.join(5)
                self.assertFalse(thread.is_alive(), "Sair não encerrou os servidores")
                self.assertEqual(errors, [])
                self.assertFalse(find_window(CLASS_PREFIX + str(os.getpid()), None))
                self.assertNotEqual(get_rect(ctypes.byref(identifier), ctypes.byref(w.RECT())), 0)
                for address in (shared["tcp"].server_address, shared["web"].server_address):
                    with socket.socket() as probe:
                        probe.bind(address)
            finally:
                if hwnd and thread.is_alive():
                    PostMessage(hwnd, 0x10, 0, 0)
                    thread.join(5)


if __name__ == "__main__":
    unittest.main()
