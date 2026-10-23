"""Permite executar ``python -m sonarfuzzy`` sem instalar o pacote."""

from .cli import main


if __name__ == '__main__':
    raise SystemExit(main())
