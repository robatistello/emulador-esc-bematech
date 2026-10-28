#!/usr/bin/env bash
# Gera o executável Linux em outputs/linux, com o LEIA-ME.txt ao lado.
set -euo pipefail

packaging_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(dirname "$packaging_dir")"
package_dir="$project_root/emulator"

# Pastas próprias do Linux: a mesma cópia do projeto pode ser compilada
# pelo Windows e pelo WSL, e uma não deve apagar o ambiente da outra.
venv="$project_root/.venv-build-linux"
work="$project_root/work/linux"
dist="$project_root/outputs/linux"
max_glibc=GLIBC_2.17

fail() {
    echo "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null || fail "$2"
}

read_version() {
    tr -d '\r' <"$package_dir/server.py" | sed -n 's/^VERSION = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p'
}

prepare_environment() {
    # O Python gerenciado do uv é compilado para glibc 2.17; com o Python do
    # sistema, o binário só abriria em distribuições tão novas quanto esta máquina.
    uv python install 3.14
    uv venv --allow-existing --managed-python --python 3.14 "$venv"
    uv pip install --python "$venv/bin/python" -r "$packaging_dir/requirements-build.txt"
}

build_executable() {
    export PYINSTALLER_CONFIG_DIR="$work/pyinstaller-cache"

    "$venv/bin/python" -m PyInstaller \
        --noconfirm --clean --onefile \
        --name EmuladorEscBematech \
        --paths "$project_root" \
        --add-data "$package_dir/web:emulator/web" \
        --add-data "$project_root/THIRD-PARTY-NOTICES.txt:." \
        --distpath "$dist" \
        --workpath "$work/pyinstaller" \
        --specpath "$work" \
        "$package_dir/__main__.py"

    cp "$packaging_dir/LEIA-ME-LINUX.txt" "$dist/LEIA-ME.txt"
}

required_glibc() {
    "$venv/bin/python" - "$dist/EmuladorEscBematech" "$work/libs" <<'PY'
import pathlib
import sys

from PyInstaller.archive.readers import CArchiveReader

archive = CArchiveReader(sys.argv[1])
target = pathlib.Path(sys.argv[2])
target.mkdir(parents=True, exist_ok=True)

for name in archive.toc:
    if name.endswith(".so") or ".so." in name:
        (target / pathlib.Path(name).name).write_bytes(archive.extract(name))
PY

    for file in "$dist/EmuladorEscBematech" "$work"/libs/*; do
        objdump -T "$file"
    done | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1
}

require_command uv "O uv não foi encontrado. Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh"
require_command objdump "O objdump não foi encontrado. Instale o pacote binutils."
[ -L "$project_root/work" ] && fail "A pasta work é um link; limpeza cancelada."

version="$(read_version)"
[ -n "$version" ] || fail "VERSION não encontrada em emulator/server.py."

rm -rf "$work"
prepare_environment
build_executable

required="$(required_glibc)"
if [ "$(printf '%s\n' "$max_glibc" "$required" | sort -V | tail -1)" != "$max_glibc" ]; then
    fail "O executável exige $required; o máximo aceito é $max_glibc."
fi

echo "Pronto: $dist/EmuladorEscBematech $version e LEIA-ME.txt (exige $required)"
