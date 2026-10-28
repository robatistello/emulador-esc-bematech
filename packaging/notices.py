"""Monta o THIRD-PARTY-NOTICES.txt dos executáveis: o aviso do projeto mais as licenças do Python embutido."""

import argparse
import sys
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGING_DIR.parent
LICENSES_DIR = PACKAGING_DIR / "licenses"

# O LICENSE.txt do Python para Windows já traz o próprio Python, as condições da
# Microsoft, bzip2, libffi, zstd e OpenSSL; faltam as bibliotecas abaixo, que
# também ficam dentro da python314.dll e dos módulos empacotados.
WINDOWS_EXTRA = (
    ("mpdecimal", "mpdecimal.txt"),
    ("zlib-ng", "zlib-ng.txt"),
    ("liblzma (XZ Utils)", "liblzma.txt"),
    ("SQLite", "sqlite.txt"),
)

# Bibliotecas que o python-build-standalone liga dentro da libpython usada no build Linux.
LINUX_COMPONENTS = (
    ("CPython", "cpython.txt"),
    ("OpenSSL 3", "openssl-3.txt"),
    ("SQLite", "sqlite.txt"),
    ("libffi", "libffi.txt"),
    ("mpdecimal", "mpdecimal.txt"),
    ("bzip2", "bzip2.txt"),
    ("liblzma (XZ Utils)", "liblzma.txt"),
    ("zlib", "zlib.txt"),
    ("zlib-ng", "zlib-ng.txt"),
    ("Zstandard", "zstd.txt"),
    ("libedit", "libedit.txt"),
    ("ncurses", "ncurses.txt"),
    ("libuuid", "libuuid.txt"),
    ("Expat", "expat.txt"),
)

INTRODUCTION = (
    "O executável inclui o interpretador Python e as bibliotecas nativas que ele usa,\n"
    "empacotados pelo PyInstaller. Seguem as licenças desses componentes."
)

PYINSTALLER_NOTE = (
    "O executável foi gerado com o PyInstaller (https://pyinstaller.org). O carregador\n"
    "que o PyInstaller embute é distribuído sob a GPL 2.0 com uma exceção que permite\n"
    "usá-lo em programas sob qualquer licença."
)


def section(title, text):
    rule = "=" * 72
    return f"{rule}\n{title}\n{rule}\n\n{text.strip()}\n"


def license_text(file_name):
    return (LICENSES_DIR / file_name).read_text(encoding="utf-8")


def windows_sections():
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        raise SystemExit(f"Licença do Python não encontrada em {python_license}.")

    sections = [section("Python e bibliotecas da build Windows", python_license.read_text(encoding="utf-8"))]
    sections += [section(title, license_text(file_name)) for title, file_name in WINDOWS_EXTRA]
    return sections


def linux_sections():
    return [section(title, license_text(file_name)) for title, file_name in LINUX_COMPONENTS]


def main():
    parser = argparse.ArgumentParser(description="Monta os avisos de licença de um executável")
    parser.add_argument("platform", choices=("windows", "linux"))
    parser.add_argument("output", type=Path)
    config = parser.parse_args()

    project_notices = (PROJECT_ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8").strip()
    sections = windows_sections() if config.platform == "windows" else linux_sections()

    parts = [project_notices, INTRODUCTION, *sections, PYINSTALLER_NOTE]
    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.output.write_text("\n\n\n".join(part.strip() for part in parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
