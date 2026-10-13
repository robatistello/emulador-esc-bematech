"""Atalho pelos fontes: duplo clique ou pythonw, sem janela de terminal."""
import sys
from server import main

if __name__ == "__main__":
    raise SystemExit(main(["--tray", *sys.argv[1:]]))
