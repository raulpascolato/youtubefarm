# -*- coding: utf-8 -*-
"""Narracao pelo DarkPlanner (app.darkplanner.com.br).

O ponto importante: alem do audio.mp3, a API devolve o SRT DE BLOCOS (srt_tempo_url).
Esse SRT e' o relogio do video — e' dele que sai quantos blocos existem e quanto dura
cada um, que e' o que o diretor e o montador consomem depois. Por isso a etapa de audio
ja' entrega a etapa de timing junto.

Fluxo: generate (job_id) -> status (poll ate completed) -> download (urls) -> baixa.
Auth: header X-API-Key com a chave dpk_...
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://app.darkplanner.com.br/api/v1/audio"
# o urllib padrao leva 403 no preview das vozes; com UA de navegador passa.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


class TTSError(Exception):
    pass


def _req(url, key=None, metodo="GET", corpo=None, timeout=60):
    h = {"User-Agent": UA}
    if key:
        h["X-API-Key"] = key
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        h["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=dados, headers=h, method=metodo)


def _json(url, key=None, metodo="GET", corpo=None, timeout=60):
    try:
        with urllib.request.urlopen(_req(url, key, metodo, corpo), timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detalhe = e.read()[:300].decode("utf-8", "ignore")
        raise TTSError(f"HTTP {e.code} em {urllib.parse.urlparse(url).path} — {detalhe}")
    except Exception as e:
        raise TTSError(f"{type(e).__name__}: {e}")


def listar_vozes(key):
    return _json(f"{BASE}/voices", key).get("voices", [])


def uso(key):
    try:
        return _json(f"{BASE}/usage", key)
    except TTSError:
        return {}


def preview_bytes(url):
    """Baixa o preview de uma voz. Passa pelo nosso servidor porque a origem exige UA
    de navegador e a gente nao quer depender do que o WebView2 manda."""
    with urllib.request.urlopen(_req(url), timeout=30) as r:
        return r.read(), r.headers.get("Content-Type", "audio/mpeg")


def _baixar(url, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(_req(url), timeout=300) as r, open(dest, "wb") as f:
        while True:
            pedaco = r.read(1 << 16)
            if not pedaco:
                break
            f.write(pedaco)
    return dest


def gerar_e_baixar(key, texto, voice_id, pasta, titulo="", speed=1.0,
                   veo_min=None, veo_max=None,
                   on_status=None, timeout_s=1800, intervalo=5):
    """Bloqueante: enfileira, espera terminar e baixa audio.mp3 + blocos.srt em `pasta`.
    on_status(txt) e' chamado a cada checagem, pra tela mostrar o que esta acontecendo."""
    def aviso(t):
        if on_status:
            on_status(t)

    aviso("enviando o roteiro…")
    corpo = {"text": texto, "voice_id": voice_id, "speed": speed}
    if titulo:
        corpo["title"] = titulo
    # tamanho dos pedacos do SRT — e' o que define de quanto em quanto tempo a tela muda
    if veo_min:
        corpo["subtitle_veo_min"] = int(veo_min)
    if veo_max:
        corpo["subtitle_veo_max"] = int(veo_max)
    j = _json(f"{BASE}/generate", key, "POST", corpo)
    job = j.get("job_id")
    if not j.get("success") or not job:
        raise TTSError(f"a API não devolveu job_id: {str(j)[:200]}")

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = _json(f"{BASE}/status/{job}", key, timeout=30).get("status", "unknown")
        if st == "completed":
            break
        if st in ("failed", "error"):
            raise TTSError(f"a geração falhou no servidor (status={st})")
        aviso(f"gerando a narração… ({int(time.time() - t0)}s)")
        time.sleep(intervalo)
    else:
        raise TTSError(f"passou de {timeout_s // 60} min esperando o áudio ficar pronto")

    aviso("baixando os arquivos…")
    info = _json(f"{BASE}/download/{job}", key, timeout=60)
    if not info.get("success"):
        raise TTSError(f"download recusado: {str(info)[:200]}")
    url_audio = info.get("audio_url")
    # srt_tempo = o SRT DE BLOCOS (o que interessa). Os outros sao fallback.
    url_srt = info.get("srt_tempo_url") or info.get("srt_veo_url") or info.get("srt_url")
    if not url_audio:
        raise TTSError("a resposta não trouxe a URL do áudio")

    pasta = Path(pasta)
    saida = {"job_id": job, "pasta": str(pasta)}
    saida["audio"] = str(_baixar(url_audio, pasta / "audio.mp3"))
    saida["srt"] = str(_baixar(url_srt, pasta / "blocos.srt")) if url_srt else ""
    return saida
