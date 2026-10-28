"""Subconjunto do protocolo EscBematech, com pacotes TCP fragmentados."""
import base64
import re
from datetime import datetime, timezone

TEXT = re.compile(rb"[^\x00-\x1f]+")


class Parser:
    def __init__(self, save):
        self.save = save
        self.pending = bytearray()
        self.raw = bytearray()
        self.lines, self.spans = [], []
        self.events = []
        self.text = bytearray()
        self.warnings = set()
        self.reset_style()

    def reset_style(self):
        self.bold, self.italic, self.underline = False, False, False
        self.align, self.font = "left", "A"
        self.width, self.height = 1, 1
        self.line_spacing, self.encoding = 30, "cp850"

    def print_qr(self, packet):
        error, module, version, encoding = packet[3:7]
        data = packet[9:]
        if error > 3 or version != 0 or encoding > 2 or not data:
            self.warnings.add("QR code com parâmetros não suportados ou conteúdo vazio.")
            return
        if self.spans or self.text:
            self.newline()
        self.lines.append(dict(type="qr", align=self.align, spans=[], module_size=module or 4,
                               error_level="LMQH"[error], data_base64=base64.b64encode(data).decode("ascii")))

    def flush_text(self):
        if self.text:
            self.spans.append(dict(text=self.text.decode(self.encoding, errors="replace"),
                                   bold=self.bold, italic=self.italic, underline=self.underline,
                                   width=self.width, height=self.height, font=self.font))
            self.text.clear()

    def newline(self):
        self.flush_text()
        self.lines.append(dict(align=self.align, spans=self.spans, spacing=self.line_spacing))
        self.spans = []

    def has_content(self):
        return bool(self.events or self.warnings) or any(
            line.get("type") == "qr" or any(span["text"].strip() for span in line["spans"]) for line in self.lines)

    def finish(self, reason="disconnect"):
        self.flush_text()
        if self.spans:
            self.newline()
        # Sistemas costumam mandar inicialização ou avanço de papel logo depois do
        # corte; sem texto, QR, gaveta ou aviso, isso não é uma nova impressão.
        if self.has_content():
            self.save(dict(protocol="bematech", created_at=datetime.now(timezone.utc).isoformat(),
                           reason=reason, lines=self.lines, events=self.events, warnings=sorted(self.warnings),
                           raw_base64=base64.b64encode(self.raw).decode("ascii")))
        self.raw.clear()
        self.lines, self.spans = [], []
        self.events = []
        self.warnings.clear()

    def packet_size(self):
        """None significa que ainda faltam bytes; blocos binários são atômicos."""
        p = self.pending
        if p[0] not in (0x1b, 0x1d, 0x1c, 0x10):
            return 1
        if len(p) < 2:
            return None
        prefix, cmd = p[:2]
        if prefix == 0x1b:
            if cmd == 0x28:  # ESC ( A: beep, comprimento little endian.
                return None if len(p) < 5 else 5 + int.from_bytes(p[3:5], "little")
            if cmd == 0x2a:  # ESC *: imagem em colunas.
                if len(p) < 5:
                    return None
                return 5 + int.from_bytes(p[3:5], "little") * (3 if p[2] in (32, 33) else 1)
            return 3 if cmd in (0x21, 0x2d, 0x33, 0x57, 0x61, 0x64, 0x74, 0x76, 0x80) else 2
        if prefix == 0x1d:
            if cmd in (0x0a, 0x0d):
                return 1  # GS solto: preservar a quebra seguinte.
            if cmd == 0x6b:
                if len(p) < 3:
                    return None
                if p[2] == 0x51:  # QR nativo: GS k Q n1 n2 n3 n4 n5 n6 dados.
                    return None if len(p) < 9 else 9 + int.from_bytes(p[7:9], "little")
                if p[2] <= 6:
                    try:
                        return p.index(0, 3) + 1
                    except ValueError:
                        return None
                return None if len(p) < 4 else 4 + p[3]
            return {0xf9: 4, 0xf8: 3, 0x48: 3, 0x68: 3, 0x77: 3, 0x66: 3}.get(cmd, 2)
        if prefix == 0x1c:
            return 4 if cmd == 0x70 else 2
        return 3

    def feed(self, data):
        self.pending.extend(data)
        while self.pending:
            # Texto comum segue em bloco; só bytes de controle passam pelo enquadramento.
            text = TEXT.match(self.pending)
            if text:
                run = self.pending[:text.end()]
                del self.pending[:text.end()]
                self.raw.extend(run)
                self.text.extend(run)
                continue
            size = self.packet_size()
            if size is None or len(self.pending) < size:
                return
            packet = bytes(self.pending[:size])
            del self.pending[:size]
            b = packet[0]
            # Consultas de status não constituem uma impressão.
            if packet[:2] in (b"\x10\x04", b"\x1d\xf8"):
                continue
            self.raw.extend(packet)
            if b == 0x0a:
                self.newline()
            elif b == 0x0d:
                pass
            elif b == 0x09:
                self.text.extend(b"    ")
            elif b == 0x1b:
                self.flush_text()
                cmd = packet[1]
                n = packet[2] if len(packet) > 2 else 0
                if cmd == 0x40:
                    self.reset_style()
                elif cmd == 0x32:
                    self.line_spacing = 30
                elif cmd == 0x33:
                    self.line_spacing = n
                elif cmd in (0x45, 0x46):
                    self.bold = cmd == 0x45
                elif cmd in (0x34, 0x35):
                    self.italic = cmd == 0x34
                elif cmd in (0x0f, 0x48):
                    self.font = "B" if cmd == 0x0f else "A"
                elif cmd == 0x57:
                    self.width = 2 if n else 1
                elif cmd == 0x64:
                    self.height = 2 if n else 1
                elif cmd == 0x61:
                    self.align = {0: "left", 1: "center", 2: "right"}.get(n, "left")
                elif cmd == 0x21:
                    self.bold, self.underline = bool(n & 8), bool(n & 128)
                    self.width, self.height = (2 if n & 32 else 1), (2 if n & 16 else 1)
                    self.font = "B" if n & 1 else "A"
                elif cmd == 0x2d:
                    self.underline = bool(n)
                elif cmd in (0x77, 0x6d):
                    self.finish("cut")
                elif cmd == 0x74:
                    self.encoding = {2: "cp850", 3: "cp437", 4: "cp860", 8: "utf-8"}.get(n, "cp850")
                    if n not in (2, 3, 4, 8):
                        self.warnings.add(f"Página de código {n} não suportada; usado CP850.")
                elif cmd in (0x76, 0x80):
                    self.events.append(dict(type="drawer", drawer=1 if cmd == 0x76 else 2, pulse_ms=n))
                elif cmd == 0x28 and packet[2] == 0x41:
                    pass  # Beep: sem dispositivo físico.
                elif cmd == 0x2a:
                    self.warnings.add("Imagem ESC * não renderizada.")
                else:
                    self.warnings.add(f"Comando ESC {cmd:02X} não suportado.")
            elif b == 0x1d:
                if len(packet) == 1:
                    continue
                self.flush_text()
                if packet[:3] == b"\x1dkQ":
                    self.print_qr(packet)
                elif packet == b"\x1d\xf9\x20\x00" or packet[1] in (0x48, 0x68, 0x77, 0x66):
                    pass  # Seleção EscBema e parâmetros de código de barras.
                elif packet[1] == 0x6b:
                    self.warnings.add("Código de barras não renderizado.")
                else:
                    self.warnings.add(f"Comando GS {packet[1]:02X} não suportado.")
            elif b == 0x1c:
                self.flush_text()
                self.warnings.add("Logo FS não renderizado." if packet[1] == 0x70 else f"Comando FS {packet[1]:02X} não suportado.")
            else:
                self.warnings.add(f"Controle {b:02X} não suportado.")

    def close(self, reason="disconnect"):
        if self.pending:
            self.raw.extend(self.pending)
            self.pending.clear()
            self.warnings.add("Comando incompleto ao encerrar a conexão.")
        self.finish(reason)
