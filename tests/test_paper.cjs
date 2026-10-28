const assert = require('node:assert/strict');
const { layoutPaper, qrMatrix } = require('../web/paper.js');
const span = (text, extra = {}) => ({ text, font: 'A', width: 1, height: 1, ...extra });
const line = (spans, align = 'left') => ({ spans, align, spacing: 30 });

assert.equal(layoutPaper([line([span('A'.repeat(48))])]).length, 1);
assert.deepEqual(
  layoutPaper([line([span('A'.repeat(49))])]).map((r) => r.chunks.map((s) => s.text).join('').length),
  [48, 1],
);
assert.equal(layoutPaper([line([span('B'.repeat(64), { font: 'B' })])]).length, 1);
assert.equal(layoutPaper([line([span('B'.repeat(65), { font: 'B' })])]).length, 2);
const normal = layoutPaper([line([span('2X HAMBÚRGUER ARTESANAL - UNID')])])[0];
const tall = layoutPaper([line([span('2X HAMBÚRGUER ARTESANAL - UNID', { height: 2 })])])[0];
assert.equal(tall.chunks[0].dotWidth, normal.chunks[0].dotWidth);
assert.equal(tall.chunks[0].glyphHeight, normal.chunks[0].glyphHeight * 2);
assert.equal(layoutPaper([line([span('X'.repeat(25), { width: 2 })])]).length, 2);
assert.equal(layoutPaper([line([span('123')], 'right')])[0].chunks[0].x, 540);
assert.equal(layoutPaper([line([span('123')], 'center')])[0].chunks[0].x, 270);
assert.equal(layoutPaper([line([span('A'.repeat(24)), span('B'.repeat(32), { font: 'B' })])]).length, 1);
assert.equal(layoutPaper([line([])])[0].height, 30);
const base64 = (s) => Buffer.from(s, 'latin1').toString('base64');
// Versão 1 (21 módulos) + margem de 4 módulos em cada lado.
const qr = {
  type: 'qr',
  spans: [],
  data_base64: base64('https://a.com'),
  error_level: 'L',
  module_size: 4,
  align: 'center',
};
const matrix = qrMatrix(qr);
assert.equal(matrix.length, 29);
assert.ok(matrix.every((row) => row.length === 29 && /^[01]+$/.test(row)));
assert.ok(
  matrix
    .slice(0, 4)
    .concat(matrix.slice(-4))
    .every((row) => !row.includes('1')),
);
assert.ok(matrix.every((row) => row.startsWith('0000') && row.endsWith('0000')));
assert.equal(matrix[4].slice(4, 11), '1111111');
assert.equal(qrMatrix({ ...qr, data_base64: base64('A\x00\x1d\n\x1b@\xffB') }).length, 29);
assert.equal(
  qrMatrix({
    ...qr,
    error_level: 'H',
    data_base64: base64('https://example.com/emulador-escbematech'),
  }).length,
  45,
);
const qrRow = layoutPaper([line([span('Antes')]), qr, line([span('Depois')])])[1];
assert.equal(qrRow.qr.size, 116);
assert.equal(qrRow.qr.x, 230);
assert.equal(qrRow.height, 116);
assert.equal(layoutPaper([{ ...qr, align: 'right' }])[0].qr.x, 460);
assert.ok(Math.abs(layoutPaper([{ ...qr, module_size: 16 }])[0].qr.size - 230.4) < 0.001);
const warnings = [];
const overflow = layoutPaper(
  [{ ...qr, error_level: 'H', data_base64: base64('a'.repeat(4000)) }, line([span('Texto')])],
  warnings,
);
assert.equal(warnings.length, 1);
assert.equal(overflow.length, 1);
assert.equal(overflow[0].chunks[0].text, 'Texto');
assert.match(warnings[0], /excede a capacidade/);
const invalid = [];
layoutPaper([{ ...qr, data_base64: '!!!' }], invalid);
assert.equal(invalid.length, 1);
assert.doesNotMatch(invalid[0], /capacidade/);
assert.match(invalid[0], /^QR code não gerado: /);
console.log('OK: 48/64 colunas, fontes mistas, altura e largura independentes, alinhamento, quebras e QR.');
