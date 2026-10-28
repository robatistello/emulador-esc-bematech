"""Abre o executável compilado, envia a impressão de exemplo e confere o histórico."""

import argparse
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from send_demo import build_demo

ROOT = Path(__file__).resolve().parent.parent
STATIC_FILES = (
    "/style.css",
    "/app.js",
    "/paper.js",
    "/qrcode.js",
    "/fonts/roboto.woff2",
    "/fonts/roboto-mono.woff2",
)


def source_version():
    source = (ROOT / "emulator" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^VERSION = "(.+)"$', source, re.MULTILINE).group(1)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fetch(url):
    with urlopen(url, timeout=5) as response:
        return response.read()


def wait_for(check, seconds, message):
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except OSError:
            pass
        time.sleep(0.5)

    raise SystemExit(message)


def stop(process):
    if sys.platform == "win32":
        # O .exe de arquivo único é um lançador que abre o Python como processo
        # filho; encerrar só o lançador deixaria o filho com as portas abertas.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()

    process.wait(timeout=10)


def check_version(executable, expected):
    # Com a saída redirecionada, o .exe sem console recebe stdout e não abre janela própria.
    output = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=60).stdout

    if expected not in output:
        raise SystemExit(f"--version mostrou {output.strip()!r}; esperado {expected}.")


def check_printing(executable):
    port = free_port()
    web_port = free_port()
    url = f"http://127.0.0.1:{web_port}"

    with tempfile.TemporaryDirectory() as folder:
        arguments = ["--console", "--port", str(port), "--web-port", str(web_port)]
        process = subprocess.Popen(
            [executable, *arguments, "--db", str(Path(folder) / "history.sqlite3")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            wait_for(lambda: fetch(url + "/"), 60, "O histórico não respondeu.")
            for path in STATIC_FILES:
                fetch(url + path)

            with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
                connection.sendall(build_demo(qr=True))

            jobs = wait_for(lambda: json.loads(fetch(url + "/api/jobs")), 10, "A impressão não chegou ao histórico.")
            if "CAFÉ EXEMPLO" not in jobs[0]["preview"]:
                raise SystemExit(f"Prévia inesperada: {jobs[0]['preview']!r}")
        finally:
            stop(process)


def main():
    parser = argparse.ArgumentParser(description="Teste rápido do executável compilado")
    parser.add_argument("executable", type=Path)
    executable = parser.parse_args().executable.resolve()
    version = source_version()

    check_version(executable, version)
    check_printing(executable)

    print(f"OK: {executable.name} {version} recebeu a impressão de exemplo.")


if __name__ == "__main__":
    main()
