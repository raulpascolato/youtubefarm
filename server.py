# -*- coding: utf-8 -*-
"""API do YOUTUBE FARM. Serve o front (static/) e expoe /api/*."""
import json
import os
import re
import shutil
import threading
import time
import traceback
import unicodedata
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles

import caminhos
import diretor
import estilo
import montador
import roteirista
import tts
from caminhos import dir_app, dir_dados, dir_saida
import urllib.request
import zipfile
import tempfile
import io
import versao
from store import Store, MODELO_PERSONAGEM

STATIC = dir_app() / "static"

store = Store()
app = FastAPI(title="YOUTUBE FARM")

# faixa unica de duracao do canal. Nao e' configuravel de proposito: o roteiro so' sai
# bom nessa janela, e deixar o usuario pedir 45min so' rendia roteiro estufado.
DUR_MIN, DUR_MAX = 16, 20


def erro(msg, code=400):
    return JSONResponse({"ok": False, "erro": msg}, status_code=code)


# ------------------------------------------------------------------ config
def _mascara(k):
    return (k[:10] + "…" + k[-4:]) if len(k) > 18 else ("" if not k else "•••")


@app.get("/api/config")
def get_config():
    cfg = store.get_cfg()
    ka, kd = cfg.get("anthropic_key") or "", cfg.get("darkplanner_key") or ""
    # nunca devolve as chaves inteiras pro front
    cfg["anthropic_key"] = _mascara(ka)
    cfg["darkplanner_key"] = _mascara(kd)
    cfg["tem_key"] = bool(ka)
    cfg["tem_key_dp"] = bool(kd)
    cfg["modelo_personagem"] = MODELO_PERSONAGEM
    return cfg


@app.post("/api/config")
def set_config(body: dict = Body(...)):
    patch = {}
    for campo in ("anthropic_key", "darkplanner_key"):
        if campo in body:
            k = (body.get(campo) or "").strip()
            if k and "…" not in k and "•" not in k:   # ignora o placeholder mascarado
                patch[campo] = k
    for campo in ("modelo", "chars_por_minuto"):
        if campo in body and body[campo] not in (None, ""):
            patch[campo] = body[campo]
    store.set_cfg(patch)
    return get_config()


# ------------------------------------------------------------------ presets
@app.get("/api/presets")
def listar_presets():
    return store.presets()


@app.post("/api/presets")
def criar_preset(body: dict = Body(...)):
    nome = (body.get("nome") or "").strip()
    conteudo = body.get("conteudo")
    origem = (body.get("origem") or "").strip()
    if not nome:
        return erro("dá um nome pro modelo (ex: cozinheiro).")
    if not conteudo:
        return erro("anexa o arquivo de treinamento.")
    try:
        # aceita JSON ou o formato de blocos entre chaves — decide sozinho
        roteiros = (roteirista.parse_conteudo(conteudo) if isinstance(conteudo, str)
                    else roteirista.parse_treinamento(conteudo))
    except ValueError as e:
        return erro(str(e))
    return store.add_preset(nome, roteiros, origem)


@app.delete("/api/presets/{pid}")
def apagar_preset(pid: str):
    r = store.del_preset(pid)
    if r == "em-uso":
        return erro("tem canal usando esse modelo. Apaga o canal antes.")
    if not r:
        return erro("modelo não encontrado.", 404)
    return {"ok": True}


# ------------------------------------------------------------------ canais
@app.get("/api/canais")
def listar_canais():
    return store.canais()


@app.get("/api/canais/{cid}")
def ver_canal(cid: str):
    c = store.canal(cid)
    return c or erro("canal não encontrado.", 404)


@app.post("/api/canais")
def criar_canal(body: dict = Body(...)):
    nome = (body.get("nome") or "").strip()
    idioma = (body.get("idioma") or "").strip()
    preset_id = (body.get("preset_id") or "").strip()
    if not nome:
        return erro("dá um nome pro canal.")
    if not idioma:
        return erro("escolhe o idioma do canal.")
    if not store.preset(preset_id):
        return erro("escolhe um modelo de roteiro.")
    return store.add_canal(nome, idioma, preset_id)


@app.delete("/api/canais/{cid}")
def apagar_canal(cid: str):
    store.del_canal(cid)
    return {"ok": True}


@app.post("/api/canais/{cid}/editar")
def editar_canal(cid: str, body: dict = Body(...)):
    if "nome" in body and not (body.get("nome") or "").strip():
        return erro("o canal precisa de um nome.")
    if "idioma" in body and not (body.get("idioma") or "").strip():
        return erro("o canal precisa de um idioma.")
    c = store.editar_canal(cid, body)
    return c or erro("canal não encontrado.", 404)


@app.post("/api/canais/{cid}/capa")
def enviar_capa(cid: str, body: dict = Body(...)):
    """Recebe a capa do produto em base64 (o front lê o arquivo e manda o conteúdo)."""
    import base64
    if not store.canal(cid):
        return erro("canal não encontrado.", 404)
    dados = (body.get("conteudo") or "")
    if "," in dados:
        dados = dados.split(",", 1)[1]          # tira o "data:image/png;base64,"
    try:
        binario = base64.b64decode(dados)
    except Exception:
        return erro("não consegui ler essa imagem.")
    if not binario:
        return erro("arquivo vazio.")
    if len(binario) > 8 * 1024 * 1024:
        return erro("imagem grande demais (máximo 8 MB).")
    ext = Path(body.get("nome") or "capa.png").suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return erro("use PNG, JPG ou WEBP.")
    pasta = dir_dados() / "data" / "capas"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = f"{cid}{ext}"
    (pasta / arq).write_bytes(binario)
    return store.editar_canal(cid, {"produto_capa": arq})


@app.get("/api/canais/{cid}/capa")
def ver_capa(cid: str):
    c = store.canal(cid)
    if not c or not c.get("produto_capa"):
        return erro("sem capa.", 404)
    p = dir_dados() / "data" / "capas" / c["produto_capa"]
    if not p.exists():
        return erro("sem capa.", 404)
    return FileResponse(p)


@app.post("/api/canais/{cid}/voz")
def escolher_voz(cid: str, body: dict = Body(...)):
    c = store.set_voz(cid, (body.get("voz_id") or "").strip(),
                      (body.get("voz_nome") or "").strip())
    return c or erro("canal não encontrado.", 404)


# ------------------------------------------------------------------ vozes
_vozes_cache = {"lista": [], "quando": 0.0}

# o idioma do canal e' escrito por extenso; a API usa codigo ISO
ISO = {"português": "pt", "portugues": "pt", "english": "en", "deutsch": "de",
       "español": "es", "espanol": "es", "français": "fr", "francais": "fr",
       "italiano": "it", "nederlands": "nl", "polski": "pl", "svenska": "sv",
       "dansk": "da", "norsk": "no"}

# Qual gravacao usar no preview. multilingual_v2 e' o modelo de mais alta qualidade da
# ElevenLabs pra voz multilingue, feito pra narracao — e o que tem mais entradas em
# alemao. Fica de fora o *_sts_v2: aquilo e' speech-to-speech, nao leitura de texto.
MODELOS_PREVIEW = ["eleven_multilingual_v2", "eleven_turbo_v2_5",
                   "eleven_flash_v2_5", "eleven_v2_5_flash", "eleven_turbo_v2"]


def _verificados(v):
    """As entradas de idioma da voz. Vem aninhado em voice_info, nao no topo."""
    i = v.get("voice_info") or {}
    return [e for e in (i.get("verified_languages") or []) if isinstance(e, dict)]


def _idiomas(v):
    return {e.get("language") for e in _verificados(v) if e.get("language")}


def _preview_url(v, iso=""):
    """Preview NO IDIOMA do canal — é ouvindo a voz falar alemão que se decide se ela
    presta pra um canal alemão, não ouvindo ela em inglês."""
    ents = [e for e in _verificados(v)
            if (not iso or e.get("language") == iso) and e.get("preview_url")]
    for modelo in MODELOS_PREVIEW:
        for e in ents:
            if e.get("model_id") == modelo:
                return e["preview_url"]
    return ents[0]["preview_url"] if ents else (v.get("preview_url") or "")


def _vozes():
    """844 vozes que quase nunca mudam — busca uma vez e guarda por 1h."""
    if _vozes_cache["lista"] and (time.time() - _vozes_cache["quando"]) < 3600:
        return _vozes_cache["lista"]
    key = (store.get_cfg().get("darkplanner_key") or "").strip()
    if not key:
        raise tts.TTSError("falta a chave do DarkPlanner. Coloca em Ajustes.")
    lista = tts.listar_vozes(key)
    _vozes_cache.update(lista=lista, quando=time.time())
    return lista


@app.get("/api/vozes")
def listar_vozes(q: str = "", genero: str = "", idioma: str = "",
                 limite: int = 60, pagina: int = 1):
    """Filtra pelo idioma do canal. As que não declaram idioma nenhum não somem —
    vão pro fim, num grupo à parte, porque pode ter voz boa ali."""
    try:
        vs = _vozes()
    except tts.TTSError as e:
        return erro(str(e))
    q = (q or "").strip().lower()
    if genero in ("male", "female"):
        vs = [v for v in vs if v.get("gender") == genero]
    if q:
        vs = [v for v in vs if q in (v.get("name") or "").lower()]

    iso = ISO.get((idioma or "").strip().lower(), "")
    if iso:
        no_idioma = [v for v in vs if iso in _idiomas(v)]
        sem_info = [v for v in vs if not _idiomas(v)]
    else:
        no_idioma, sem_info = vs, []

    def linha(v, grupo):
        return {"id": v.get("id"), "nome": v.get("name"),
                "genero": v.get("gender"), "grupo": grupo}

    limite = max(1, min(200, limite))
    paginas = max(1, -(-len(no_idioma) // limite))      # divisao arredondando pra cima
    pagina = max(1, min(paginas, pagina))
    ini = (pagina - 1) * limite
    saida = [linha(v, "idioma") for v in no_idioma[ini:ini + limite]]
    # as "sem idioma" so' na ULTIMA pagina: elas fecham a lista, nao atrapalham quem
    # esta' folheando as do idioma certo
    if pagina == paginas:
        saida += [linha(v, "sem_idioma") for v in sem_info]
    return {"total": len(no_idioma), "total_sem_idioma": len(sem_info),
            "iso": iso, "pagina": pagina, "paginas": paginas,
            "de": ini + 1 if saida else 0, "ate": min(ini + limite, len(no_idioma)),
            "vozes": saida}


@app.get("/api/vozes/{vid}/preview")
def preview_voz(vid: str, idioma: str = ""):
    """Proxy do preview: a origem recusa quem não manda User-Agent de navegador."""
    try:
        v = next((x for x in _vozes() if x.get("id") == vid), None)
        if not v:
            return erro("voz não encontrada.", 404)
        url = _preview_url(v, ISO.get((idioma or "").strip().lower(), ""))
        if not url:
            return erro("essa voz não tem preview.", 404)
        dados, tipo = tts.preview_bytes(url)
    except Exception as e:
        return erro(f"não consegui tocar essa voz: {e}")
    return Response(content=dados, media_type=tipo)


# ------------------------------------------------------------------ videos
@app.get("/api/canais/{cid}/videos")
def listar_videos(cid: str):
    return [{k: v for k, v in vid.items() if k != "roteiro"} for vid in store.videos(cid)]


@app.get("/api/videos/{vid}")
def ver_video(vid: str):
    v = store.video(vid)
    return v or erro("vídeo não encontrado.", 404)


@app.get("/api/videos/{vid}/txt")
def baixar_txt(vid: str):
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    return PlainTextResponse(v.get("roteiro") or "", media_type="text/plain; charset=utf-8")


@app.delete("/api/videos/{vid}")
def apagar_video(vid: str):
    store.del_video(vid)
    return {"ok": True}


@app.post("/api/videos")
def criar_video(body: dict = Body(...)):
    canal_id = (body.get("canal_id") or "").strip()
    titulo = (body.get("titulo") or "").strip()
    try:
        dur = int(body.get("dur") or 0)
    except Exception:
        dur = 0
    canal = store.canal(canal_id)
    if not canal:
        return erro("canal não encontrado.", 404)
    if not titulo:
        return erro("escreve o título do vídeo.")

    # roteiro colado: pula a geração inteira. A duração sai do tamanho do texto,
    # porque aqui quem manda é o roteiro que já existe, não a faixa de 16-20.
    colado = (body.get("roteiro") or "").strip()
    if colado:
        cfg = store.get_cfg()
        cpm = int(cfg.get("chars_por_minuto") or 810)
        if len(colado) < 400:
            return erro("esse roteiro é curto demais — parece que faltou colar o texto.")
        v = store.add_video(canal_id, titulo, max(1, round(len(colado) / cpm)))
        return store.up_video(v["id"], estado="pronto", roteiro=colado,
                              n_chars=len(colado), alvo_chars=len(colado))

    if not (DUR_MIN <= dur <= DUR_MAX):
        return erro(f"a duração tem que ser entre {DUR_MIN} e {DUR_MAX} minutos.")

    cfg = store.get_cfg()
    if not (cfg.get("anthropic_key") or "").strip():
        return erro("falta a chave da API do Claude. Coloca em Ajustes.")
    roteiros = store.roteiros_do_preset(canal["preset_id"])
    if not roteiros:
        return erro("o modelo desse canal está vazio ou foi removido.")

    v = store.add_video(canal_id, titulo, dur)
    alvo = int(dur * int(cfg.get("chars_por_minuto") or 810))
    store.up_video(v["id"], alvo_chars=alvo, estado="gerando")
    threading.Thread(target=_gerar, args=(v["id"], canal, titulo, dur, alvo, roteiros, cfg),
                     daemon=True).start()
    return store.video(v["id"])


def _slug(txt, tamanho=60):
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return (t or "video")[:tamanho]


@app.post("/api/videos/{vid}/audio")
def criar_audio(vid: str):
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    if v["estado"] != "pronto":
        return erro("espera o roteiro terminar primeiro.")
    if v["audio_estado"] == "gerando":
        return erro("já tem uma narração sendo gerada pra esse vídeo.")
    canal = store.canal(v["canal_id"])
    if not canal:
        return erro("canal não encontrado.", 404)
    if not canal.get("voz_id"):
        return erro("esse canal ainda não tem voz. Escolhe uma na tela do canal.")
    cfg = store.get_cfg()
    if not (cfg.get("darkplanner_key") or "").strip():
        return erro("falta a chave do DarkPlanner. Coloca em Ajustes.")

    pasta = dir_saida() / _slug(canal["nome"], 40) / _slug(v["titulo"])
    store.up_video(vid, audio_estado="gerando", audio_msg="preparando…",
                   audio_erro="", pasta=str(pasta))
    threading.Thread(target=_gerar_audio, args=(vid, v, canal, cfg, pasta),
                     daemon=True).start()
    return store.video(vid)


def _gerar_audio(vid, v, canal, cfg, pasta):
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        # o roteiro tambem fica na pasta: e' o que voce leva pro HeyGen depois
        (pasta / "roteiro.txt").write_text(v["roteiro"], encoding="utf-8")
        r = tts.gerar_e_baixar(
            key=cfg["darkplanner_key"],
            texto=v["roteiro"],
            voice_id=canal["voz_id"],
            pasta=pasta,
            titulo=v["titulo"],
            veo_min=estilo.BLOCO_MIN_S,
            veo_max=estilo.BLOCO_MAX_S,
            on_status=lambda t: store.up_video(vid, audio_msg=t),
        )
        store.up_video(vid, audio_estado="pronto", audio_msg="",
                       audio_path=r.get("audio", ""), srt_path=r.get("srt", ""),
                       pasta=r.get("pasta", str(pasta)))
    except Exception as e:
        traceback.print_exc()
        store.up_video(vid, audio_estado="erro", audio_msg="", audio_erro=str(e))


@app.post("/api/videos/{vid}/direcao")
def criar_direcao(vid: str):
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    if v["audio_estado"] != "pronto" or not v.get("srt_path"):
        return erro("gera a narração primeiro — a direção precisa do blocos.srt.")
    if v["direcao_estado"] == "gerando":
        return erro("já tem uma direção rodando pra esse vídeo.")
    cfg = store.get_cfg()
    if not (cfg.get("anthropic_key") or "").strip():
        return erro("falta a chave do Claude. Coloca em Ajustes.")
    canal = store.canal(v["canal_id"])
    store.up_video(vid, direcao_estado="gerando", direcao_msg="lendo o SRT…",
                   direcao_erro="")
    threading.Thread(target=_gerar_direcao, args=(vid, v, canal, cfg), daemon=True).start()
    return store.video(vid)


def _gerar_direcao(vid, v, canal, cfg):
    try:
        blocos = diretor.parse_srt(v["srt_path"])
        plano = diretor.dirigir(
            api_key=cfg["anthropic_key"],
            modelo=cfg.get("modelo") or "claude-opus-5",
            blocos=blocos,
            tema=v["titulo"],
            canal=canal,
            on_status=lambda t: store.up_video(vid, direcao_msg=t),
        )
        resumo = diretor.escrever_saidas(plano, Path(v["pasta"]) / "broll")
        store.up_video(vid, direcao_estado="pronto", direcao_msg="",
                       direcao_resumo=resumo)
    except Exception as e:
        traceback.print_exc()
        store.up_video(vid, direcao_estado="erro", direcao_msg="", direcao_erro=str(e))


@app.post("/api/videos/{vid}/avatar")
def anexar_avatar(vid: str, body: dict = Body(...)):
    """Guarda o CAMINHO do avatar.mp4, não uma cópia: o arquivo tem centenas de MB."""
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    p = Path((body.get("caminho") or "").strip())
    if not p.exists() or not p.is_file():
        return erro("não achei esse arquivo.")
    if p.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm"):
        return erro("o avatar tem que ser um vídeo (.mp4, .mov, .mkv).")
    return store.up_video(vid, avatar_path=str(p))


@app.post("/api/videos/{vid}/broll")
def importar_broll(vid: str, body: dict = Body(...)):
    """Traz o que o DarkPlanner baixou pra dentro da pasta do vídeo."""
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    if v["direcao_estado"] != "pronto":
        return erro("gera a direção primeiro.")
    pasta = Path((body.get("pasta") or "").strip())
    if not pasta.is_dir():
        return erro("essa pasta não existe.")
    if not (pasta / "images").is_dir() and not (pasta / "videos").is_dir():
        return erro("não achei 'images' nem 'videos' aí dentro. "
                    "Aponta a pasta onde o DarkPlanner baixa.")
    try:
        conta = montador.importar_broll(pasta, Path(v["pasta"]) / "broll",
                                        Path(v["pasta"]) / "clipes")
    except montador.ErroMontagem as e:
        return erro(str(e))
    resumo = {"imagem": conta["imagem"], "video": conta["video"],
              "faltando": len(conta["faltando"])}
    return store.up_video(vid, pasta_dark=str(pasta), broll_resumo=resumo)


@app.post("/api/videos/{vid}/montar")
def montar_video(vid: str):
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    if v["direcao_estado"] != "pronto":
        return erro("gera a direção primeiro.")
    if not v.get("avatar_path"):
        return erro("anexa o avatar antes de montar.")
    if v["montagem_estado"] == "montando":
        return erro("já tem uma montagem rodando.")
    if not caminhos.tem_ffmpeg():
        return erro("não achei o ffmpeg. Ele deveria estar em bin/ffmpeg.exe.")
    canal = store.canal(v["canal_id"])
    store.up_video(vid, montagem_estado="montando", montagem_msg="preparando…",
                   montagem_erro="")
    threading.Thread(target=_montar, args=(vid, v, canal), daemon=True).start()
    return store.video(vid)


def _montar(vid, v, canal):
    try:
        pasta = Path(v["pasta"])
        if canal and canal.get("produto_capa"):
            canal = dict(canal)
            canal["_capa_path"] = str(dir_dados() / "data" / "capas" / canal["produto_capa"])
        saida = pasta / (_slug(v["titulo"]) + ".mp4")
        r = montador.montar(
            plano_json=pasta / "broll" / "plano.json",
            avatar=v["avatar_path"],
            audio=v["audio_path"],
            clipes=pasta / "clipes",
            saida=saida,
            canal=canal,
            on_status=lambda t: store.up_video(vid, montagem_msg=t),
        )
        store.up_video(vid, montagem_estado="pronto", montagem_msg="",
                       montagem_saida=r["saida"], montagem_erro="",
                       montagem_faltaram=r.get("faltaram", 0))
    except Exception as e:
        traceback.print_exc()
        store.up_video(vid, montagem_estado="erro", montagem_msg="", montagem_erro=str(e))


@app.get("/api/videos/{vid}/prompts")
def ver_prompts(vid: str):
    """O prompts_flow.txt cru — o front copia isso pro multiprompt do DarkPlanner."""
    v = store.video(vid)
    if not v or not v.get("pasta"):
        return erro("vídeo não encontrado.", 404)
    p = Path(v["pasta"]) / "broll" / "prompts_flow.txt"
    if not p.exists():
        return erro("gera a direção primeiro.", 404)
    return PlainTextResponse(p.read_text(encoding="utf-8"),
                             media_type="text/plain; charset=utf-8")


@app.post("/api/videos/{vid}/refazer")
def refazer_roteiro(vid: str):
    """Gera o roteiro de novo, mesmo título e duração. Zera o que vinha depois."""
    v = store.video(vid)
    if not v:
        return erro("vídeo não encontrado.", 404)
    if v["estado"] == "gerando":
        return erro("o roteiro ainda está sendo escrito.")
    canal = store.canal(v["canal_id"])
    if not canal:
        return erro("canal não encontrado.", 404)
    cfg = store.get_cfg()
    if not (cfg.get("anthropic_key") or "").strip():
        return erro("falta a chave do Claude. Coloca em Ajustes.")
    roteiros = store.roteiros_do_preset(canal["preset_id"])
    if not roteiros:
        return erro("o modelo desse canal está vazio ou foi removido.")
    store.up_video(vid, estado="gerando", roteiro="", n_chars=0, erro="", aviso="",
                   audio_estado="nao", audio_path="", srt_path="",
                   direcao_estado="nao", direcao_resumo={})
    threading.Thread(target=_gerar,
                     args=(vid, canal, v["titulo"], v["dur"], v["alvo_chars"],
                           roteiros, cfg), daemon=True).start()
    return store.video(vid)


@app.get("/api/videos/{vid}/audio.mp3")
def ouvir_audio(vid: str):
    v = store.video(vid)
    if not v or not v.get("audio_path") or not Path(v["audio_path"]).exists():
        return erro("áudio não encontrado.", 404)
    return FileResponse(v["audio_path"], media_type="audio/mpeg")


@app.post("/api/videos/{vid}/pasta")
def abrir_pasta(vid: str):
    v = store.video(vid)
    if not v or not v.get("pasta") or not Path(v["pasta"]).exists():
        return erro("a pasta ainda não existe.", 404)
    try:
        os.startfile(v["pasta"])          # abre no Explorer
    except Exception as e:
        return erro(f"não consegui abrir: {e}")
    return {"ok": True}


def _gerar(vid, canal, titulo, dur, alvo, roteiros, cfg):
    def on_delta(parcial):
        store.up_video(vid, roteiro=parcial, n_chars=len(parcial))

    modelo = cfg.get("modelo") or "claude-opus-5"
    try:
        texto = roteirista.gerar_roteiro(
            api_key=cfg["anthropic_key"],
            modelo=modelo,
            titulo=titulo,
            dur_min=dur,
            idioma=canal["idioma"],
            roteiros=roteiros,
            alvo_chars=alvo,
            on_delta=on_delta,
            canal=canal,
        )
        # rede de seguranca: canal sem produto que mesmo assim saiu vendendo algo
        aviso = roteirista.checar_produto(cfg["anthropic_key"], modelo, texto, canal)
        store.up_video(vid, roteiro=texto, n_chars=len(texto), estado="pronto",
                       erro="", aviso=aviso)
    except Exception as e:
        traceback.print_exc()
        store.up_video(vid, estado="erro", erro=f"{type(e).__name__}: {e}")


# ------------------------------------------------------------------ front
@app.middleware("http")
async def sem_cache(request, call_next):
    """O WebView2 guarda o css/js em cache e continua mostrando a versão velha depois
    de uma atualização do app — dá pra editar a interface e não ver mudança nenhuma.
    Como tudo aqui é servido do próprio PC, cache não economiza nada."""
    r = await call_next(request)
    r.headers["Cache-Control"] = "no-store, must-revalidate"
    return r


@app.get("/", response_class=HTMLResponse)
def index():
    """Carimba a data do arquivo no link do css/js. Sem isso o WebView2 continua usando
    a versão em cache mesmo com no-store, e a interface fica congelada numa versão
    antiga depois de uma atualização do app."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for arq in ("style.css", "app.js"):
        try:
            v = int((STATIC / arq).stat().st_mtime)
        except OSError:
            v = 0
        html = html.replace(f"/{arq}", f"/{arq}?v={v}")
    return HTMLResponse(html)

# ---------------------------------------------------------------- atualizacao
def _num(tag):
    """'v1.10.2' -> (1, 10, 2). Compara como numero, senao '1.10' < '1.9' no texto."""
    partes = re.findall(r"\d+", (tag or ""))
    return tuple(int(p) for p in partes[:4]) or (0,)


def _github(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "youtube-farm", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


@app.get("/api/versao")
def ver_versao():
    if not versao.REPO or "/" not in versao.REPO:
        return {"atual": versao.VERSAO, "configurado": False}
    try:
        d = _github(f"https://api.github.com/repos/{versao.REPO}/releases/latest")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"atual": versao.VERSAO, "configurado": True,
                    "erro": "esse repositório não tem nenhuma release publicada ainda."}
        return {"atual": versao.VERSAO, "configurado": True,
                "erro": f"o GitHub respondeu {e.code}."}
    except Exception as e:
        return {"atual": versao.VERSAO, "configurado": True,
                "erro": f"não consegui falar com o GitHub: {e}"}
    tag = d.get("tag_name") or ""
    return {"atual": versao.VERSAO, "configurado": True, "ultima": tag.lstrip("vV"),
            "ha_atualizacao": _num(tag) > _num(versao.VERSAO),
            "notas": (d.get("body") or "").strip()[:1200],
            "zip": d.get("zipball_url") or ""}


@app.post("/api/atualizar")
def atualizar(body: dict = Body(default={})):
    """Baixa o zip da release e escreve por cima, menos o que esta' em PROTEGIDOS.

    Escrever .py por cima com o app rodando e' seguro: o Python ja' leu tudo na
    importacao. Por isso o app pede pra fechar e abrir de novo no fim.
    """
    zip_url = (body or {}).get("zip") or ""
    if not zip_url.startswith("https://api.github.com/"):
        return erro("endereço de download inválido.")
    destino = Path(caminhos.dir_app())
    try:
        req = urllib.request.Request(zip_url, headers={"User-Agent": "youtube-farm"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dados = r.read()
    except Exception as e:
        return erro(f"não consegui baixar: {e}")

    tmp = Path(tempfile.mkdtemp(prefix="yf_upd_"))
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            z.extractall(tmp)
        # o zip do GitHub vem dentro de uma pasta unica: usuario-repo-abc1234/
        raizes = [p for p in tmp.iterdir() if p.is_dir()]
        if len(raizes) != 1:
            return erro("o zip da release veio num formato inesperado.")
        raiz, trocados = raizes[0], 0
        for item in raiz.iterdir():
            if item.name in versao.PROTEGIDOS:
                continue
            alvo = destino / item.name
            if item.is_dir():
                shutil.rmtree(alvo, ignore_errors=True)
                shutil.copytree(item, alvo)
            else:
                shutil.copy2(item, alvo)
            trocados += 1
        return {"ok": True, "trocados": trocados,
                "msg": "Atualizado. Feche e abra o app pra valer."}
    except Exception as e:
        return erro(f"não consegui aplicar a atualização: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


app.mount("/", StaticFiles(directory=str(STATIC)), name="static")
