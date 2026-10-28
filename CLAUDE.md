# CLAUDE.md

Emulador de impressora térmica que recebe comandos **EscBematech** de qualquer sistema que imprima nesse padrão (no ACBr, modelo `ppEscBematech`) via TCP/RAW e mostra cada impressão num histórico web. Roda no Windows, na bandeja ou no terminal, e no Linux, no terminal. O uso está no [README.md](README.md); estrutura, padrão de escrita, formatação, build e versões estão no [CONTRIBUTING.md](CONTRIBUTING.md), que vale como regra.

## Comandos

```powershell
py -m emulator --console                         # terminal (impressora 9100, histórico http://127.0.0.1:9101)
py -m emulator --tray                            # bandeja, mantendo o terminal
py tools/send_demo.py --qr                       # envia uma impressão de exemplo
py -m unittest discover -s tests -v              # testes Python
node tests/test_paper.cjs                        # testes do renderizador e do QR
uvx ruff@0.17.3 format                           # formata o Python
npx prettier@3.9.10 --write emulator/web tests/test_paper.cjs eslint.config.mjs  # formata a página e o teste Node
npx eslint@10.13.0 emulator/web tests/test_paper.cjs  # analisa o JavaScript
.\packaging\build.ps1                            # gera outputs\windows\EmuladorEscBematech.exe
./packaging/build.sh                             # no Linux ou WSL: gera outputs/linux/EmuladorEscBematech
py tools/smoke_test.py outputs/windows/EmuladorEscBematech.exe  # abre o executável e confere uma impressão
```

Rode sempre os dois conjuntos de testes (o Node não faz parte do `unittest`), os dois formatadores e o ESLint; o CI confere todos.

## Arquitetura

- `emulator/escpos.py` — `Parser` incremental: enquadra os bytes em comandos (aceita pacotes TCP fragmentados), mantém o estado de estilo e chama `save(job)` a cada corte (`ESC w`/`ESC m`) ou ao fechar a conexão. `handle_esc`, `handle_gs` e o tratamento de FS interpretam cada família. O job é um dict com `lines`, `events`, `warnings` e `raw_base64`.
- `emulator/server.py` — servidor TCP (`PrinterServer`), servidor HTTP (`WebServer`), histórico SQLite (`History`, tabela `jobs`) e linha de comando (`build_argument_parser`, `serve`, `main`). Rotas: `/`, `/style.css`, `/app.js`, `/paper.js`, `/qrcode.js`, as fontes em `/fonts/`, `GET /api/jobs`, `GET /api/jobs/<id>` e `DELETE /api/jobs`. `GET /api/jobs` envia `ETag` (número e data da última impressão) e responde 304 quando a lista não mudou.
- `emulator/logs.py` — `configure_logging`: no terminal, as mensagens vão para a tela; na bandeja, para `emulator.log` na pasta do histórico, com rotação de 1 MB e três cópias. Registra início, conexões (cliente, motivo do fim, bytes, impressões) e erros, nunca o conteúdo das impressões.
- `emulator/tray.py` — ícone da bandeja via API Win32 com `ctypes`.
- `emulator/__main__.py` — ponto de entrada de `python -m emulator` e do executável.
- `emulator/web/index.html` — estrutura da página e o script do tema, embutido antes do `style.css` para a página não abrir no tema errado.
- `emulator/web/app.js` — comportamento da página: consulta `/api/jobs` a cada 2 segundos, conta as impressões novas no título e no ícone com a aba em segundo plano, e opcionalmente mostra cada impressão nova (pulando as que são só gaveta). As escolhas de tema e dessa opção ficam em `localStorage` (`theme`, `show-new-jobs`).
- `emulator/web/paper.js` — layout e renderização em SVG com células fixas de 48 colunas, matriz do QR a partir de `data_base64` e exportação do papel como PNG (`paperPng`), que embute a fonte no SVG.
- `emulator/web/fonts/` — Roboto (interface) e Roboto Mono (papel), servidas em `/fonts/`; veja "Fontes da página" no CONTRIBUTING.md.
- `emulator/web/qrcode.js` — biblioteca de terceiros (qrcode-generator 2.0.4, MIT). Não edite; para atualizar, substitua o arquivo inteiro e ajuste `THIRD-PARTY-NOTICES.txt`.
- `packaging/` — `build.ps1`, `build.sh`, `requirements-build.txt` e os LEIA-ME de cada pacote, que viram `LEIA-ME.txt` no zip e no tar.gz. `notices.py` monta o `THIRD-PARTY-NOTICES.txt` do executável (o da raiz mais as licenças do Python embutido, de `packaging/licenses` e, no Windows, do `LICENSE.txt` do próprio Python); veja "Licenças nos executáveis" no CONTRIBUTING.md.
- `tools/send_demo.py` — impressão de exemplo, também usada pelos testes (`build_demo`, `qr_command`); `tools/smoke_test.py` — teste do executável compilado, rodado pelo release nos dois sistemas.
- `tests/` — `test_emulator.py` (parser, histórico, servidores), `test_lifecycle.py` (linha de comando, portas, encerramento), `test_logs.py` (destino e rotação do registro), `test_tray.py` (bandeja real, só no Windows) e `test_paper.cjs` (renderizador, com `node:test`).
- `.github/workflows/` — `tests.yml` roda os testes no Windows e no Linux com o Python 3.14 (o mínimo suportado e o dos executáveis), e a formatação e o ESLint uma vez, a cada push e pull request; `release.yml` publica a Release a cada tag `v*`.

## Convenções

- **Sem dependências Python**: só a biblioteca padrão. O build instala apenas o PyInstaller.
- **Banco**: o esquema é criado direto, sem migrações. Ao mudar a tabela, os bancos existentes podem ser apagados.
- **Versão**: constante `VERSION` em `emulator/server.py`; não repita o número em outro arquivo.
- **Escopo**: o emulador é genérico para sistemas que imprimem em EscBematech. O ACBr aparece só como exemplo de configuração e referência dos comandos, nunca como o sistema-alvo.
- Idiomas, nomes, espaçamento, comentários, termos e commits: siga o "Padrão de escrita" do CONTRIBUTING.md.

## Cuidados

- As portas são exclusivas no Windows (`SO_EXCLUSIVEADDRUSE`). Ao abrir uma segunda vez, o programa detecta a instância em execução pelo cabeçalho `Server` e só abre o histórico dela.
- O HTTP recusa `Host` que não seja IP ou `localhost` (proteção contra DNS rebinding), e o `DELETE` também valida a origem.
- Caminhos: `server.py` acha a página e o ícone ao lado do próprio pacote e as licenças em `PACKAGE_DIR.parent`. No executável, o PyInstaller extrai os recursos com a mesma disposição (`emulator/web`, `emulator/printer.ico`, licenças na raiz); ao mudar um caminho, ajuste os `--add-data` dos dois scripts de build. O histórico fica em `data/` ao lado do executável ou, pelos fontes, na raiz do projeto.
- O `.exe` em `outputs/windows/` não é atualizado sozinho: depois de mudar os fontes, rode o build.
- O `build.sh` usa o Python gerenciado do uv, compilado para glibc 2.17; trocar pelo Python do sistema faz o binário exigir a glibc da máquina de build, e o script falha na checagem final. Ele precisa de LF (garantido pelo `.gitattributes`). O `build.ps1` precisa de UTF-8 com BOM, senão o Windows PowerShell 5.1 estraga os acentos das mensagens.
- O `.exe` é de arquivo único e sem console: o lançador do PyInstaller fica entre o terminal e o Python e desliga o Ctrl+C. `ensure_console` usa o console do avô, religa o Ctrl+C e, com `--console`, abre janela própria. Mudanças nessa área precisam ser testadas no `.exe` compilado, não só pelos fontes.
- Testes de bandeja criam um ícone real por alguns instantes.
