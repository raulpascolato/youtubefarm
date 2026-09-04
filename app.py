# -*- coding: utf-8 -*-
"""YOUTUBE FARM — janela nativa, sem borda.

Nao abre navegador: sobe a API em 127.0.0.1 numa thread e desenha tudo dentro de uma
janela WebView2 sem moldura do Windows. A barra de titulo (arrastar / minimizar /
fechar) e' desenhada pelo proprio app, no HTML.

ATENCAO A ORDEM DOS IMPORTS AQUI. So' entra biblioteca padrao no topo. Tudo que vem de
fora (uvicorn, webview) e os modulos do proprio app entram DEPOIS, dentro do try — se
um deles falhar com o import solto la' em cima, o erro acontece antes do try/except do
final e o app morre calado: sem janela, sem erro.txt, sem nada. Foi o que aconteceu.
"""
import json
import os
import socket
import threading
import time
import traceback
import webbrowser
from pathlib import Path

LARGURA, ALTURA = 430, 800
MINIMO = (360, 560)


def _aviso(titulo, texto):
    """Sem console, um erro nao aparece em lugar nenhum: a pessoa clica e nada acontece.
    Entao qualquer falha vira uma caixa de dialogo do Windows."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, texto, titulo, 0x10)
    except Exception:
        print(texto)


def _pasta():
    """A pasta do app SEM depender do caminhos.py — ele mesmo pode ser o que falhou."""
    return Path(__file__).resolve().parent


try:
    import uvicorn
    import webview

    import janela_win32 as jw
except Exception:
    _detalhe = traceback.format_exc()
    try:
        (_pasta() / "erro.txt").write_text(
            "faltou instalar as dependencias do python\n\n"
            "o que fazer\n\n"
            "fecha isso e abre pelo \"youtube farm.bat\".\n"
            "ele instala sozinho.\n\n\n"
            + "-" * 60 + "\ndetalhe tecnico, so pra quem for arrumar\n\n" + _detalhe,
            encoding="utf-8")
    except Exception:
        pass
    _aviso("YOUTUBE FARM",
           "faltou instalar as dependencias do python\n\n"
           "fecha isso e abre pelo \"youtube farm.bat\".\nele instala sozinho.\n\n"
           "(o detalhe ficou no arquivo erro.txt, na pasta do app)")
    raise


def porta_livre(preferida):
    for p in [preferida] + list(range(preferida + 1, preferida + 30)):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return preferida


def esperar_no_ar(port, limite=25.0):
    fim = time.time() + limite
    while time.time() < fim:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


class Janela:
    """Exposto pro front como window.pywebview.api — a moldura e' nossa, os botoes tambem.

    ATENCAO: a referencia da janela TEM que ser privada (_win). O pywebview serializa
    todo atributo publico deste objeto pra expor ao JS; num atributo publico ele desce
    recursivamente pelo objeto Window (win.native.AccessibilityObject.Bounds.Empty...)
    ate estourar a pilha, e ainda toca membros COM do WebView2 fora da UI thread.
    """

    def __init__(self):
        self._win = None
        self._hwnd = None

    def ligar(self, win, hwnd):
        self._win = win
        self._hwnd = hwnd

    def minimizar(self):
        # pelo Win32, nao pelo pywebview: mexer no WindowState daqui (thread do bridge)
        # e' o caminho que trava. O vigia cuida do repaint quando restaurar.
        if self._hwnd:
            jw.minimizar(self._hwnd)

    def escolher_arquivo(self, filtro="Vídeo (*.mp4;*.mov;*.mkv)"):
        """Dialogo NATIVO do Windows. O <input type=file> do HTML nao serve aqui: por
        seguranca o navegador esconde o caminho real, e o avatar.mp4 tem centenas de MB —
        mandar o conteudo pro servidor seria absurdo. Aqui a gente so' guarda o caminho."""
        if not self._win:
            return ""
        r = self._win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                         file_types=(filtro, "Todos (*.*)"))
        return (r[0] if isinstance(r, (list, tuple)) and r else r) or ""

    def abrir_link(self, url):
        """Abre no navegador do sistema. Um <a href> comum trocaria a INTERFACE do app
        pela pagina e o usuario ficaria preso, sem barra de endereco pra voltar."""
        u = (url or "").strip()
        if u.startswith(("http://", "https://")):
            webbrowser.open(u)
            return True
        return False

    def escolher_pasta(self):
        if not self._win:
            return ""
        r = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        return (r[0] if isinstance(r, (list, tuple)) and r else r) or ""

    def fechar(self):
        # destroy() NAO pode rodar dentro do handler do bridge: o pywebview fica esperando
        # a chamada JS retornar enquanto a janela e' destruida, e trava sem erro nenhum.
        # Agenda numa thread solta e devolve o controle pro JS na hora.
        if self._win:
            threading.Timer(0.05, self._win.destroy).start()


def main():
    try:
        cfg = json.loads((_pasta() / "data" / "config.json").read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    port = porta_livre(int(cfg.get("port") or 8777))

    import server  # importa o objeto direto (import por string quebra dentro do .exe)

    threading.Thread(
        target=uvicorn.run,
        args=(server.app,),
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "warning"},
        daemon=True,
    ).start()
    esperar_no_ar(port)

    api = Janela()
    janela = webview.create_window(
        "YOUTUBE FARM",
        f"http://127.0.0.1:{port}",
        width=LARGURA,
        height=ALTURA,
        min_size=MINIMO,
        frameless=True,      # sem a moldura do Windows
        easy_drag=False,     # so' arrasta pela barra (senao atrapalha rolagem e clique)
        resizable=True,
        js_api=api,
    )

    def ligar_vigia():
        # o hwnd so' existe depois que a janela aparece; buscamos pelo PID porque
        # ler janela.native fora da UI thread trava o processo.
        _, _, hwnd = jw.iniciar_vigia(os.getpid())
        api.ligar(janela, hwnd)

    threading.Thread(target=ligar_vigia, daemon=True).start()

    webview.start()
    os._exit(0)              # derruba a thread do uvicorn junto com a janela


# os modulos que fazem parte do app — se um deles falta, e' arquivo, nao dependencia
MEUS = {"app", "server", "montador", "roteirista", "diretor", "estilo",
        "card", "store", "tts", "caminhos", "janela_win32", "versao"}


def _diagnostico(detalhe):
    """Traduz o tombo do Python pra uma frase que a pessoa entende.

    Devolve (o que houve, o que fazer). O traceback cru fica no fim do erro.txt,
    pra quem for consertar — mas nao e' a primeira coisa que se ve'.
    """
    d = detalhe.lower()
    if "no module named" in d:
        falta = detalhe.split("No module named")[-1].strip().strip("'\"\n )")
        if falta in MEUS:
            return (f"esta faltando o arquivo {falta}.py na pasta do app",
                    "a copia esta incompleta. baixa o projeto inteiro de novo\n"
                    "(no github: botao verde Code > Download ZIP) e extrai por cima.\n"
                    "as suas pastas data e bin nao vem no zip, entao nao se perde nada.")
        return (f"faltou instalar uma coisa do python ({falta})",
                "fecha isso e abre pelo \"youtube farm.bat\".\n"
                "ele instala sozinho na primeira vez.")
    if "webview" in d or "clr" in d or "edgechromium" in d:
        return ("nao consegui abrir a janela do app",
                "provavelmente falta o microsoft edge webview2 nesta maquina.\n"
                "baixa em: developer.microsoft.com/microsoft-edge/webview2")
    if "10048" in d or "address" in d and "use" in d:
        return ("o app ja esta aberto",
                "procura a janela dele na barra de tarefas.\n"
                "se nao achar, reinicia o computador e tenta de novo.")
    if "permission" in d or "acesso negado" in d or "winerror 5" in d:
        return ("o windows bloqueou o acesso a um arquivo",
                "tira a pasta de dentro de Arquivos de Programas,\n"
                "ou de qualquer lugar que peca permissao de administrador.")
    return ("o app nao conseguiu abrir",
            "manda o texto la de baixo pra quem cuida do programa.")


def _gravar_erro(detalhe):
    houve, fazer = _diagnostico(detalhe)
    texto = (f"{houve}\n\n"
             f"o que fazer\n\n"
             f"{fazer}\n\n\n"
             f"{'-' * 60}\n"
             f"detalhe tecnico, so pra quem for arrumar\n\n"
             f"{detalhe}")
    try:
        (_pasta() / "erro.txt").write_text(texto, encoding="utf-8")
    except Exception:
        pass
    return houve, fazer

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        detalhe = traceback.format_exc()
        houve, fazer = _gravar_erro(detalhe)
        _aviso("YOUTUBE FARM", f"{houve}\n\n{fazer}\n\n"
                               "(o detalhe ficou no arquivo erro.txt, na pasta do app)")
        raise
