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
    """Onde caem os arquivos de cada video (audio, srt, prompts, o mp4 final).
    Fica na area de trabalho de proposito: esses arquivos voce abre e usa por fora."""
    return Path.home() / "Desktop" / "YOUTUBE FARM - videos"
