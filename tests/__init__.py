"""
Pacote de testes.

Duas variaveis de ambiente sao fixadas ANTES de qualquer import do
backend, porque config.py as le na importacao:

- PBKDF2_ITERATIONS baixo: o seed cria dezenas de usuarios por teste e,
  com as 600 mil iteracoes de producao, a suite levaria mais de meia
  hora so em hashing. O hash legado e o rehash no login sao testados a
  parte, em test_auth.py, com o numero real.
- API_DOCS desligado: o .env de desenvolvimento pode liga-lo, e os testes
  conferem o padrao seguro (documentacao fora do ar).
"""

import os

os.environ.setdefault("PBKDF2_ITERATIONS", "1000")
os.environ.setdefault("API_DOCS", "false")
