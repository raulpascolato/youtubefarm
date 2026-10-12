# -*- coding: utf-8 -*-
"""O Claude do app e' o Claude Code instalado no PC, logado na conta do usuario.

Substituiu a API (chave sk-ant, cobranca por uso): o roteiro e a direcao gastam o
limite do plano do Claude (Pro/Max) da conta que estiver logada. O login fica salvo
pelo proprio Claude Code em ~/.claude, entao depois de entrar uma vez o app abre sempre
conectado.

Cada chamada roda `claude -p` sem ferramentas e em modo seguro: o Claude Code aqui e'
so' um escritor — nao le' arquivo, nao roda comando, nao carrega CLAUDE.md, plugin ou
hook do usuario. As instrucoes vao por ARQUIVO (--system-prompt-file) porque os
roteiros de treino passam de 150 mil caracteres e a linha de comando do Windows corta
em 32 mil.
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NOVA_JANELA = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

# Os modelos que aparecem nos Ajustes, pelo nome EXATO (testados no --model do Claude
# Code em 2026-10-12, todos com --effort high). Pelo nome exato, e nao pelo apelido
# ("opus"), pra tela mostrar a versao que esta' rodando de verdade.
MODELOS = [
    ("claude-fable-5-1", "Fable 5.1"),
    ("claude-opus-5-5", "Opus 5.5"),
    ("claude-sonnet-5-5", "Sonnet 5.5"),
    ("claude-haiku-4-5-20251001", "Haiku 4.5"),
]
MODELO_PADRAO = "claude-opus-5-5"
# o esforco e' sempre alto: e' o que o usuario quer, e o custo e' do plano, nao da API
ESFORCO = "high"


class ErroClaude(RuntimeError):
    pass


def executavel():
    """O claude.exe de verdade. O claude.cmd do npm passa os argumentos pelo cmd.exe,
    que estraga aspas — e o --json-schema e' cheio delas."""
    candidatos = [
        os.environ.get("CLAUDE_CODE_EXE", ""),
        str(Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai"
            / "claude-code" / "bin" / "claude.exe"),
        str(Path.home() / ".local" / "bin" / "claude.exe"),
        shutil.which("claude.exe") or "",
        shutil.which("claude") or "",
    ]
    for c in candidatos:
        if c and Path(c).is_file():
            return c
    return None


def modelo_cli(modelo):
    """O nome exato que vai no --model. Config antiga ('claude-sonnet-5', 'opus'...) vira
    o modelo mais novo da mesma familia."""
    m = (modelo or "").strip().lower()
    if m in dict(MODELOS):
        return m
    for nome, _ in MODELOS:
        familia = nome.split("-")[1]          # fable / opus / sonnet / haiku
        if familia in m:
            return nome
    return MODELO_PADRAO


def status():
    """{instalado, logado, email, plano}. Le' o login salvo; nao gasta limite do plano."""
    exe = executavel()
    if not exe:
        return {"instalado": False, "logado": False, "email": "", "plano": ""}
    try:
        r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           creationflags=SEM_JANELA)
        d = json.loads(r.stdout or "{}")
    except Exception:
        d = {}
    return {"instalado": True, "logado": bool(d.get("loggedIn")),
            "email": d.get("email") or "", "plano": d.get("subscriptionType") or ""}


def entrar():
    """Abre uma janela com o login do Claude Code. Ele abre o navegador pra pessoa entrar
    na conta; quando termina, o login fica salvo e a janela pode ser fechada."""
    exe = executavel()
    if not exe:
        raise ErroClaude("o Claude Code não está instalado neste PC.")
    subprocess.Popen([exe, "auth", "login", "--claudeai"], creationflags=NOVA_JANELA)


def sair():
    exe = executavel()
    if not exe:
        raise ErroClaude("o Claude Code não está instalado neste PC.")
    subprocess.run([exe, "auth", "logout"], capture_output=True, timeout=60,
                   creationflags=SEM_JANELA)


def pronto():
    """'' se da' pra usar; senao, a frase que a tela mostra."""
    s = status()
    if not s["instalado"]:
        return "o Claude Code não está instalado neste PC. Instale e conecte em Ajustes."
    if not s["logado"]:
        return "o Claude Code não está conectado. Entre na sua conta do Claude em Ajustes."
    return ""


def _quando(ts):
    try:
        return time.strftime("%H:%M", time.localtime(float(ts)))
    except Exception:
        return ""


def escrever(sistema, pedido, modelo=None, on_delta=None, schema=None):
    """Roda uma geracao e devolve o texto (ou, com schema, o objeto JSON validado).

    on_delta(texto_acumulado) recebe o texto nascendo, como no streaming da API.
    """
    exe = executavel()
    if not exe:
        raise ErroClaude("o Claude Code não está instalado neste PC.")
    pasta = Path(tempfile.mkdtemp(prefix="yf_claude_"))
    arq = pasta / "instrucoes.txt"
    arq.write_text(sistema or "", encoding="utf-8")
    cmd = [exe, "-p", "--tools", "", "--safe-mode", "--no-session-persistence",
           "--system-prompt-file", str(arq), "--model", modelo_cli(modelo),
           "--effort", ESFORCO,
           "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    if schema:
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8",
                             errors="replace", cwd=str(pasta), creationflags=SEM_JANELA)
        erro_txt = []
        leitor = threading.Thread(target=lambda: erro_txt.append(p.stderr.read()), daemon=True)
        leitor.start()
        p.stdin.write(pedido or "")
        p.stdin.close()
        buf, final, limite = [], None, None
        for linha in p.stdout:
            linha = linha.strip()
            if not linha.startswith("{"):
                continue
            try:
                ev = json.loads(linha)
            except json.JSONDecodeError:
                continue
            tipo = ev.get("type")
            if tipo == "stream_event":
                e = ev.get("event") or {}
                d = e.get("delta") or {}
                if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                    buf.append(d.get("text", ""))
                    if on_delta and not schema:
                        on_delta("".join(buf))
            elif tipo == "rate_limit_event":
                limite = ev.get("rate_limit_info") or {}
            elif tipo == "result":
                final = ev
        p.wait()
        leitor.join(5)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    if final is None:
        detalhe = ("".join(erro_txt) or "").strip()[-400:]
        if "login" in detalhe.lower() or "auth" in detalhe.lower():
            raise ErroClaude("o Claude Code não está conectado. Entre na sua conta em Ajustes.")
        raise ErroClaude("o Claude Code parou sem responder. " + detalhe)
    if final.get("is_error"):
        msg = str(final.get("result") or final.get("subtype") or "erro desconhecido")
        if limite and limite.get("status") not in (None, "allowed", "allowed_warning"):
            volta = _quando(limite.get("resetsAt"))
            raise ErroClaude("o limite do seu plano do Claude acabou por agora"
                             + (f"; ele volta às {volta}." if volta else ".")
                             + " Tente de novo depois.")
        raise ErroClaude("o Claude Code deu erro: " + msg[:400])
    if schema:
        obj = final.get("structured_output")
        if obj is None:
            try:
                obj = json.loads(final.get("result") or "")
            except Exception:
                raise ErroClaude("o Claude Code não devolveu o formato pedido.")
        return obj
    texto = (final.get("result") or "".join(buf)).strip()
    if not texto:
        raise ErroClaude("o Claude Code não devolveu texto.")
    return texto
