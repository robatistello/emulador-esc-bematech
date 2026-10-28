import ctypes
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

from emulator.history import DEFAULT_KEEP
from emulator.servers import running_servers


def wait_until(condition, seconds):
    deadline = time.monotonic() + seconds

    while not condition() and time.monotonic() < deadline:
        time.sleep(0.02)

    return condition()


@unittest.skipUnless(sys.platform == "win32", "Bandeja nativa do Windows")
@unittest.skipIf(os.environ.get("GITHUB_ACTIONS"), "GitHub Actions não tem área de trabalho interativa")
class TrayTests(unittest.TestCase):
    def setUp(self):
        from emulator.tray import api, shell32, user32

        class NotifyIconIdentifier(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("guidItem", ctypes.c_byte * 16),
            ]

        self.identifier_type = NotifyIconIdentifier
        self.find_window = api(user32, "FindWindowW", wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
        self.get_icon_rect = api(
            shell32,
            "Shell_NotifyIconGetRect",
            ctypes.c_long,
            ctypes.POINTER(NotifyIconIdentifier),
            ctypes.POINTER(wintypes.RECT),
        )
        self.thread_dpi_context = api(user32, "GetThreadDpiAwarenessContext", wintypes.HANDLE)
        self.dpi_awareness = api(user32, "GetAwarenessFromDpiAwarenessContext", ctypes.c_int, wintypes.HANDLE)

    def tray_window(self):
        from emulator.tray import CLASS_PREFIX

        return self.find_window(CLASS_PREFIX + str(os.getpid()), None)

    def icon_registered(self, hwnd):
        identifier = self.identifier_type(cbSize=ctypes.sizeof(self.identifier_type), hWnd=hwnd, uID=1)
        return self.get_icon_rect(ctypes.byref(identifier), ctypes.byref(wintypes.RECT())) == 0

    def test_native_icon_open_history_and_exit(self):
        from emulator.tray import EXIT, OPEN_HISTORY, WM_CLOSE, WM_COMMAND, PostMessage, run_tray

        opened_urls = []
        errors = []
        shared = {}
        ready = threading.Event()

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        config = SimpleNamespace(
            host="127.0.0.1", port=0, web_port=0, db=Path(folder.name) / "history.sqlite3", keep=DEFAULT_KEEP
        )

        def run_emulator():
            try:
                with running_servers(config) as (tcp, web):
                    shared.update(tcp=tcp, web=web, url=f"http://127.0.0.1:{web.server_port}")
                    ready.set()

                    run_tray(
                        shared["url"],
                        port=tcp.server_address[1],
                        open_browser=lambda url: opened_urls.append(url) or True,
                    )
            # Qualquer erro da bandeja precisa chegar ao teste, que espera em outra thread.
            except Exception as error:  # noqa: BLE001
                errors.append(error)
                ready.set()

        thread = threading.Thread(target=run_emulator, daemon=True)
        thread.start()

        self.assertTrue(ready.wait(5))
        self.assertTrue(wait_until(lambda: self.tray_window() and self.icon_registered(self.tray_window()), 5))
        self.assertEqual(errors, [])

        hwnd = self.tray_window()
        self.addCleanup(lambda: thread.is_alive() and PostMessage(hwnd, WM_CLOSE, 0, 0) and thread.join(5))

        with urlopen(shared["url"], timeout=3) as response:
            self.assertEqual(response.status, 200)

        # 2 é o modo por monitor: ícone e menu desenhados na escala real da tela.
        self.assertEqual(self.dpi_awareness(self.thread_dpi_context()), 2)

        self.assertTrue(PostMessage(hwnd, WM_COMMAND, OPEN_HISTORY, 0))
        self.assertTrue(wait_until(lambda: opened_urls, 3))
        self.assertEqual(opened_urls, [shared["url"]])

        self.assertTrue(PostMessage(hwnd, WM_COMMAND, EXIT, 0))
        thread.join(5)

        self.assertFalse(thread.is_alive(), "Sair não encerrou os servidores")
        self.assertEqual(errors, [])
        self.assertFalse(self.tray_window())
        self.assertFalse(self.icon_registered(hwnd))

        for address in (shared["tcp"].server_address, shared["web"].server_address):
            with socket.socket() as probe:
                probe.bind(address)


if __name__ == "__main__":
    unittest.main()
