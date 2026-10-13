# Emulador EscBematech

Emulador simples de impressora térmica com um único protocolo: **EscBematech**. Funciona com qualquer sistema que imprima nesse padrão por rede; no ACBr, corresponde ao modelo `ppEscBematech`. Recebe impressões TCP/RAW na porta 9100 e mostra as impressões em http://127.0.0.1:9101. A largura é fixa em **48 colunas na fonte normal**; fonte condensada comporta 64 caracteres no mesmo papel.

## Executar no Windows

Após compilar esta versão, abra `outputs/EmuladorEscBematech.exe`: ele fica na bandeja do Windows, perto do relógio, sem manter uma janela de terminal. Dê duplo clique no ícone de impressora para abrir o histórico. Ao passar o mouse, a dica mostra a porta da impressora. O botão direito oferece **Abrir histórico** e **Sair**. Se o Windows esconder o ícone, procure na seta de ícones ocultos.

O executável inclui o Python e a página do histórico; não exige instalar Python. Pode ser copiado para outro Windows de 64 bits em uma pasta com permissão de escrita. O histórico fica em `data/history.sqlite3` ao lado do executável. Copie essa pasta junto ao programa para levar as impressões anteriores. A opção **Sair** para os servidores e salva os dados já recebidos de impressões em andamento. Erros de inicialização, como porta ocupada, aparecem em uma caixa de mensagem.

Para executar pelos fontes, use Python 3.10 ou superior nesta pasta:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python315\python.exe" server.py
```

Não há dependências Python a instalar. Para enviar um exemplo, em outro terminal:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python315\python.exe" tools\send_demo.py --qr
```

### Bandeja pelos fontes

Dê duplo clique em `start_tray.pyw` se os arquivos `.pyw` estiverem associados ao Python. Ou inicie sem terminal pelo PowerShell, na pasta do projeto:

```powershell
Start-Process -FilePath "$env:LOCALAPPDATA\Programs\Python\Python315\pythonw.exe" -ArgumentList start_tray.pyw -WorkingDirectory $PWD -WindowStyle Hidden
```

Também pode usar `python server.py --tray` para testar a bandeja mantendo o terminal aberto. `python server.py` continua em modo terminal, encerrado com Ctrl+C. O executável usa bandeja por padrão; `EmuladorEscBematech.exe --console` abre o modo terminal numa janela própria, encerrada com Ctrl+C. `--help` e `--licenses` escrevem no terminal de onde foram chamados; uma opção inválida aparece numa caixa de mensagem. Abrir o programa de novo enquanto ele já está em execução apenas abre o histórico da instância existente. Se a porta estiver ocupada por outro programa, a mensagem indica qual porta e sugere `--port` ou `--web-port`.

A bandeja usa a API nativa do Windows, sem novas bibliotecas. Não é adicionada inicialização automática com o Windows; o `LEIA-ME.txt` explica como criar um atalho na pasta `shell:startup`.

## Configurar o sistema que imprime

- Modelo: Bematech / EscBematech. No ACBr, `ACBrPosPrinter` com modelo `ppEscBematech`.
- Conexão TCP/RAW: `127.0.0.1:9100` quando está no mesmo computador. No ACBr, porta `TCP:127.0.0.1:9100`.
- Colunas da fonte normal: `48` (no ACBr, `ColunasFonteNormal`).
- Página de código: CP850 (padrão), CP437, CP860 ou UTF-8.

O emulador espera comandos nativos EscBematech. Configure o sistema que envia as impressões com esse modelo.

Referência dos comandos: [ACBrEscBematech.pas](https://sourceforge.net/p/acbr/code/HEAD/tree/trunk2/Fontes/ACBrSerial/ACBrEscBematech.pas), no repositório SVN oficial do Projeto ACBr.

Portas e banco alternativos, tanto nos fontes quanto no executável:

```powershell
python server.py --port 9102 --web-port 9103 --db data/teste.sqlite3
.\outputs\EmuladorEscBematech.exe --port 9102 --web-port 9103
```

Para receber de outro computador, use `--host 0.0.0.0` e configure o cliente com o IP local do emulador. O histórico deve ser aberto pelo IP (por exemplo `http://192.168.0.10:9101`) ou por `localhost`; nomes de máquina são recusados para impedir DNS rebinding. Pode ser necessário liberar as portas no Firewall. A interface não possui autenticação; destina-se a testes em uma rede controlada.

## Histórico

As impressões anteriores permanecem disponíveis após novas impressões e reinicializações. A chegada de uma nova impressão não troca a seleção atual. A busca considera o número e os primeiros 90 caracteres. Cada impressão pode ser baixada como imagem PNG, na resolução da impressora, e com os bytes originais (`.bin`); o nome do arquivo leva o número, a data e a hora da impressão, como `impressao-12_2026-10-13_19-35-19.png`, para não repetir depois de limpar o histórico. A página segue o tema claro ou escuro do Windows, e o botão de sol/lua no cabeçalho alterna entre eles.

Aberturas de gaveta aparecem na lista e nos detalhes com o número da gaveta e a duração do pulso, em vez de apenas “sem texto”. É o registro do comando recebido; o emulador não aciona uma gaveta física.

O botão **Limpar histórico** exclui todas as impressões após confirmação. Não há exclusão automática. Para backup, pare o servidor e copie `data/history.sqlite3`.

Um corte `ESC w` ou `ESC m` salva a impressão. Sem corte, salva ao encerrar a conexão ou após 60 segundos de inatividade. Uma conexão pode produzir várias impressões. O limite é de 10 MiB por conexão; ao excedê-lo a impressão é truncada com aviso. Encerrar abruptamente o processo pode perder uma impressão ainda não finalizada.

## Comandos e limites

Interpreta inicialização e seleção EscBema, texto, quebras, alinhamento, negrito (`ESC E/F`), itálico (`ESC 4/5`), sublinhado, fonte condensada (`ESC SI/H`), largura dupla (`ESC W`), altura dupla (`ESC d`), fonte normal (`ESC !`), espaçamento, página de código e cortes.

QR nativo `GS k Q` é renderizado em SVG na sequência da impressão, com níveis L/M/Q/H, tamanho de módulo recebido e margem branca de quatro módulos. Os bytes do conteúdo são preservados; a exibição é reduzida proporcionalmente se ultrapassar 40% da largura do papel, incluindo a margem branca. A matriz é gerada no navegador, com versão automática e codificação numérica, alfanumérica ou byte escolhida pelo conteúdo. Se o conteúdo exceder a capacidade do nível de correção, o QR é omitido e um aviso aparece nos detalhes.

As fontes e dimensões são aproximadas. As quebras respeitam células de caracteres e os espaços recebidos. Largura dupla reduz a quantidade de caracteres por linha; altura dupla não muda a largura. Não há seletor de perfil ou colunas.

Gaveta e beep são consumidos sem ação física. Imagens `ESC *`, logos `FS p` e códigos de barras não são renderizados e geram avisos. Não há modo página, USB, porta serial ou spooler Windows. Consultas de status são consumidas sem resposta; use envio RAW sem exigir confirmação de sensores. Comandos desconhecidos podem afetar os bytes seguintes. Novos comandos podem ser acrescentados conforme aparecerem nos testes com os sistemas que imprimem nele.

A geração QR usa o arquivo `web/qrcode.js` (qrcode-generator 2.0.4, MIT), servido junto com a página; funciona sem internet. As licenças estão em `THIRD-PARTY-NOTICES.txt`, também acessíveis com `--licenses`.

## Compilar e testar

Para gerar o executável, abra o PowerShell na pasta do projeto:

```powershell
.\build.ps1
```

O script cria um ambiente isolado, instala `requirements-build.txt` e gera `outputs/EmuladorEscBematech.exe`, copiando ao lado o `LEIA-ME.txt` com as instruções para quem vai usar. Python não é necessário nas máquinas que usam o executável; envie os dois arquivos juntos.

Antes de compilar, o script remove os arquivos temporários de `work/pyinstaller` e o cache local `work/pyinstaller-cache`, inclusive arquivos marcados como somente leitura. Não apaga fontes, histórico ou o executável anterior. Para apenas limpar, sem instalar dependências ou compilar, use `.\build.ps1 -CleanOnly`. Se houver um arquivo em uso, a limpeza interrompe com erro; feche o processo de compilação anterior e tente novamente. Encerre o emulador antes de compilar para permitir a substituição do `.exe`.

O script usa o lançador `py` quando ele está instalado, e o comando `python` caso contrário; assim não depende do atalho da Microsoft Store que o Windows coloca no PATH. Para escolher outra instalação, informe o caminho com `-Python`, por exemplo `.\build.ps1 -Python 'C:\Python312\python.exe'`. A primeira compilação precisa de acesso à internet para instalar as dependências.

Para executar os testes pelos fontes:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python315\python.exe" -m unittest discover -s tests -v
```

Os testes verificam fragmentação byte a byte, comandos Bematech, QR binário, cortes, recebimento TCP, API HTTP, limpeza e persistência. No Windows, também verificam o ícone nativo, as ações da bandeja e o encerramento com impressão pendente. Se tiver Node.js, `node tests/test_paper.cjs` verifica também a geometria do renderizador e a geração do QR; Node não é necessário para executar o emulador.

## Versão

A versão fica na constante `VERSION` do `server.py`, no formato `maior.menor.correção`: o último número sobe em correções, o do meio em recursos novos e o primeiro em mudanças grandes. Ela aparece no rodapé do histórico, em `EmuladorEscBematech.exe --version` e em Propriedades > Detalhes do executável, que o `build.ps1` preenche a partir da mesma constante. Cada versão publicada recebe uma tag `vX.Y.Z` no GitHub.

Para publicar uma versão, altere `VERSION`, faça o commit e envie a tag correspondente:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

O GitHub Actions (`.github/workflows/release.yml`) confere se a tag bate com `VERSION`, roda os testes, executa o `build.ps1` numa máquina Windows e cria uma Release com o `EmuladorEscBematech-X.Y.Z.zip`, que contém o `EmuladorEscBematech.exe` e o `LEIA-ME.txt`. O teste da bandeja é pulado lá, porque a máquina não tem área de trabalho interativa.

Além disso, `.github/workflows/tests.yml` roda os testes a cada push na `main` e em pull requests, sem gerar executável.

## Autor e licença

[Rodrigo Batistello](https://github.com/robatistello). Distribuído sob a licença MIT; veja [LICENSE](LICENSE).
