"""Subconjunto do protocolo EscBematech, com pacotes TCP fragmentados."""

import base64
import re
from datetime import datetime, timezone

TEXT = re.compile(rb"[^\x00-\x1f]+")
ESC, GS, FS, DLE = 0x1B, 0x1D, 0x1C, 0x10
CODE_PAGES = {2: "cp850", 3: "cp437", 4: "cp860", 8: "utf-8"}


class Parser:
    def __init__(self, save):
        self.save = save
        self.pending = bytearray()
        self.raw = bytearray()
        self.text = bytearray()
        self.lines = []
        self.spans = []
        self.events = []
        self.warnings = set()
        self.reset_style()

    def reset_style(self):
        self.bold = False
        self.italic = False
        self.underline = False
        self.align = "left"
        self.font = "A"
        self.width = 1
        self.height = 1
        self.line_spacing = 30
        self.encoding = "cp850"

    def print_qr(self, packet):
        error, module, version, encoding = packet[3:7]
        data = packet[9:]

        if error > 3 or version != 0 or encoding > 2 or not data:
            self.warnings.add("QR code com parâmetros não suportados ou conteúdo vazio.")
            return

        if self.spans or self.text:
            self.newline()

        self.lines.append(
            dict(
                type="qr",
                align=self.align,
                spans=[],
                module_size=module or 4,
                error_level="LMQH"[error],
                data_base64=base64.b64encode(data).decode("ascii"),
            )
        )

    def flush_text(self):
        if not self.text:
            return

        self.spans.append(
            dict(
                text=self.text.decode(self.encoding, errors="replace"),
                bold=self.bold,
                italic=self.italic,
                underline=self.underline,
                width=self.width,
                height=self.height,
                font=self.font,
            )
        )
        self.text.clear()

    def newline(self):
        self.flush_text()
        self.lines.append(dict(align=self.align, spans=self.spans, spacing=self.line_spacing))
        self.spans = []

    def has_content(self):
        if self.events or self.warnings:
            return True

        return any(
            line.get("type") == "qr" or any(span["text"].strip() for span in line["spans"]) for line in self.lines
        )

    def finish(self, reason="disconnect"):
        self.flush_text()
        if self.spans:
            self.newline()

        # Sistemas costumam mandar inicialização ou avanço de papel logo depois do
        # corte; sem texto, QR, gaveta ou aviso, isso não é uma nova impressão.
        if self.has_content():
            self.save(
                dict(
                    protocol="bematech",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    reason=reason,
                    lines=self.lines,
                    events=self.events,
                    warnings=sorted(self.warnings),
                    raw_base64=base64.b64encode(self.raw).decode("ascii"),
                )
            )

        self.raw.clear()
        self.lines = []
        self.spans = []
        self.events = []
        self.warnings.clear()

    def packet_size(self):
        """None significa que ainda faltam bytes; blocos binários são atômicos."""
        pending = self.pending

        if pending[0] not in (ESC, GS, FS, DLE):
            return 1
        if len(pending) < 2:
            return None

        prefix, command = pending[:2]

        if prefix == ESC:
            if command == 0x28:  # ESC ( A: beep, comprimento little endian.
                return None if len(pending) < 5 else 5 + int.from_bytes(pending[3:5], "little")
            if command == 0x2A:  # ESC *: imagem em colunas.
                if len(pending) < 5:
                    return None
                return 5 + int.from_bytes(pending[3:5], "little") * (3 if pending[2] in (32, 33) else 1)
            return 3 if command in (0x21, 0x2D, 0x33, 0x57, 0x61, 0x64, 0x74, 0x76, 0x80) else 2

        if prefix == GS:
            if command in (0x0A, 0x0D):
                return 1  # GS solto: preservar a quebra seguinte.
            if command == 0x6B:
                if len(pending) < 3:
                    return None
                if pending[2] == 0x51:  # QR nativo: GS k Q n1 n2 n3 n4 n5 n6 dados.
                    return None if len(pending) < 9 else 9 + int.from_bytes(pending[7:9], "little")
                if pending[2] <= 6:
                    try:
                        return pending.index(0, 3) + 1
                    except ValueError:
                        return None
                return None if len(pending) < 4 else 4 + pending[3]
            return {0xF9: 4, 0xF8: 3, 0x48: 3, 0x68: 3, 0x77: 3, 0x66: 3}.get(command, 2)

        if prefix == FS:
            return 4 if command == 0x70 else 2

        return 3

    def feed(self, data):
        self.pending.extend(data)

        while self.pending:
            text = TEXT.match(self.pending)
            if text:
                run = self.pending[: text.end()]
                del self.pending[: text.end()]
                self.raw.extend(run)
                self.text.extend(run)
                continue

            size = self.packet_size()
            if size is None or len(self.pending) < size:
                return

            packet = bytes(self.pending[:size])
            del self.pending[:size]

            # Consultas de status não constituem uma impressão.
            if packet[:2] in (b"\x10\x04", b"\x1d\xf8"):
                continue

            self.raw.extend(packet)
            self.handle_packet(packet)

    def handle_packet(self, packet):
        control = packet[0]

        if control == 0x0A:
            self.newline()
        elif control == 0x0D:
            pass
        elif control == 0x09:
            self.text.extend(b"    ")
        elif control == ESC:
            self.flush_text()
            self.handle_esc(packet)
        elif control == GS:
            if len(packet) > 1:
                self.flush_text()
                self.handle_gs(packet)
        elif control == FS:
            self.flush_text()
            if packet[1] == 0x70:
                self.warnings.add("Logo FS não renderizado.")
            else:
                self.warnings.add(f"Comando FS {packet[1]:02X} não suportado.")
        else:
            self.warnings.add(f"Controle {control:02X} não suportado.")

    def handle_esc(self, packet):
        command = packet[1]
        argument = packet[2] if len(packet) > 2 else 0

        if command == 0x40:
            self.reset_style()
        elif command == 0x32:
            self.line_spacing = 30
        elif command == 0x33:
            self.line_spacing = argument
        elif command in (0x45, 0x46):
            self.bold = command == 0x45
        elif command in (0x34, 0x35):
            self.italic = command == 0x34
        elif command in (0x0F, 0x48):
            self.font = "B" if command == 0x0F else "A"
        elif command == 0x57:
            self.width = 2 if argument else 1
        elif command == 0x64:
            self.height = 2 if argument else 1
        elif command == 0x61:
            self.align = {0: "left", 1: "center", 2: "right"}.get(argument, "left")
        elif command == 0x21:
            self.bold = bool(argument & 8)
            self.underline = bool(argument & 128)
            self.width = 2 if argument & 32 else 1
            self.height = 2 if argument & 16 else 1
            self.font = "B" if argument & 1 else "A"
        elif command == 0x2D:
            self.underline = bool(argument)
        elif command in (0x77, 0x6D):
            self.finish("cut")
        elif command == 0x74:
            self.encoding = CODE_PAGES.get(argument, "cp850")
            if argument not in CODE_PAGES:
                self.warnings.add(f"Página de código {argument} não suportada; usado CP850.")
        elif command in (0x76, 0x80):
            self.events.append(dict(type="drawer", drawer=1 if command == 0x76 else 2, pulse_ms=argument))
        elif command == 0x28 and packet[2] == 0x41:
            pass  # Beep: sem dispositivo físico.
        elif command == 0x2A:
            self.warnings.add("Imagem ESC * não renderizada.")
        else:
            self.warnings.add(f"Comando ESC {command:02X} não suportado.")

    def handle_gs(self, packet):
        command = packet[1]

        if packet[:3] == b"\x1dkQ":
            self.print_qr(packet)
        elif packet == b"\x1d\xf9\x20\x00" or command in (0x48, 0x68, 0x77, 0x66):
            pass  # Seleção EscBema e parâmetros de código de barras.
        elif command == 0x6B:
            self.warnings.add("Código de barras não renderizado.")
        else:
            self.warnings.add(f"Comando GS {command:02X} não suportado.")

    def close(self, reason="disconnect"):
        if self.pending:
            self.raw.extend(self.pending)
            self.pending.clear()
            self.warnings.add("Comando incompleto ao encerrar a conexão.")

        self.finish(reason)
