# Emulador EscBematech

Emulador simples de impressora térmica com um único protocolo: **EscBematech**. Funciona com qualquer sistema que imprima nesse padrão por rede; no ACBr, corresponde ao modelo `ppEscBematech`. Recebe impressões TCP/RAW na porta 9100 e mostra as impressões em http://127.0.0.1:9101. A largura é fixa em **48 colunas na fonte normal**; fonte condensada comporta 64 caracteres no mesmo papel.

## Executar no Windows

Após compilar esta versão, abra `outputs/EmuladorEscBematech.exe`: ele fica na bandeja do Windows, perto do relógio, sem manter uma janela de terminal. Dê duplo clique no ícone de impressora para abrir o histórico. Ao passar o mouse, a dica mostra a porta da impressora. O botão direito oferece **Abrir histórico** e **Sair**. Se o Windows esconder o ícone, procure na seta de ícones ocultos.

O executável inclui o Python e a página do histórico; não exige instalar Python. Roda no Windows 10 ou 11 de 64 bits (ou Windows Server 2016 em diante) e pode ser copiado para outro computador, numa pasta com permissão de escrita; o Python embutido não funciona no Windows 7 nem no 8. O histórico fica em `data/history.sqlite3` ao lado do executável. Copie essa pasta junto ao programa para levar as impressões anteriores. A opção **Sair** para os servidores e salva os dados já recebidos de impressões em andamento. Erros de inicialização, como porta ocupada, aparecem em uma caixa de mensagem.

Para executar pelos fontes, use Python 3.10 ou superior nesta pasta. Os comandos usam o lançador `py`, instalado junto com o Python do python.org; ele não depende do atalho da Microsoft Store que o Windows coloca no PATH no lugar de `python`:

```powershell
py server.py
```

Não há dependências Python a instalar. Para enviar um exemplo, em outro terminal:

```powershell
py tools\send_demo.py --qr
```

### Bandeja pelos fontes

Dê duplo clique em `start_tray.pyw` se os arquivos `.pyw` estiverem associados ao Python. Ou inicie sem terminal pelo PowerShell, na pasta do projeto:

```powershell
Start-Process -FilePath pyw -ArgumentList start_tray.pyw -WorkingDirectory $PWD -WindowStyle Hidden
```

Também pode usar `py server.py --tray` para testar a bandeja mantendo o terminal aberto. `py server.py` continua em modo terminal, encerrado com Ctrl+C. O executável usa bandeja por padrão; `EmuladorEscBematech.exe --console` abre o modo terminal numa janela própria, encerrada com Ctrl+C. `--help` e `--licenses` escrevem no terminal de onde foram chamados; uma opção inválida aparece numa caixa de mensagem. Abrir o programa de novo enquanto ele já está em execução apenas abre o histórico da instância existente. Se a porta estiver ocupada por outro programa, a mensagem indica qual porta e sugere `--port` ou `--web-port`.

A bandeja usa a API nativa do Windows, sem novas bibliotecas. Não é adicionada inicialização automática com o Windows; o [LEIA-ME-WINDOWS.txt](LEIA-ME-WINDOWS.txt) explica como criar um atalho na pasta `shell:startup`.

## Executar no Linux

Cada Release também traz `EmuladorEscBematech-X.Y.Z-linux.tar.gz`, com um executável para Linux de 64 bits (x86_64) que inclui o Python e roda em distribuições com glibc 2.17 ou mais nova (CentOS 7, Debian 11, Ubuntu 20.04 e posteriores). Não funciona no Alpine, que usa musl em vez de glibc, nem em ARM, como o Raspberry Pi; nesses casos, rode pelos fontes. Não há bandeja no Linux; o programa roda no terminal e encerra com Ctrl+C:

```bash
tar -xzf EmuladorEscBematech-*-linux.tar.gz
cd EmuladorEscBematech-*-linux
chmod +x EmuladorEscBematech
./EmuladorEscBematech
```

O `chmod` repõe a permissão de execução quando o pacote foi extraído por uma ferramenta do Windows. O histórico fica em `data/history.sqlite3` ao lado do executável; numa pasta sem permissão de escrita, use `--db`. As demais opções são as mesmas do Windows. Não há inicialização automática embutida; o [LEIA-ME-LINUX.txt](LEIA-ME-LINUX.txt), que vai no pacote com o nome `LEIA-ME.txt`, explica como rodar o emulador como serviço de usuário do systemd.

Pelos fontes, com Python 3.10 ou superior, basta `python3 server.py`. O executável Linux é gerado apenas pelo GitHub Actions; não há script de build local.

## Configurar o sistema que imprime

- Modelo: Bematech / EscBematech. No ACBr, `ACBrPosPrinter` com modelo `ppEscBematech`.
- Conexão TCP/RAW: `127.0.0.1:9100` quando está no mesmo computador. No ACBr, porta `TCP:127.0.0.1:9100`.
- Colunas da fonte normal: `48` (no ACBr, `ColunasFonteNormal`).
- Página de código: CP850 (padrão), CP437, CP860 ou UTF-8.

O emulador espera comandos nativos EscBematech. Configure o sistema que envia as impressões com esse modelo.

Referência dos comandos: [ACBrEscBematech.pas](https://sourceforge.net/p/acbr/code/HEAD/tree/trunk2/Fontes/ACBrSerial/ACBrEscBematech.pas), no repositório SVN oficial do Projeto ACBr.

Portas e banco alternativos, tanto nos fontes quanto no executável:

```powershell
py server.py --port 9102 --web-port 9103 --db data/teste.sqlite3
.\outputs\EmuladorEscBematech.exe --port 9102 --web-port 9103
```

Para receber de outro computador, use `--host 0.0.0.0` e configure o cliente com o IP local do emulador. O histórico deve ser aberto pelo IP (por exemplo `http://192.168.0.10:9101`) ou por `localhost`; nomes de máquina são recusados para impedir DNS rebinding. Pode ser necessário liberar as portas no Firewall. A interface não possui autenticação; destina-se a testes em uma rede controlada.

## Histórico

As impressões anteriores permanecem disponíveis após novas impressões e reinicializações. A chegada de uma nova impressão não troca a seleção atual, a menos que **Mostrar novas impressões automaticamente** esteja marcado; nesse caso, a mais recente é selecionada sozinha, exceto as que são só abertura de gaveta, para que a gaveta enviada logo depois do cupom não esconda a impressão. A escolha fica salva no navegador. Com a aba do histórico em segundo plano, o título mostra quantas impressões chegaram, como “(2) Emulador EscBematech”, e o ícone da aba ganha um ponto vermelho; os dois voltam ao normal ao abrir a aba. Em abas esquecidas por vários minutos, o navegador espaça as consultas e o aviso pode levar até um minuto. A busca considera o número e os primeiros 90 caracteres; `#10` encontra só a impressão 10. Cada impressão pode ser baixada como imagem PNG, na resolução da impressora, e com os bytes originais (`.bin`); o nome do arquivo leva o número, a data e a hora da impressão, como `impressao-12_2026-10-13_19-35-19.png`, para não repetir depois de limpar o histórico. A página segue o tema claro ou escuro do Windows, e o botão de sol/lua no cabeçalho alterna entre eles.

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

O script cria um ambiente isolado, instala `requirements-build.txt` e gera `outputs/EmuladorEscBematech.exe`, copiando ao lado, com o nome `LEIA-ME.txt`, o [LEIA-ME-WINDOWS.txt](LEIA-ME-WINDOWS.txt) com as instruções para quem vai usar. Python não é necessário nas máquinas que usam o executável; envie os dois arquivos juntos.

Antes de compilar, o script remove os arquivos temporários de `work/pyinstaller` e o cache local `work/pyinstaller-cache`, inclusive arquivos marcados como somente leitura. Não apaga fontes, histórico ou o executável anterior. Para apenas limpar, sem instalar dependências ou compilar, use `.\build.ps1 -CleanOnly`. Se houver um arquivo em uso, a limpeza interrompe com erro; feche o processo de compilação anterior e tente novamente. Encerre o emulador antes de compilar para permitir a substituição do `.exe`.

O script usa o lançador `py` quando ele está instalado, e o comando `python` caso contrário; assim não depende do atalho da Microsoft Store que o Windows coloca no PATH. Para escolher outra instalação, informe o caminho com `-Python`, por exemplo `.\build.ps1 -Python 'C:\Python312\python.exe'`. A primeira compilação precisa de acesso à internet para instalar as dependências.

Para executar os testes pelos fontes:

```powershell
py -m unittest discover -s tests -v
```

Os testes verificam fragmentação byte a byte, comandos Bematech, QR binário, cortes, recebimento TCP, API HTTP, limpeza e persistência. No Windows, também verificam o ícone nativo, as ações da bandeja e o encerramento com impressão pendente. Se tiver Node.js, `node tests/test_paper.cjs` verifica também a geometria do renderizador e a geração do QR; Node não é necessário para executar o emulador.

## Versão

A versão fica na constante `VERSION` do `server.py`, no formato `maior.menor.correção`: o último número sobe em correções, o do meio em recursos novos e o primeiro em mudanças grandes. Ela aparece no rodapé do histórico, em `EmuladorEscBematech.exe --version` e em Propriedades > Detalhes do executável, que o `build.ps1` preenche a partir da mesma constante. Cada versão publicada recebe uma tag `vX.Y.Z` no GitHub.

Para publicar uma versão, altere `VERSION`, faça o commit e envie a tag correspondente:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

O GitHub Actions (`.github/workflows/release.yml`) confere se a tag bate com `VERSION`, roda os testes e compila nos dois sistemas. No Windows, executa o `build.ps1` e gera o `EmuladorEscBematech-X.Y.Z-windows.zip`, com o `EmuladorEscBematech.exe` e o `LEIA-ME.txt`. No Linux, compila com o Python do [uv](https://docs.astral.sh/uv/), feito para glibc 2.17, para que o executável não exija uma distribuição tão nova quanto a máquina do GitHub; antes de empacotar o `EmuladorEscBematech-X.Y.Z-linux.tar.gz`, abre o executável, envia a impressão de exemplo e confere que ela chegou ao histórico. A Release só é criada se os dois lados passarem. O teste da bandeja é pulado lá, porque a máquina não tem área de trabalho interativa.

Além disso, `.github/workflows/tests.yml` roda os testes no Windows e no Linux a cada push na `main` e em pull requests, sem gerar executável.

## Autor e licença

[Rodrigo Batistello](https://github.com/robatistello). Distribuído sob a licença MIT; veja [LICENSE](LICENSE).
