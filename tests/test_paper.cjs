const assert = require('node:assert/strict');
const { describe, test } = require('node:test');

const { layoutPaper, qrMatrix } = require('../web/paper.js');

const span = (text, extra = {}) => ({ text, font: 'A', width: 1, height: 1, ...extra });
const line = (spans, align = 'left') => ({ spans, align, spacing: 30 });
const base64 = (text) => Buffer.from(text, 'latin1').toString('base64');
const rowTexts = (rows) => rows.map((row) => row.chunks.map((chunk) => chunk.text).join(''));

const qr = {
  type: 'qr',
  spans: [],
  data_base64: base64('https://a.com'),
  error_level: 'L',
  module_size: 4,
  align: 'center',
};

describe('layoutPaper', () => {
  test('fits 48 normal characters or 64 condensed characters per row', () => {
    assert.equal(layoutPaper([line([span('A'.repeat(48))])]).length, 1);
    assert.deepEqual(rowTexts(layoutPaper([line([span('A'.repeat(49))])])), ['A'.repeat(48), 'A']);

    assert.equal(layoutPaper([line([span('B'.repeat(64), { font: 'B' })])]).length, 1);
    assert.equal(layoutPaper([line([span('B'.repeat(65), { font: 'B' })])]).length, 2);
  });

  test('mixes fonts in the same row', () => {
    const rows = layoutPaper([line([span('A'.repeat(24)), span('B'.repeat(32), { font: 'B' })])]);

    assert.equal(rows.length, 1);
  });

  test('keeps double height independent from width', () => {
    const text = '2X HAMBÚRGUER ARTESANAL - UNID';

    const normal = layoutPaper([line([span(text)])])[0];
    const tall = layoutPaper([line([span(text, { height: 2 })])])[0];

    assert.equal(tall.chunks[0].dotWidth, normal.chunks[0].dotWidth);
    assert.equal(tall.chunks[0].glyphHeight, normal.chunks[0].glyphHeight * 2);
  });

  test('halves the capacity of double width text', () => {
    assert.equal(layoutPaper([line([span('X'.repeat(25), { width: 2 })])]).length, 2);
  });

  test('aligns rows to the right and to the center', () => {
    assert.equal(layoutPaper([line([span('123')], 'right')])[0].chunks[0].x, 540);
    assert.equal(layoutPaper([line([span('123')], 'center')])[0].chunks[0].x, 270);
  });

  test('keeps the line spacing of empty lines', () => {
    assert.equal(layoutPaper([line([])])[0].height, 30);
  });

  test('places QR codes between text rows', () => {
    const qrRow = layoutPaper([line([span('Antes')]), qr, line([span('Depois')])])[1];

    assert.equal(qrRow.qr.size, 116);
    assert.equal(qrRow.qr.x, 230);
    assert.equal(qrRow.height, 116);
    assert.equal(layoutPaper([{ ...qr, align: 'right' }])[0].qr.x, 460);
  });

  test('limits QR codes to 40% of the paper', () => {
    const size = layoutPaper([{ ...qr, module_size: 16 }])[0].qr.size;

    assert.ok(Math.abs(size - 230.4) < 0.001);
  });

  test('warns about QR codes over capacity and keeps the following text', () => {
    const warnings = [];
    const oversized = { ...qr, error_level: 'H', data_base64: base64('a'.repeat(4000)) };

    const rows = layoutPaper([oversized, line([span('Texto')])], warnings);

    assert.deepEqual(rowTexts(rows), ['Texto']);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /excede a capacidade/);
  });

  test('reports other QR failures with their own message', () => {
    const warnings = [];

    layoutPaper([{ ...qr, data_base64: '!!!' }], warnings);

    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /^QR code não gerado: /);
    assert.doesNotMatch(warnings[0], /capacidade/);
  });
});

describe('qrMatrix', () => {
  test('adds a four module quiet zone around version 1', () => {
    const matrix = qrMatrix(qr);
    const borderRows = [...matrix.slice(0, 4), ...matrix.slice(-4)];

    // Versão 1 (21 módulos) + margem de 4 módulos em cada lado.
    assert.equal(matrix.length, 29);
    assert.ok(matrix.every((row) => row.length === 29 && /^[01]+$/.test(row)));
    assert.ok(borderRows.every((row) => !row.includes('1')));
    assert.ok(matrix.every((row) => row.startsWith('0000') && row.endsWith('0000')));
    assert.equal(matrix[4].slice(4, 11), '1111111');
  });

  test('encodes binary content byte by byte', () => {
    assert.equal(qrMatrix({ ...qr, data_base64: base64('A\x00\x1d\n\x1b@\xffB') }).length, 29);
  });

  test('grows the version with the error correction level', () => {
    const matrix = qrMatrix({
      ...qr,
      error_level: 'H',
      data_base64: base64('https://example.com/emulador-escbematech'),
    });

    assert.equal(matrix.length, 45);
  });
});
