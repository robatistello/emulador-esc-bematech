// Regras escolhidas uma a uma, sem importar presets, para o ESLint rodar pelo
// npx sem package.json nem node_modules no projeto.
const rules = {
  'no-undef': 'error',
  'no-unused-vars': ['error', { args: 'after-used', argsIgnorePattern: '^_' }],
  'no-redeclare': 'error',
  'no-dupe-keys': 'error',
  'no-duplicate-case': 'error',
  'no-unreachable': 'error',
  'no-constant-condition': 'error',
  'no-self-assign': 'error',
  'no-empty': ['error', { allowEmptyCatch: true }],
  'no-var': 'error',
  'prefer-const': 'error',
  eqeqeq: 'error',
};

const browser = {
  atob: 'readonly',
  btoa: 'readonly',
  Blob: 'readonly',
  confirm: 'readonly',
  document: 'readonly',
  fetch: 'readonly',
  Image: 'readonly',
  localStorage: 'readonly',
  matchMedia: 'readonly',
  setTimeout: 'readonly',
  URL: 'readonly',
  window: 'readonly',
  XMLSerializer: 'readonly',
};

export default [
  { ignores: ['emulator/web/qrcode.js'] },
  {
    files: ['emulator/web/paper.js'],
    languageOptions: {
      sourceType: 'script',
      globals: { ...browser, globalThis: 'readonly', module: 'readonly', require: 'readonly' },
    },
    rules,
  },
  {
    files: ['emulator/web/app.js'],
    languageOptions: {
      sourceType: 'script',
      // Definidos pelo paper.js e pelo script do tema no index.html, carregados antes.
      globals: {
        ...browser,
        renderPaper: 'readonly',
        paperPng: 'readonly',
        systemDark: 'readonly',
        applyTheme: 'readonly',
      },
    },
    rules,
  },
  {
    files: ['tests/**/*.cjs'],
    languageOptions: {
      sourceType: 'commonjs',
      globals: { Buffer: 'readonly', require: 'readonly' },
    },
    rules,
  },
];
