# -*- coding: utf-8 -*-
"""Onde ler e onde escrever.

Tudo mora ao lado dos .py: static/, data/ e bin/. O app roda pelo YOUTUBE FARM.bat,
nao existe versao empacotada — por isso aqui nao ha' nada de PyInstaller.
"""
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def dir_app():
    """A pasta do programa: static/, bin/."""
    return RAIZ


def dir_dados():
    """O que o app escreve: data/ (config, db, presets, capas)."""
    return RAIZ


def ffmpeg():
    """O ffmpeg de bin/. Se nao estiver la', tenta o que estiver instalado no sistema.

    Ele nao vem junto com o projeto: tem 98 MB e o GitHub corta em 100 MB por arquivo.
    O LEIA.txt explica como baixar e onde por.
    """
    embutido = RAIZ / "bin" / "ffmpeg.exe"
    if embutido.exists():
        return str(embutido)
    return shutil.which("ffmpeg") or "ffmpeg"


def tem_ffmpeg():
    try:
        r = subprocess.run([ffmpeg(), "-version"], capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


def dir_saida():
    """Onde ficam os arquivos de TRABALHO de cada video (audio, srt, prompts, imagens,
    o mp4 montado). Dentro do app, em data/videos: antes era uma pasta na area de
    trabalho, que enchia de lixo. O video pronto o usuario salva onde quiser (o app
    pergunta), e apagar o video no app apaga a pasta dele daqui."""
    return RAIZ / "data" / "videos"
