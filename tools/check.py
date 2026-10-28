"""Roda de uma vez o que o CI confere: testes, formatação e análise do código."""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# As mesmas versões do CI; ao atualizar, veja "Dependências do desenvolvimento" no CONTRIBUTING.md.
RUFF = "ruff@0.17.3"
PRETTIER = "prettier@3.9.10"
ESLINT = "eslint@10.13.0"

PRETTIER_FILES = ("emulator/web", "tests/test_paper.cjs", "eslint.config.mjs")
ESLINT_FILES = ("emulator/web", "tests/test_paper.cjs")


def ruff_command():
    # Sem o uv, vale o Ruff instalado pelo pip no próprio Python.
    if not shutil.which("uvx") and importlib.util.find_spec("ruff"):
        return [sys.executable, "-m", "ruff"]

    return ["uvx", "-q", RUFF]


def fix_steps():
    ruff = ruff_command()

    return [
        ("Formatação do Python", [*ruff, "format"]),
        ("Correções automáticas do Python", [*ruff, "check", "--fix"]),
        ("Formatação da página", ["npx", "--yes", PRETTIER, "--write", *PRETTIER_FILES]),
    ]


def check_steps():
    ruff = ruff_command()

    return [
        ("Testes Python", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
        ("Testes do renderizador", ["node", "tests/test_paper.cjs"]),
        ("Formatação do Python", [*ruff, "format", "--check"]),
        ("Análise do Python", [*ruff, "check"]),
        ("Formatação da página", ["npx", "--yes", PRETTIER, "--check", *PRETTIER_FILES]),
        ("Análise do JavaScript", ["npx", "--yes", ESLINT, *ESLINT_FILES]),
    ]


def run_step(name, command):
    print(f"\n== {name}", flush=True)

    # No Windows, npx e uvx são scripts .cmd que o subprocess só encontra pelo caminho completo.
    executable = shutil.which(command[0])
    if executable is None:
        print(f'{command[0]} não encontrado. Veja a seção "Ambiente" do CONTRIBUTING.md.')
        return False

    environment = {**os.environ, "PYTHONUTF8": "1"}
    result = subprocess.run([executable, *command[1:]], cwd=ROOT, env=environment, check=False)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Roda os testes, a formatação e a análise do código, como o CI.")
    parser.add_argument(
        "--fix", action="store_true", help="Formata e aplica as correções automáticas antes de conferir"
    )
    arguments = parser.parse_args()

    steps = (fix_steps() if arguments.fix else []) + check_steps()
    failed = [name for name, command in steps if not run_step(name, command)]

    if failed:
        print(f"\nFalhou: {', '.join(failed)}.")
        return 1

    print("\nTudo certo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
