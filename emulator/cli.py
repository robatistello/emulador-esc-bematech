"""Linha de comando: opções, inicialização dos servidores e mensagens de erro."""

import argparse
import logging
import sqlite3
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from emulator import VERSION
from emulator.history import DEFAULT_KEEP
from emulator.logs import configure_logging
from emulator.servers import SERVER_NAME, PortInUseError, running_servers

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
# Pelos fontes, a pasta acima do pacote é a raiz do projeto; no executável, é a
# pasta temporária onde o PyInstaller extrai os recursos, com a mesma disposição.
NOTICES_PATH = PACKAGE_DIR.parent / "THIRD-PARTY-NOTICES.txt"
# Os recursos do .exe ficam em uma pasta temporária; o histórico precisa
# permanecer ao lado do executável para sobreviver a cada nova execução.
DATA_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PACKAGE_DIR.parent


def running_emulator(url):
    try:
        with urlopen(url, timeout=2) as response:
            return response.headers.get("Server", "").startswith(SERVER_NAME)
    except OSError:
        return False


def port_number(value):
    port = int(value) if value.isdigit() else -1

    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"porta inválida: {value} (use um número de 0 a 65535)")

    return port


def job_limit(value):
    if not value.isdigit():
        raise argparse.ArgumentTypeError(f"limite inválido: {value} (use um número; 0 guarda todas as impressões)")

    return int(value)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        if sys.stderr is None and sys.platform == "win32":
            from emulator.tray import show_error

            show_error(f"{message}\n\nUse --help para ver as opções.")
            raise SystemExit(2)

        super().error(message)


def build_argument_parser():
    parser = ArgumentParser(description="Emulador EscBematech com histórico persistente", add_help=False)

    parser.add_argument("-h", "--help", action="help", help="Mostra esta ajuda e sai")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Endereço de escuta; 0.0.0.0 aceita outros computadores (padrão: 127.0.0.1)"
    )
    parser.add_argument("--port", type=port_number, default=9100, help="Porta da impressora (padrão: 9100)")
    parser.add_argument(
        "--web-port", type=port_number, default=9101, help="Porta do histórico no navegador (padrão: 9101)"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DATA_ROOT / "data" / "history.sqlite3",
        help="Arquivo do histórico (padrão: data/history.sqlite3 ao lado do programa)",
    )
    parser.add_argument(
        "--keep",
        type=job_limit,
        default=DEFAULT_KEEP,
        help=f"Quantas impressões guardar; as mais antigas são apagadas, e 0 guarda todas (padrão: {DEFAULT_KEEP})",
    )
    parser.add_argument(
        "--version", action="version", version=f"Emulador EscBematech {VERSION}", help="Mostra a versão e sai"
    )
    parser.add_argument("--licenses", action="store_true", help="Exibe licenças das bibliotecas incluídas")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tray", dest="tray", action="store_true", help="Executa na bandeja do Windows")
    mode.add_argument("--console", dest="tray", action="store_false", help="Executa no terminal")
    parser.set_defaults(tray=getattr(sys, "frozen", False) and sys.platform == "win32")

    return parser


def needs_console(argv):
    console_flags = ("--console", "--licenses", "--version", "--help", "-h")
    return sys.platform == "win32" and sys.stdout is None and any(flag in argv for flag in console_flags)


def serve(config, browser_host):
    if config.tray and sys.platform != "win32":
        raise RuntimeError("O modo bandeja está disponível apenas no Windows.")

    with running_servers(config) as (tcp, web):
        url = f"http://{browser_host}:{web.server_port}"
        logger.info(
            "Emulador %s iniciado: impressora em %s:%s, histórico em %s, banco em %s.",
            VERSION,
            config.host,
            tcp.server_address[1],
            url,
            config.db.resolve(),
        )

        try:
            if config.tray:
                from emulator.tray import run_tray

                run_tray(url, port=tcp.server_address[1])
                return

            print(f"Impressora: {config.host}:{tcp.server_address[1]}")
            print(f"Histórico: {url}")
            print("Protocolo: EscBematech — 48 colunas")
            print(f"Banco: {config.db.resolve()} — Ctrl+C para sair", flush=True)
            threading.Event().wait()
        finally:
            logger.info("Encerrando o emulador.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    if needs_console(argv):
        from emulator.tray import ensure_console

        # O terminal não espera um programa de janela: o emulador ficaria rodando
        # escondido e sem receber Ctrl+C. Ele ganha uma janela própria.
        ensure_console(own_window="--console" in argv)

    parser = build_argument_parser()
    config = parser.parse_args(argv)

    if config.licenses:
        print(NOTICES_PATH.read_text(encoding="utf-8"))
        return 0

    try:
        configure_logging(config.db.parent if config.tray else None)
    except OSError:
        # Sem permissão de escrita na pasta, o erro aparece ao abrir o histórico logo abaixo.
        configure_logging(None)

    def fail(message):
        logger.error(message)

        if config.tray and sys.platform == "win32":
            from emulator.tray import show_error

            show_error(message)
            return 1

        parser.error(message)

    browser_host = "127.0.0.1" if config.host == "0.0.0.0" else config.host

    try:
        serve(config, browser_host)
    except KeyboardInterrupt:
        pass
    except PortInUseError as error:
        url = f"http://{browser_host}:{config.web_port}"
        if not running_emulator(url):
            return fail(str(error))

        logger.info("Já havia um emulador em execução; abrindo o histórico dele em %s.", url)
        if config.tray:
            webbrowser.open(url)
        else:
            print(f"O emulador já está em execução. Histórico: {url}")
    except sqlite3.Error as error:
        return fail(
            f"Não foi possível usar o histórico em {config.db.resolve()}: {error}. Escolha outro arquivo com --db."
        )
    except (OSError, RuntimeError) as error:
        return fail(str(error))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
