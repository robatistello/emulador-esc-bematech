# CLAUDE.md

Emulador de impressora térmica que recebe comandos **EscBematech** de qualquer sistema que imprima nesse padrão (no ACBr, modelo `ppEscBematech`) via TCP/RAW e mostra cada impressão num histórico web. Roda no Windows, na bandeja ou no terminal. Detalhes de uso estão no [README.md](README.md).

## Comandos

```powershell
python server.py                         # modo terminal (impressora 9100, histórico http://127.0.0.1:9101)
python server.py --tray                  # modo bandeja, mantendo o terminal
python tools/send_demo.py --qr           # envia uma impressão de exemplo
python -m unittest discover -s tests -v  # testes Python
node tests/test_paper.cjs                # testes do renderizador e do QR
.\build.ps1                              # gera outputs/EmuladorEscBematech.exe e copia o LEIA-ME-WINDOWS.txt como LEIA-ME.txt
```

Rode sempre os dois conjuntos de testes: o teste Node não faz parte do `unittest`.

## Arquitetura

- `escpos.py` — `Parser` incremental: enquadra os bytes em comandos (aceita pacotes TCP fragmentados), mantém o estado de estilo e chama `save(job)` a cada corte (`ESC w`/`ESC m`) ou ao fechar a conexão. O job é um dict com `lines`, `events`, `warnings` e `raw_base64`.
- `server.py` — servidor TCP (`PrinterServer`), servidor HTTP (`WebServer`), histórico SQLite (`History`, tabela `jobs`) e `main`. Rotas: `/`, `/paper.js`, `/qrcode.js`, `GET /api/jobs`, `GET /api/jobs/<id>` e `DELETE /api/jobs`. `GET /api/jobs` envia `ETag` (número e data da última impressão) e responde 304 quando a lista não mudou.
- `web/paper.js` — layout e renderização em SVG com células fixas de 48 colunas; gera a matriz do QR a partir de `data_base64` e exporta o papel como PNG (`paperPng`).
- `web/index.html` — página do histórico; consulta `/api/jobs` a cada 2 segundos. Com a aba em segundo plano, conta as impressões novas no título e põe um ponto no ícone (SVG gerado na própria página). A opção "Mostrar novas impressões automaticamente" seleciona a mais recente, pulando as que são só abertura de gaveta, e também fica em `localStorage`. O tema claro/escuro segue o sistema, e a escolha manual fica em `localStorage`.
- `tray.py` — ícone da bandeja via API Win32 com `ctypes`. `start_tray.pyw` inicia a bandeja pelos fontes, sem terminal.
- `tests/` — testes Python (`unittest`) e do renderizador (Node). Os módulos Python ficam na raiz para manter as importações simples.
- `tools/send_demo.py` — envia uma impressão de exemplo sem precisar de um sistema emissor; os testes usam `build_demo` e `qr_command`.
- `.github/workflows/tests.yml` — roda os testes Python e Node no Windows e no Linux a cada push na `main` e em pull requests.
- `.github/workflows/release.yml` — ao enviar uma tag `v*`, confere a tag com `VERSION` e, em jobs paralelos, roda os testes e compila: no Windows com `build.ps1` (zip com o `.exe` e o `LEIA-ME-WINDOWS.txt`); no Linux com PyInstaller sobre o Python do uv, testando o binário antes de empacotar o tar.gz com o `LEIA-ME-LINUX.txt`. Nos dois pacotes, o arquivo se chama `LEIA-ME.txt`. Um último job publica a Release com os dois pacotes.
- `web/qrcode.js` — biblioteca de terceiros (qrcode-generator 2.0.4, MIT). Não edite; para atualizar, substitua o arquivo inteiro e ajuste `THIRD-PARTY-NOTICES.txt`.

## Convenções

- **Sem dependências Python**: só a biblioteca padrão. O build instala apenas o PyInstaller.
- **Idiomas**: identificadores em inglês; interface, mensagens, comentários, README e mensagens de commit em português.
- **Público**: o emulador é genérico para sistemas que imprimem em EscBematech. Cite o ACBr só como exemplo de configuração ou referência dos comandos, nunca como o sistema-alvo, e não cite sistemas específicos que o usam.
- **Termos**: cada envio é uma *impressão* na interface e um `job` no código. Não use "recibo"/`receipt`; nem todo envio é recibo (gaveta, relatórios, DANFE).
- **Comentários**: só quando explicam um porquê que o código não mostra (protocolo, peculiaridades do Windows, segurança). Não descreva o que o código faz nem o histórico das mudanças.
- **Banco**: o esquema é criado direto, sem migrações. Ao mudar a tabela, os bancos existentes podem ser apagados.
- **Versão**: constante `VERSION` no `server.py` (`maior.menor.correção`); página, `--version`, cabeçalho `Server` e propriedades do `.exe` leem dela. Não repita o número em outro arquivo.
- **Commits**: prefixo convencional (`feat:`, `fix:`, `refactor:`) e corpo explicando o porquê.

## Cuidados

- As portas são exclusivas no Windows (`SO_EXCLUSIVEADDRUSE`). Ao abrir uma segunda vez, o programa detecta a instância em execução pelo cabeçalho `Server` e só abre o histórico dela.
- O HTTP recusa `Host` que não seja IP ou `localhost` (proteção contra DNS rebinding), e o `DELETE` também valida a origem.
- O `.exe` em `outputs/` não é atualizado sozinho: depois de mudar os fontes, rode `.\build.ps1`.
- O binário Linux só é gerado no GitHub Actions. O build usa o Python gerenciado do uv (`--managed-python`), compilado para glibc 2.17; trocar pelo Python do sistema ou do `setup-python` faz o binário exigir a glibc do runner. A bandeja só existe no Windows: fora dele, o executável abre em modo terminal.
- Testes de bandeja só rodam no Windows e criam um ícone real por alguns instantes.
- O `.exe` é de arquivo único e sem console: o lançador do PyInstaller fica entre o terminal e o Python e desliga o Ctrl+C. `ensure_console` usa o console do avô, religa o Ctrl+C e, com `--console`, abre janela própria. Mudanças nessa área precisam ser testadas no `.exe` compilado, não só pelos fontes.
