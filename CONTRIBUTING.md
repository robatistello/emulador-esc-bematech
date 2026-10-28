# Contribuir

Este guia reúne o que é preciso para desenvolver o emulador: estrutura do projeto, testes, padrão de escrita, formatação, build dos executáveis e publicação de versões. Para usar o emulador, veja o [README](README.md).

Contribuições são bem-vindas! Correções pequenas podem ir direto num pull request. Para mudanças maiores, como um comando novo ou uma alteração na interface, vale abrir uma issue antes para conversarmos sobre a ideia e alinharmos o caminho juntos desde o começo. Ao abrir o pull request, o GitHub mostra um modelo com o que ajuda na revisão.

## Estrutura

```
emulator/            código do programa
  __main__.py        ponto de entrada (python -m emulator e o executável)
  escpos.py          Parser incremental dos comandos EscBematech
  server.py          servidores TCP e HTTP, histórico SQLite e linha de comando
  tray.py            ícone da bandeja do Windows, pela API Win32 com ctypes
  printer.ico        ícone da bandeja e do .exe
  web/               página do histórico (HTML, CSS e JavaScript)
    fonts/           Roboto (interface) e Roboto Mono (papel)
packaging/           build dos executáveis, LEIA-ME de cada pacote e avisos de licença
  licenses/          textos de licença das bibliotecas que o Python embute no executável
tests/               testes Python (unittest) e do renderizador (Node)
tools/               send_demo.py (impressão de exemplo) e smoke_test.py (teste do executável)
docs/                imagens do README
.github/workflows/   testes a cada push e release a cada tag
```

O emulador usa só a biblioteca padrão do Python. As ferramentas de desenvolvimento abaixo não são necessárias para executá-lo.

## Ambiente

- **Python 3.14 ou superior**, a mesma versão que vai dentro dos executáveis e que o CI testa. No Windows, use o lançador `py`, que acompanha o instalador do python.org e não depende do atalho da Microsoft Store que o Windows coloca no PATH.
- **[Node.js](https://nodejs.org/) LTS**, para os testes do renderizador e o Prettier.
- **[uv](https://docs.astral.sh/uv/)**, para o Ruff e o build Linux. No Windows, pelo PowerShell:

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  No Linux ou no WSL:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## Executar e testar

Na pasta do projeto:

```bash
python -m emulator --console
python tools/send_demo.py --qr
```

Rode sempre os dois conjuntos de testes; o do renderizador não faz parte do `unittest`:

```bash
python -m unittest discover -s tests -v
node tests/test_paper.cjs
```

Os testes Python cobrem o parser (com os bytes entregues um a um, como o pior caso de fragmentação TCP), o histórico, os servidores TCP e HTTP, a linha de comando e o encerramento com impressão pendente. No Windows, também criam por alguns instantes um ícone real na bandeja; esse teste é pulado no GitHub Actions, que não tem área de trabalho interativa.

## Padrão de escrita

- **Idiomas:** o código é em inglês, inclusive nomes de variáveis, funções, testes e chaves salvas no navegador. Textos da interface, mensagens, comentários e documentação são em português.
- **Nomes por extenso:** nada de variáveis de uma letra ou abreviadas (`p`, `n`, `s`, `cmd`); a exceção são termos consagrados do domínio, como `hwnd` da API do Windows, `db` ou as coordenadas `x` e `y`.
- **Espaçamento:** uma linha em branco separa os passos de uma função (preparação, laço, resultado), e não só uma função da outra. Os formatadores preservam essas linhas, mas não as criam.
- **Funções pequenas:** cada função faz uma coisa; um bloco que precisa de um comentário para dizer o que faz geralmente vira uma função com esse nome.
- **Comentários:** só quando explicam um porquê que o código não mostra, como detalhes do protocolo, peculiaridades do Windows ou segurança. Não descreva o que o código faz nem o histórico das mudanças.
- **Termos:** cada envio é uma *impressão* na interface e um `job` no código. Não use "recibo" ou `receipt`: nem todo envio é recibo (gaveta, relatórios, DANFE).

## Fontes da página

A página leva as próprias fontes, para ter a mesma aparência em qualquer sistema: a Roboto na interface e a Roboto Mono no papel, que também vai embutida no PNG exportado. As duas são fontes variáveis, com todos os pesos num arquivo só, baixadas do repositório [google/fonts](https://github.com/google/fonts) (`ofl/roboto` e `ofl/robotomono`) e apenas convertidas para WOFF2, sem tirar caracteres:

```bash
uvx --from fonttools --with brotli fonttools ttLib.woff2 compress "RobotoMono[wght].ttf" -o emulator/web/fonts/roboto-mono.woff2
```

A Roboto Mono não tem os desenhos de caixa e blocos do CP437 e do CP850 (`═ ║ ╔ ░ ▒ ▓`); quando uma impressão usa esses caracteres, o navegador os desenha com uma fonte monoespaçada do sistema.

## Formatação

O código segue dois formatadores, com 120 colunas nos dois. O workflow de testes confere a formatação e falha se algum arquivo estiver fora do padrão.

| Arquivos | Ferramenta | Configuração |
|---|---|---|
| Python | [Ruff](https://docs.astral.sh/ruff/) | `ruff.toml` |
| HTML, CSS e JavaScript de `emulator/web`, `tests/test_paper.cjs` e `eslint.config.mjs` | [Prettier](https://prettier.io/) | `.prettierrc.json`; o `.prettierignore` deixa de fora o `qrcode.js`, que é de terceiros |

Depois de editar, formate:

```bash
uvx ruff@0.17.3 format
npx prettier@3.9.10 --write emulator/web tests/test_paper.cjs eslint.config.mjs
```

Para só conferir, como o CI, troque `format` por `format --check` e `--write` por `--check`. Sem o uv, o Ruff também instala pelo pip: `python -m pip install ruff==0.17.3` e depois `python -m ruff format`.

Além da formatação, o JavaScript passa pelo [ESLint](https://eslint.org/), que aponta erros que o Prettier não vê, como variável não declarada ou não usada, `var` e comparação com `==`. As regras ficam em `eslint.config.mjs`, escolhidas uma a uma para o ESLint rodar pelo `npx`, sem `package.json`:

```bash
npx eslint@10.13.0 emulator/web tests/test_paper.cjs
```

No VS Code, as extensões oficiais [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode) e [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) leem as mesmas configurações; com "Format On Save" ligado, cada arquivo é formatado ao salvar. A extensão do ESLint precisa do pacote instalado; sem ele, use o comando acima.

## Build dos executáveis

**Windows**, no PowerShell, na pasta do projeto:

```powershell
.\packaging\build.ps1
```

O script cria o ambiente `.venv-build`, instala o PyInstaller e gera `outputs\windows\EmuladorEscBematech.exe`, com o `LEIA-ME.txt` ao lado e a versão nas propriedades do arquivo. Se esse `.exe` estiver aberto, ele para e pede para sair do emulador pela bandeja. `-CleanOnly` só limpa os temporários de `work\windows`, e `-Python` escolhe outro Python, como `-Python 'C:\Python314\python.exe'`.

**Linux**, num Linux x86_64 ou no WSL, com o uv e o `objdump` (pacote `binutils`):

```bash
./packaging/build.sh
```

O script gera `outputs/linux/EmuladorEscBematech` com o Python do uv, que é compilado para glibc 2.17; com o Python do sistema, o binário só abriria em distribuições tão novas quanto a máquina do build. No fim, ele confere a glibc exigida e falha se passar de 2.17. As pastas do Linux (`.venv-build-linux`, `work/linux`, `outputs/linux`) são separadas das do Windows, para a mesma cópia do projeto poder ser compilada pelos dois.

### Licenças nos executáveis

O repositório só contém código de terceiros no `qrcode.js`, coberto pelo `THIRD-PARTY-NOTICES.txt` da raiz. Os executáveis, porém, levam o interpretador Python e bibliotecas nativas (OpenSSL, libffi, SQLite, mpdecimal e outras), cujas licenças pedem que o texto acompanhe o binário. Por isso os dois scripts de build rodam o `packaging/notices.py`, que monta um `THIRD-PARTY-NOTICES.txt` completo: o da raiz mais as licenças do Python embutido. Esse arquivo vai dentro do executável, para o `--licenses`, e ao lado dele no pacote.

- **Windows:** usa o `LICENSE.txt` que o instalador do Python já traz (Python, condições da Microsoft, bzip2, libffi, zstd e OpenSSL) e completa com os textos de `packaging/licenses` para mpdecimal, zlib-ng, liblzma e SQLite.
- **Linux:** usa os textos de `packaging/licenses`, tirados do pacote completo do [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (release `20261013`), que é de onde vem o Python do uv. A lista segue o `PYTHON.json` desse pacote: só entram as bibliotecas ligadas dentro da `libpython`, que é o que o PyInstaller empacota.

Ao trocar a versão do Python do build, confira se as bibliotecas embutidas mudaram.

### Teste do executável

Para conferir um executável compilado, o teste rápido abre o programa em portas livres, envia a impressão de exemplo e verifica o histórico:

```bash
python tools/smoke_test.py outputs/windows/EmuladorEscBematech.exe
python tools/smoke_test.py outputs/linux/EmuladorEscBematech
```

## Versões

A versão fica na constante `VERSION` de `emulator/server.py`, no formato `maior.menor.correção`: o último número sobe em correções, o do meio em recursos novos e o primeiro em mudanças grandes. A página, o `--version`, o cabeçalho `Server` e as propriedades do `.exe` leem dela; não repita o número em outro arquivo.

Para publicar uma versão, altere `VERSION`, faça o commit e envie a tag correspondente:

```bash
git tag v1.2.0
git push origin v1.2.0
```

O workflow de release confere se a tag bate com `VERSION`, roda os testes, compila nos dois sistemas, roda o teste rápido em cada executável e só então publica a Release com o `EmuladorEscBematech-X.Y.Z-windows.zip` e o `EmuladorEscBematech-X.Y.Z-linux.tar.gz`.

## Dependências do desenvolvimento

O Dependabot (`.github/dependabot.yml`) abre um pull request por mês quando há versão nova das actions dos workflows ou do PyInstaller (`packaging/requirements-build.txt`). As versões do Ruff, do Prettier e do ESLint ficam escritas nos comandos do `tests.yml`, deste guia e do CLAUDE.md, e o Dependabot não as acompanha: ao atualizar uma delas, troque em todos esses lugares.

## Commits

Mensagens em português, com prefixo convencional (`feat:`, `fix:`, `refactor:`, `style:`, `docs:`) e um corpo explicando o porquê da mudança.
