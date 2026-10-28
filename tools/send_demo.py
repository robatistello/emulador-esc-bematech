"""Envia uma impressão EscBematech de exemplo, sem precisar de um sistema emissor."""

import argparse
import socket

SELECT_ESCBEMA = b"\x1d\xf9\x20\x00"
INITIALIZE = b"\x1b@"
CODE_PAGE_850 = b"\x1bt\x02"
ALIGN_LEFT = b"\x1ba\x00"
ALIGN_CENTER = b"\x1ba\x01"
BOLD_ON = b"\x1bE"
BOLD_OFF = b"\x1bF"
DOUBLE_SIZE_ON = b"\x1bW\x01\x1bd\x01"
DOUBLE_SIZE_OFF = b"\x1bW\x00\x1bd\x00"
CUT = b"\x1bw"


def qr_command(data, error=1, module=8):
    return b"\x1dkQ" + bytes([error, module, 0, 1]) + len(data).to_bytes(2, "little") + data


def text(value):
    return value.encode("cp850")


def build_demo(qr=False):
    parts = [
        SELECT_ESCBEMA,
        INITIALIZE,
        CODE_PAGE_850,
        ALIGN_CENTER,
        BOLD_ON,
        DOUBLE_SIZE_ON,
        text("CAFÉ EXEMPLO\n"),
        DOUBLE_SIZE_OFF,
        BOLD_OFF,
        text("Rua das Flores, 123\n\n"),
        ALIGN_LEFT,
        text("1 Café                                 R$  6,00\n"),
        text("2 Pães                                 R$  8,00\n"),
        text("-" * 48 + "\n"),
        BOLD_ON,
        text("TOTAL                                  R$ 14,00\n"),
        BOLD_OFF,
        text("\n"),
        ALIGN_CENTER,
        text("Obrigado pela visita!\n"),
    ]

    if qr:
        parts.append(qr_command(b"https://example.com/emulador-escbematech"))

    parts.append(b"\n\n\n" + CUT)
    return b"".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Envia uma impressão EscBematech de exemplo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--qr", action="store_true", help="Inclui QR code abaixo do texto")
    config = parser.parse_args()

    with socket.create_connection((config.host, config.port), timeout=5) as connection:
        connection.sendall(build_demo(config.qr))

    print("Impressão de exemplo enviada. Consulte o histórico no navegador.")


if __name__ == "__main__":
    main()
