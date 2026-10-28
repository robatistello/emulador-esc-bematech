#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null; then
    echo "O uv não foi encontrado. Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi
if ! command -v objdump >/dev/null; then
    echo "O objdump não foi encontrado. Instale o pacote binutils." >&2
    exit 1
fi
if [ -L work ]; then
    echo "A pasta work é um link; limpeza cancelada." >&2
    exit 1
fi

# Pastas próprias do Linux: a mesma cópia do projeto pode ser compilada
# pelo Windows e pelo WSL, e uma não deve apagar o ambiente da outra.
venv=.venv-build-linux
work=work/linux
dist=outputs/linux
rm -rf "$work"
export PYINSTALLER_CONFIG_DIR="$PWD/$work/pyinstaller-cache"

version=$(tr -d '\r' < server.py | sed -n 's/^VERSION = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p')
if [ -z "$version" ]; then
    echo "VERSION não encontrada em server.py." >&2
    exit 1
fi

# O Python gerenciado do uv é compilado para glibc 2.17; com o Python do
# sistema, o binário só abriria em distribuições tão novas quanto esta máquina.
uv python install 3.14
uv venv --allow-existing --managed-python --python 3.14 "$venv"
uv pip install --python "$venv/bin/python" -r requirements-build.txt

"$venv/bin/python" -m PyInstaller --noconfirm --clean --onefile --name EmuladorEscBematech \
    --add-data "$PWD/web:web" --add-data "$PWD/THIRD-PARTY-NOTICES.txt:." \
    --distpath "$dist" --workpath "$work/pyinstaller" --specpath "$work" server.py
cp LEIA-ME-LINUX.txt "$dist/LEIA-ME.txt"

"$venv/bin/python" - "$dist/EmuladorEscBematech" "$work/libs" <<'PY'
import pathlib, sys
from PyInstaller.archive.readers import CArchiveReader
archive, target = CArchiveReader(sys.argv[1]), pathlib.Path(sys.argv[2])
target.mkdir(parents=True, exist_ok=True)
for name in archive.toc:
    if name.endswith(".so") or ".so." in name:
        (target / pathlib.Path(name).name).write_bytes(archive.extract(name))
PY
required=$(for file in "$dist/EmuladorEscBematech" "$work"/libs/*; do objdump -T "$file"; done \
    | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1)
if [ "$(printf '%s\n' GLIBC_2.17 "$required" | sort -V | tail -1)" != GLIBC_2.17 ]; then
    echo "O executável exige $required; o máximo aceito é GLIBC_2.17." >&2
    exit 1
fi

echo "Pronto: $PWD/$dist/EmuladorEscBematech $version e LEIA-ME.txt (exige $required)"
