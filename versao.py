# -*- coding: utf-8 -*-
"""Versao do app e de onde vem a atualizacao.

Suba um numero em VERSAO a cada release. O botao "Verificar atualizacao" compara este
numero com a tag da ultima release do repositorio, entao os dois tem que andar juntos:
release v1.1.0 no GitHub <-> VERSAO = "1.1.0" aqui dentro.
"""

VERSAO = "1.0.3"

# usuario/repositorio no GitHub. Vazio = o botao de atualizar fica desligado.
REPO = "raulpascolato/youtubefarm"

# O que NUNCA e' sobrescrito quando atualiza:
#   data  -> db.json, config.json (suas chaves), presets e capas
#   bin   -> o ffmpeg de 98 MB, que nao cabe no GitHub e nao muda
PROTEGIDOS = {"data", "bin", "__pycache__", ".git"}
