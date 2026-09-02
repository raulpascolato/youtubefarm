# -*- coding: utf-8 -*-
"""Remendos de janela no Win32 puro.

Por que existe: numa janela sem moldura o WebView2 volta EM BRANCO depois de minimizar
(vale pro botao do app, pro Win+D e pro clique na taskbar — e' do WebView2, nao do botao).
Medido: janela normal = 130 cores distintas; depois de restaurar = 1 cor (branco);
depois de um resize de 1px = 130 cores de novo. Entao o conserto e' forcar um relayout.

Tudo aqui e' user32 via ctypes de proposito: as funcoes do user32 podem ser chamadas de
qualquer thread, enquanto tocar em win.native (winforms/COM) fora da UI thread trava.
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time

u32 = ctypes.windll.user32

SW_MINIMIZE = 6
SW_RESTORE = 9
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SEM_MEXER = SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE


def hwnd_do_processo(pid, limite=20.0):
    """Acha a janela visivel do nosso processo. Nao usa win.native (que trava fora da UI thread)."""
    fim = time.time() + limite
    while time.time() < fim:
        achados = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def visitar(h, _):
            dono = wt.DWORD()
            u32.GetWindowThreadProcessId(h, ctypes.byref(dono))
            if dono.value == pid and u32.IsWindowVisible(h):
                r = wt.RECT()
                u32.GetWindowRect(h, ctypes.byref(r))
                if (r.right - r.left) > 100 and (r.bottom - r.top) > 100:
                    achados.append(h)
            return True

        u32.EnumWindows(visitar, 0)
        if achados:
            return achados[0]
        time.sleep(0.2)
    return None


def empurrao(hwnd):
    """Cresce 1px e volta: obriga o WebView2 a refazer o layout e repintar."""
    r = wt.RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(r)):
        return
    w, h = r.right - r.left, r.bottom - r.top
    u32.SetWindowPos(hwnd, 0, 0, 0, w + 1, h, SEM_MEXER)
    u32.SetWindowPos(hwnd, 0, 0, 0, w, h, SEM_MEXER)


def minimizar(hwnd):
    u32.ShowWindow(hwnd, SW_MINIMIZE)


def vigiar_repaint(hwnd, parar):
    """Enquanto a janela viver: toda vez que sair de minimizada, da' o empurrao."""
    estava = False
    while not parar.is_set() and u32.IsWindow(hwnd):
        agora = bool(u32.IsIconic(hwnd))
        if estava and not agora:
            time.sleep(0.25)      # deixa o Windows terminar de restaurar
            empurrao(hwnd)
        estava = agora
        time.sleep(0.25)


def iniciar_vigia(pid):
    """Sobe o vigia em background. Devolve (thread, evento_de_parada, hwnd)."""
    hwnd = hwnd_do_processo(pid)
    if not hwnd:
        return None, None, None
    parar = threading.Event()
    t = threading.Thread(target=vigiar_repaint, args=(hwnd, parar), daemon=True)
    t.start()
    return t, parar, hwnd
