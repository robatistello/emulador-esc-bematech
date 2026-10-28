"""Funções comuns aos testes."""

from emulator.escpos import Parser


def parse(data):
    """Entrega os bytes um a um, como o pior caso de fragmentação TCP."""
    jobs = []
    parser = Parser(jobs.append)

    for byte in data:
        parser.feed(bytes([byte]))
    parser.close()

    return jobs


def line_text(line):
    return "".join(span["text"] for span in line["spans"])
