// O navegador recebe posições explícitas; CSS não decide as quebras do cupom.
(function (root) {
  const FONTS = {
    A: { cell: 12, height: 24, baseline: 21 },
    B: { cell: 9, height: 17, baseline: 16 },
  };
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const QR_BORDER = 4;

  const qrcode = root.qrcode || require('./qrcode.js');

  function setAttributes(element, attributes) {
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, value);
    }
    return element;
  }

  function svgElement(name, attributes) {
    return setAttributes(document.createElementNS(SVG_NS, name), attributes);
  }

  // atob devolve um caractere por byte, que o modo Byte grava sem conversão.
  function qrMatrix(line) {
    const data = atob(line.data_base64);
    const mode = /^[0-9]+$/.test(data) ? 'Numeric' : /^[0-9A-Z $%*+\-.\/:]+$/.test(data) ? 'Alphanumeric' : 'Byte';

    const qr = qrcode(0, line.error_level);
    qr.addData(data, mode);
    qr.make();

    const count = qr.getModuleCount();
    const size = count + QR_BORDER * 2;
    const isDark = (row, column) => row >= 0 && row < count && column >= 0 && column < count && qr.isDark(row, column);

    return Array.from({ length: size }, (_, row) =>
      Array.from({ length: size }, (_, column) => (isDark(row - QR_BORDER, column - QR_BORDER) ? '1' : '0')).join(''),
    );
  }

  function layoutPaper(lines, warnings = []) {
    const paperWidth = 48 * FONTS.A.cell;
    const rows = [];
    const offset = (align, width) =>
      align === 'center' ? (paperWidth - width) / 2 : align === 'right' ? paperWidth - width : 0;

    for (const line of lines) {
      if (line.type === 'qr') {
        let matrix;
        try {
          matrix = qrMatrix(line);
        } catch (error) {
          // A biblioteca sinaliza capacidade excedida com um texto, não com um tipo de erro.
          warnings.push(
            /overflow/i.test(String(error))
              ? 'QR code não gerado: conteúdo excede a capacidade do QR code para este nível de correção.'
              : 'QR code não gerado: ' + (error.message || error),
          );
          continue;
        }

        const moduleSize = Math.min(line.module_size, (paperWidth * 0.4) / matrix.length);
        const size = matrix.length * moduleSize;
        rows.push({
          chunks: [],
          width: paperWidth,
          height: size,
          qr: { matrix, moduleSize, size, x: offset(line.align, size) },
        });
        continue;
      }

      let chunks = [];
      let used = 0;

      function finish() {
        const glyphHeight = Math.max(FONTS.A.height, ...chunks.map((chunk) => chunk.glyphHeight));
        const x = offset(line.align, used);

        for (const chunk of chunks) {
          chunk.x += x;
        }
        rows.push({ chunks, width: paperWidth, glyphHeight, height: Math.max(glyphHeight, line.spacing ?? 30) });

        chunks = [];
        used = 0;
      }

      for (const span of line.spans) {
        const font = FONTS[span.font] || FONTS.A;
        const cell = font.cell * (span.width || 1);
        const glyphHeight = font.height * (span.height || 1);
        const baseline = font.baseline * (span.height || 1);
        const chars = Array.from(span.text);

        let cursor = 0;
        while (cursor < chars.length) {
          let capacity = Math.floor((paperWidth - used) / cell);
          if (capacity === 0) {
            finish();
            capacity = Math.floor(paperWidth / cell);
          }

          const count = Math.min(capacity, chars.length - cursor);
          chunks.push({
            ...span,
            text: chars.slice(cursor, cursor + count).join(''),
            x: used,
            dotWidth: count * cell,
            glyphHeight,
            baseline,
          });

          used += count * cell;
          cursor += count;
        }
      }

      finish();
    }

    return rows;
  }

  function renderQr(svg, { matrix, moduleSize, size, x }) {
    let path = '';
    for (let y = 0; y < matrix.length; y++) {
      for (let column = 0; column < matrix[y].length; column++) {
        if (matrix[y][column] === '1') {
          path += `M${x + column * moduleSize} ${y * moduleSize}h${moduleSize}v${moduleSize}h${-moduleSize}z`;
        }
      }
    }

    svg.classList.add('paper-qr');
    svg.setAttribute('aria-label', 'QR code');
    svg.append(svgElement('rect', { x, y: 0, width: size, height: size, fill: '#fff' }));
    svg.append(svgElement('path', { d: path, fill: '#000', 'shape-rendering': 'crispEdges' }));
  }

  function renderText(svg, row) {
    svg.setAttribute('aria-label', row.chunks.map((chunk) => chunk.text).join(''));

    for (const chunk of row.chunks) {
      const top = row.glyphHeight - chunk.glyphHeight;

      const text = svgElement('text', {
        x: chunk.x,
        y: top + chunk.baseline,
        'font-family': 'Consolas, monospace',
        'font-size': chunk.glyphHeight,
        'font-weight': chunk.bold ? '700' : '400',
        fill: '#171717',
        'font-style': chunk.italic ? 'italic' : 'normal',
        textLength: chunk.dotWidth,
        lengthAdjust: 'spacingAndGlyphs',
        'xml:space': 'preserve',
      });
      text.style.whiteSpace = 'pre';
      text.textContent = chunk.text;
      svg.append(text);

      if (chunk.underline) {
        const y = top + chunk.glyphHeight - 1;
        svg.append(
          svgElement('line', {
            x1: chunk.x,
            x2: chunk.x + chunk.dotWidth,
            y1: y,
            y2: y,
            stroke: '#171717',
            'stroke-width': 1,
          }),
        );
      }
    }
  }

  function renderPaper(container, lines) {
    const warnings = [];
    container.replaceChildren();

    for (const row of layoutPaper(lines, warnings)) {
      const svg = svgElement('svg', { viewBox: `0 0 ${row.width} ${row.height}`, class: 'paper-row', role: 'img' });

      if (row.qr) {
        renderQr(svg, row.qr);
      } else {
        renderText(svg, row);
      }

      container.append(svg);
    }

    return warnings;
  }

  function paperPng(container, margin = 24) {
    const page = document.createElementNS(SVG_NS, 'svg');
    let width = 0;
    let height = margin;

    for (const row of container.querySelectorAll('svg.paper-row')) {
      const [, , rowWidth, rowHeight] = row.getAttribute('viewBox').split(' ').map(Number);
      page.append(setAttributes(row.cloneNode(true), { x: margin, y: height, width: rowWidth, height: rowHeight }));

      width = Math.max(width, rowWidth + margin * 2);
      height += rowHeight;
    }
    height += margin;

    page.prepend(svgElement('rect', { width: '100%', height: '100%', fill: '#fffdf4' }));
    setAttributes(page, { xmlns: SVG_NS, width, height, viewBox: `0 0 ${width} ${height}` });

    const svgText = new XMLSerializer().serializeToString(page);
    const url = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml' }));

    return new Promise((resolve, reject) => {
      const fail = () => {
        URL.revokeObjectURL(url);
        reject(Error('Não foi possível gerar a imagem.'));
      };

      const image = new Image();
      image.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        canvas.getContext('2d').drawImage(image, 0, 0);
        URL.revokeObjectURL(url);
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(Error('Não foi possível gerar a imagem.'))),
          'image/png',
        );
      };
      image.onerror = fail;
      image.src = url;
    });
  }

  root.layoutPaper = layoutPaper;
  root.renderPaper = renderPaper;
  root.paperPng = paperPng;

  if (typeof module !== 'undefined') {
    module.exports = { layoutPaper, qrMatrix };
  }
})(typeof window !== 'undefined' ? window : globalThis);
