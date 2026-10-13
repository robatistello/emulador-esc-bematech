import argparse
import socket


def qr_command(data, error=1, module=8):
    return b"\x1dkQ" + bytes([error, module, 0, 1]) + len(data).to_bytes(2, "little") + data


def build_demo(qr=False):
    job = (b"\x1d\xf9\x20\x00\x1b@\x1bt\x02\x1ba\x01\x1bE\x1bW\x01\x1bd\x01"
           + "CAFÉ EXEMPLO\n".encode("cp850")
           + b"\x1bW\x00\x1bd\x00\x1bFRua das Flores, 123\n\n\x1ba\x00"
           + "1 Café                                 R$  6,00\n2 Pães                                 R$  8,00\n".encode("cp850")
           + b"------------------------------------------------\n\x1bETOTAL                                  R$ 14,00\n\x1bF"
           + b"\n\x1ba\x01Obrigado pela visita!\n")
    if qr:
        job += qr_command(b"https://example.com/emulador-escbematech")
    return job + b"\n\n\n\x1bw"


def main():
    args = argparse.ArgumentParser(description="Envia uma impressão EscBematech de exemplo")
    args.add_argument("--host", default="127.0.0.1")
    args.add_argument("--port", type=int, default=9100)
    args.add_argument("--qr", action="store_true", help="Inclui QR code abaixo do texto")
    config = args.parse_args()
    with socket.create_connection((config.host, config.port), timeout=5) as connection:
        connection.sendall(build_demo(config.qr))
    print("Impressão de exemplo enviada. Consulte o histórico no navegador.")


if __name__ == "__main__":
    main()
