"""Subconjunto do protocolo EscBematech, com pacotes TCP fragmentados."""

import base64
import re
from datetime import UTC, datetime

TEXT = re.compile(rb"[^\x00-\x1f]+")

TAB = 0x09
LF = 0x0A
CR = 0x0D
DLE = 0x10
ESC = 0x1B
FS = 0x1C
GS = 0x1D

# Segundo byte dos comandos ESC, com o mnemônico do manual.
ESC_CONDENSED_ON = 0x0F  # ESC SI
ESC_PRINT_MODE = 0x21  # ESC !
ESC_BEEP = 0x28  # ESC ( A
ESC_IMAGE = 0x2A  # ESC *
ESC_UNDERLINE = 0x2D  # ESC -
ESC_DEFAULT_SPACING = 0x32  # ESC 2
ESC_LINE_SPACING = 0x33  # ESC 3
ESC_ITALIC_ON = 0x34  # ESC 4
ESC_ITALIC_OFF = 0x35  # ESC 5
ESC_INITIALIZE = 0x40  # ESC @
ESC_BOLD_ON = 0x45  # ESC E
ESC_BOLD_OFF = 0x46  # ESC F
ESC_CONDENSED_OFF = 0x48  # ESC H
ESC_DOUBLE_WIDTH = 0x57  # ESC W
ESC_ALIGN = 0x61  # ESC a
ESC_DOUBLE_HEIGHT = 0x64  # ESC d
ESC_PARTIAL_CUT = 0x6D  # ESC m
ESC_CODE_PAGE = 0x74  # ESC t
ESC_DRAWER_1 = 0x76  # ESC v
ESC_FULL_CUT = 0x77  # ESC w
ESC_DRAWER_2 = 0x80
ESC_WITH_ARGUMENT = (
    ESC_PRINT_MODE,
    ESC_UNDERLINE,
    ESC_LINE_SPACING,
    ESC_DOUBLE_WIDTH,
    ESC_ALIGN,
    ESC_DOUBLE_HEIGHT,
    ESC_CODE_PAGE,
    ESC_DRAWER_1,
    ESC_DRAWER_2,
)

# Bits do argumento de ESC !.
PRINT_MODE_CONDENSED = 0x01
PRINT_MODE_BOLD = 0x08
PRINT_MODE_DOUBLE_HEIGHT = 0x10
PRINT_MODE_DOUBLE_WIDTH = 0x20
PRINT_MODE_UNDERLINE = 0x80

# Segundo byte dos comandos GS.
GS_BARCODE_HEIGHT = 0x68  # GS h
GS_BARCODE_WIDTH = 0x77  # GS w
GS_BARCODE_TEXT = 0x48  # GS H
GS_BARCODE_FONT = 0x66  # GS f
GS_BARCODE = 0x6B  # GS k
GS_STATUS = 0xF8
GS_SELECT_MODE = 0xF9
GS_BARCODE_SETTINGS = (GS_BARCODE_HEIGHT, GS_BARCODE_WIDTH, GS_BARCODE_TEXT, GS_BARCODE_FONT)
GS_COMMAND_SIZES = {GS_SELECT_MODE: 4, GS_STATUS: 3, **{command: 3 for command in GS_BARCODE_SETTINGS}}
QR_SYMBOLOGY = 0x51  # GS k Q

FS_LOGO = 0x70  # FS p

SELECT_ESCBEMA = b"\x1d\xf9\x20\x00"
STATUS_QUERIES = (bytes([DLE, 0x04]), bytes([GS, GS_STATUS]))
CODE_PAGES = {2: "cp850", 3: "cp437", 4: "cp860", 8: "utf-8"}
ALIGNMENTS = {0: "left", 1: "center", 2: "right"}


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
            {
                "type": "qr",
                "align": self.align,
                "spans": [],
                "module_size": module or 4,
                "error_level": "LMQH"[error],
                "data_base64": base64.b64encode(data).decode("ascii"),
            }
        )

    def flush_text(self):
        if not self.text:
            return

        self.spans.append(
            {
                "text": self.text.decode(self.encoding, errors="replace"),
                "bold": self.bold,
                "italic": self.italic,
                "underline": self.underline,
                "width": self.width,
                "height": self.height,
                "font": self.font,
            }
        )
        self.text.clear()

    def newline(self):
        self.flush_text()
        self.lines.append({"align": self.align, "spans": self.spans, "spacing": self.line_spacing})
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
                {
                    "protocol": "bematech",
                    "created_at": datetime.now(UTC).isoformat(),
                    "reason": reason,
                    "lines": self.lines,
                    "events": self.events,
                    "warnings": sorted(self.warnings),
                    "raw_base64": base64.b64encode(self.raw).decode("ascii"),
                }
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
            if command == ESC_BEEP:  # Comprimento little endian nos bytes 3 e 4.
                return None if len(pending) < 5 else 5 + int.from_bytes(pending[3:5], "little")
            if command == ESC_IMAGE:  # Colunas de 1 ou 3 bytes, conforme a densidade.
                if len(pending) < 5:
                    return None
                return 5 + int.from_bytes(pending[3:5], "little") * (3 if pending[2] in (32, 33) else 1)
            return 3 if command in ESC_WITH_ARGUMENT else 2

        if prefix == GS:
            if command in (LF, CR):
                return 1  # GS solto: preservar a quebra seguinte.
            if command == GS_BARCODE:
                if len(pending) < 3:
                    return None
                if pending[2] == QR_SYMBOLOGY:  # GS k Q n1 n2 n3 n4 n5 n6 dados.
                    return None if len(pending) < 9 else 9 + int.from_bytes(pending[7:9], "little")
                if pending[2] <= 6:  # Simbologias antigas terminam em byte zero.
                    try:
                        return pending.index(0, 3) + 1
                    except ValueError:
                        return None
                return None if len(pending) < 4 else 4 + pending[3]
            return GS_COMMAND_SIZES.get(command, 2)

        if prefix == FS:
            return 4 if command == FS_LOGO else 2

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
            if packet[:2] in STATUS_QUERIES:
                continue

            self.raw.extend(packet)
            self.handle_packet(packet)

    def handle_packet(self, packet):
        control = packet[0]

        if control == LF:
            self.newline()
        elif control == CR:
            pass
        elif control == TAB:
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
            if packet[1] == FS_LOGO:
                self.warnings.add("Logo FS não renderizado.")
            else:
                self.warnings.add(f"Comando FS {packet[1]:02X} não suportado.")
        else:
            self.warnings.add(f"Controle {control:02X} não suportado.")

    def handle_esc(self, packet):
        command = packet[1]
        argument = packet[2] if len(packet) > 2 else 0

        if command == ESC_INITIALIZE:
            self.reset_style()
        elif command == ESC_DEFAULT_SPACING:
            self.line_spacing = 30
        elif command == ESC_LINE_SPACING:
            self.line_spacing = argument
        elif command in (ESC_BOLD_ON, ESC_BOLD_OFF):
            self.bold = command == ESC_BOLD_ON
        elif command in (ESC_ITALIC_ON, ESC_ITALIC_OFF):
            self.italic = command == ESC_ITALIC_ON
        elif command in (ESC_CONDENSED_ON, ESC_CONDENSED_OFF):
            self.font = "B" if command == ESC_CONDENSED_ON else "A"
        elif command == ESC_DOUBLE_WIDTH:
            self.width = 2 if argument else 1
        elif command == ESC_DOUBLE_HEIGHT:
            self.height = 2 if argument else 1
        elif command == ESC_ALIGN:
            self.align = ALIGNMENTS.get(argument, "left")
        elif command == ESC_PRINT_MODE:
            self.apply_print_mode(argument)
        elif command == ESC_UNDERLINE:
            self.underline = bool(argument)
        elif command in (ESC_FULL_CUT, ESC_PARTIAL_CUT):
            self.finish("cut")
        elif command == ESC_CODE_PAGE:
            self.encoding = CODE_PAGES.get(argument, "cp850")
            if argument not in CODE_PAGES:
                self.warnings.add(f"Página de código {argument} não suportada; usado CP850.")
        elif command in (ESC_DRAWER_1, ESC_DRAWER_2):
            drawer = 1 if command == ESC_DRAWER_1 else 2
            self.events.append({"type": "drawer", "drawer": drawer, "pulse_ms": argument})
        elif command == ESC_BEEP and packet[2] == 0x41:
            pass  # Beep: sem dispositivo físico.
        elif command == ESC_IMAGE:
            self.warnings.add("Imagem ESC * não renderizada.")
        else:
            self.warnings.add(f"Comando ESC {command:02X} não suportado.")

    def apply_print_mode(self, mode):
        self.bold = bool(mode & PRINT_MODE_BOLD)
        self.underline = bool(mode & PRINT_MODE_UNDERLINE)
        self.width = 2 if mode & PRINT_MODE_DOUBLE_WIDTH else 1
        self.height = 2 if mode & PRINT_MODE_DOUBLE_HEIGHT else 1
        self.font = "B" if mode & PRINT_MODE_CONDENSED else "A"

    def handle_gs(self, packet):
        command = packet[1]

        if command == GS_BARCODE and packet[2] == QR_SYMBOLOGY:
            self.print_qr(packet)
        elif packet == SELECT_ESCBEMA or command in GS_BARCODE_SETTINGS:
            pass  # Não mudam o que é desenhado.
        elif command == GS_BARCODE:
            self.warnings.add("Código de barras não renderizado.")
        else:
            self.warnings.add(f"Comando GS {command:02X} não suportado.")

    def close(self, reason="disconnect"):
        if self.pending:
            self.raw.extend(self.pending)
            self.pending.clear()
            self.warnings.add("Comando incompleto ao encerrar a conexão.")

        self.finish(reason)
