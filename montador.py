# -*- coding: utf-8 -*-
"""Montagem: junta avatar, b-roll e card seguindo o plano.json, e casa com o audio.

Ideia: o avatar.mp4 tem a narracao INTEIRA. O audio toca por baixo do video todo. A cada
bloco a tela decide o que mostrar — o trecho do avatar, uma imagem com zoom lento, um
clipe, ou o card do produto. Corte seco, sem transicao, 1920x1080.

Nao usa ffprobe de proposito (seriam mais 98 MB no .exe de quem receber): toda duracao
sai do plano.json, e clipe curto o proprio ffmpeg repete com -stream_loop.
"""
import csv
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import card
from caminhos import ffmpeg

L, A, FPS = 1920, 1080, 30
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# encaixa qualquer proporcao em 1920x1080 sem distorcer, com barra preta se precisar
FIT = (f"scale={L}:{A}:force_original_aspect_ratio=decrease,"
       f"pad={L}:{A}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p,setsar=1")
# preenche a tela inteira e corta a sobra. Sem barra preta, mas perde as bordas.
PREENCHE = (f"scale={L}:{A}:force_original_aspect_ratio=increase,"
            f"crop={L}:{A},fps={FPS},format=yuv420p,setsar=1")

# Quanto a proporcao pode fugir de 16:9 e ainda valer a pena preencher.
# O avatar do HeyGen sai 1936x1080 — proporcao 1.7926 contra 1.7778 do 16:9, 16px mais
# largo. O FIT reduzia pra 1920x1071 e deixava 4px de preto em cima e 5px embaixo, que
# aparecem na tela. Preencher corta 16px de LARGURA e nada de altura.
# Um avatar 4:3 (1.3333) fica de fora de proposito: la' preencher comeria 360px de
# altura e cortaria a cabeca de quem fala. Nesse caso a barra preta e' o menor mal.
TOLERANCIA_ENQUADRAMENTO = 0.10
# color_range tv: sem isso o bloco de imagem sai yuvj420p (faixa cheia, herdada do
# JPEG) e o do avatar sai yuv420p (faixa de TV). Na troca aparece um pulo de brilho.
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-color_range", "tv", "-r", str(FPS)]

# Sem dissolvencia. Ela colava o ULTIMO QUADRO do bloco anterior, parado, por cima
# do proximo durante 0.4s — e um quadro parado no meio de um zoom parece que a
# animacao travou antes de acabar. Corte seco resolve, e ainda monta mais rapido.
class ErroMontagem(Exception):
    pass


def _tamanho(video):
    """(largura, altura) do arquivo, lidas do cabecalho pelo proprio ffmpeg.

    Nao usa ffprobe: e' mais um binario grande pra quem recebe o app baixar. O ffmpeg
    sem arquivo de saida sai com erro e imprime as informacoes do arquivo no stderr —
    e' de la' que sai o tamanho.
    """
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(video)],
                       capture_output=True, text=True, creationflags=SEM_JANELA)
    m = re.search(r"Video:.*?,\s(\d{2,5})x(\d{2,5})[\s,\[]", r.stderr or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def encaixe(video):
    """PREENCHE se a proporcao for quase 16:9; FIT se for muito diferente.

    Se nao der pra ler o tamanho, FIT: barra preta e' feia, imagem cortada errado e'
    pior.
    """
    tam = _tamanho(video)
    if not tam or not tam[1]:
        return FIT
    fuga = abs(tam[0] / tam[1] - L / A) / (L / A)
    return PREENCHE if fuga <= TOLERANCIA_ENQUADRAMENTO else FIT


def _run(cmd):
    r = subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *cmd],
                       capture_output=True, text=True, creationflags=SEM_JANELA)
    if r.returncode != 0:
        raise ErroMontagem((r.stderr or "")[-500:] or "o ffmpeg falhou sem dizer por quê")


# ------------------------------------------------------------------ importar b-roll

# O zoom anda a uma TAXA POR SEGUNDO, nao um percurso fixo. Com percurso fixo o mesmo
# movimento cabia em 5.4s num bloco e em 8.5s noutro: 15%/s contra 9%/s, velocidades
# diferentes na mesma sequencia. Assim um bloco curto fecha menos e um longo fecha mais,
# mas os dois se movem no MESMO ritmo.
# Calibrado com o video pronto na mao: o bloco mais longo (8,4s) fechava ate' 160% e
# ficou rapido demais. Reescalei TUDO pela razao ln(1,30)/ln(1,60) = 0.5582, entao o
# que fechava 160% agora fecha 130%, e o bloco mediano (6,6s) fecha 123% em vez de 145%.
TAXA_ZOOM = 1.0319     # 3.19% por segundo
ZOOM_TETO = 1.90       # bloco muito longo pararia de fechar aqui, pra nao virar borrao.
                       # Com a taxa nova so' um bloco de 21s chegaria la': e' rede de
                       # seguranca pra entrada estranha, nao um limite do dia a dia.
TAXA_PAN = 0.0060      # o centro anda 0.60% da largura por segundo. Desacelerou na
                       # mesma proporcao do zoom: mexer so' num dos dois mudaria o
                       # CARATER do movimento, nao so' a velocidade.


def _kenburns(dur, variacao, render=None, pulo=0):
    """Zoom + deslocamento lento, pra foto parada nao cansar.

    Usa PERSPECTIVE, nao zoompan. O zoompan corta em pixel INTEIRO: medido, desvio de
    0.106px da trajetoria e saltos de ate' 0.37px — era o tremor que aparecia na tela.
    O perspective reamostra em subpixel: desvio 0.015px e 3x mais rapido de renderizar.

    O zoom e' exponencial (z = taxa^t), nao linear: e' assim que a velocidade PARECE
    constante. Com z linear a entrada acelerava e a saida desacelerava.

    Quatro variacoes: o lado troca a cada imagem, entrar/sair a cada duas.

    RENDER encurta a SAIDA sem mudar o MOVIMENTO: o percurso continua sendo o do bloco
    inteiro, so' que sao gerados menos quadros. E' o que a dissolvencia usa pra pegar
    os primeiros 0.4s do movimento do bloco que entra.

    O progresso e' on/(q-1), nao on/FPS: assim o ultimo quadro cai EXATAMENTE no fim do
    percurso. Com tempo absoluto ele parava em 4.967s de 5.0s, e a imagem dava um pulo
    de 47px no instante da troca.

    PULO desloca o inicio: com pulo=q o primeiro quadro gerado e' o que VIRIA DEPOIS do
    ultimo do bloco. O progresso passa de 1 e o movimento simplesmente CONTINUA, no
    mesmo ritmo (a taxa e' por segundo, entao esticar o percurso nao muda a velocidade).
    E' o que a dissolvencia usa pra prolongar o bloco que sai.
    """
    q_mov = quadros(dur)                            # o percurso e' sempre o do bloco
    q = quadros(render) if render is not None else q_mov
    alcance = min(ZOOM_TETO, TAXA_ZOOM ** dur)      # quanto fecha neste bloco
    anda = TAXA_PAN * dur                           # quanto o centro caminha
    # ENTRAR/SAIR alterna a cada imagem, o LADO a cada duas. Essa ordem nao e' estetica,
    # e' o que faz o bloco novo COMECAR exatamente onde o anterior parou — mesmo zoom,
    # mesmo centro. Com o lado alternando a cada imagem (o inverso disso) dois blocos
    # seguidos entravam, e a dissolvencia mostrava um fechado (1.32) por cima de um
    # aberto (1.00): parecia um zoom surgindo do nada na troca.
    entrando = variacao % 2 == 0
    pra_direita = (variacao // 2) % 2 == 0

    p = f"((on+{pulo})/{q_mov - 1})"
    if entrando:
        z = f"(pow({alcance:.4f},{p}))"             # 1 -> alcance
        cx0, cx1 = 0.5, 0.5 + (anda if pra_direita else -anda)
    else:
        z = f"({alcance:.4f}*pow({1/alcance:.4f},{p}))"   # alcance -> 1
        cx0, cx1 = 0.5 + (anda if pra_direita else -anda), 0.5
    cx = f"({cx0:.4f}+({cx1 - cx0:.4f})*{p})"
    cy = "0.5"

    x0, x1 = f"(W*({cx}-1/(2*{z})))", f"(W*({cx}+1/(2*{z})))"
    y0, y1 = f"(H*({cy}-1/(2*{z})))", f"(H*({cy}+1/(2*{z})))"
    persp = (f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':"
             f"x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}':"
             f"interpolation=cubic:sense=source:eval=frame")
    return q, (f"scale={L}:{A}:force_original_aspect_ratio=increase,"
               f"crop={L}:{A},{persp},format=yuv420p,setsar=1")

def importar_broll(pasta_dark, pasta_broll, destino):
    """Traz o que o DarkPlanner baixou pra dentro da pasta do video.

    O nome do arquivo comeca com o numero do prompt (5_algum_texto.jpg). O flow_map.csv
    diz qual bloco e' aquele prompt. Entao 5 -> bloco 8 -> bloco_008.jpg.
    """
    pasta_dark, destino = Path(pasta_dark), Path(destino)
    mapa = Path(pasta_broll) / "flow_map.csv"
    if not mapa.exists():
        raise ErroMontagem("não achei o flow_map.csv — gera a direção primeiro.")
    destino.mkdir(parents=True, exist_ok=True)

    def indexar(sub, exts):
        achados = {}
        p = pasta_dark / sub
        if not p.is_dir():
            return achados
        for f in p.iterdir():
            m = re.match(r"^(\d+)_", f.name)
            if m and f.suffix.lower() in exts:
                achados.setdefault(int(m.group(1)), f)
        return achados

    imagens = indexar("images", {".jpg", ".jpeg", ".png", ".webp"})
    videos = indexar("videos", {".mp4", ".mov", ".webm"})

    conta = {"imagem": 0, "video": 0, "faltando": []}
    with open(mapa, encoding="utf-8-sig", newline="") as fmapa:
        linhas = list(csv.DictReader(fmapa))
    for linha in linhas:
        ordem, bloco, tipo = int(linha["ordem"]), int(linha["bloco"]), linha["tipo"]
        origem = videos.get(ordem) if tipo == "video" else imagens.get(ordem)
        if origem is None:                      # o video nao veio? usa a imagem dele
            origem = imagens.get(ordem)
            tipo = "imagem" if origem else tipo
        if origem is None:
            conta["faltando"].append(bloco)
            continue
        shutil.copy2(origem, destino / f"bloco_{bloco:03d}{origem.suffix.lower()}")
        conta["imagem" if tipo == "imagem" else "video"] += 1
    return conta


def _achar(clipes, n):
    for ext in (".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"):
        p = Path(clipes) / f"bloco_{n:03d}{ext}"
        if p.exists():
            return p
    return None


# ------------------------------------------------------------------ segmentos
def quadros(dur):
    """Quantos quadros um bloco tem. TODO segmento passa por aqui.

    Existe porque antes cada tipo cortava do seu jeito: a imagem por -frames:v (exato)
    e o avatar/clipe por -t (o ffmpeg arredonda por conta dele). Os dois discordavam de
    1 quadro de vez em quando, e isso ACUMULAVA — medido no video de 17min, os cortes
    caiam 0,30s a 0,36s atrasados la' pelos 8 minutos, e o avatar dessincronizava.
    """
    return max(2, int(round(dur * FPS)))


DISSOLVE = 0.4      # b-roll emendando em b-roll: um derrete no outro


def cauda(fonte, dur_ant, variacao_ant, saida, parado=False):
    """Os DISSOLVE segundos que viriam DEPOIS do bloco que sai, com a imagem dele.

    E' o que a dissolvencia sobrepoe. Imagem e movimento sao os DO BLOCO QUE SAI: ele
    simplesmente continua o que estava fazendo por mais 0,4s enquanto some. Por baixo,
    o bloco que entra ja' esta' rodando o SEU proprio movimento, desde o comeco dele.
    Uma faz zoom in ate' o fim, a outra faz zoom out desde o inicio, e o unico efeito
    entre as duas e' a opacidade.

    Antes a cauda usava o movimento do bloco que ENTRAVA. A ideia era manter as duas
    camadas andando juntas durante o fade, mas o efeito colateral era pior que o
    problema: como as direcoes alternam, a imagem que estava fechando invertia e
    comecava a ABRIR nos ultimos quadros, acompanhando a que entrava. Na tela parecia
    que ela desistia do zoom bem no finalzinho.
    """
    # o percurso continua sendo o do bloco que sai; o pulo comeca a contar depois do
    # ultimo quadro dele. Como a taxa e' por segundo, esticar 0,4s nao acelera nada.
    corte = min(DISSOLVE, dur_ant)
    if parado:
        # o bloco que sai e' um clipe de video: nao tem ken burns pra continuar, entao
        # a cauda e' o ultimo quadro dele parado, sumindo.
        q, vf = quadros(corte), FIT
    else:
        q, vf = _kenburns(dur_ant, variacao_ant, render=corte, pulo=quadros(dur_ant))
    _run(["-framerate", str(FPS), "-loop", "1", "-t", f"{corte + 0.2:.3f}",
          "-i", str(fonte), "-vf", vf, "-frames:v", str(q), *X264, str(saida)])


def cauda_avatar(avatar, inicio, saida, vf=FIT):
    """Os DISSOLVE segundos do avatar que vem DEPOIS do bloco dele.

    Nao e' o ultimo quadro congelado: e' o avatar continuando a falar, lido do proprio
    avatar.mp4 no ponto seguinte. Como o audio nao para nesses 0,4s, a boca continua
    batendo com a narracao enquanto ele some.
    """
    _run(["-ss", f"{inicio:.3f}", "-i", str(avatar), "-an", "-vf", vf,
          "-frames:v", str(quadros(DISSOLVE)), *X264, str(saida)])


def ultimo_quadro(segmento, dur, saida):
    """O ultimo quadro de um bloco de video, pra servir de fonte da cauda.

    Le' o SEGMENTO ja' renderizado, nao o clipe original. O clipe original pode ser
    mais curto que o bloco (por isso o -stream_loop na hora de gerar), e ai' o -ss
    caia depois do fim do arquivo: nao saia quadro nenhum, o ffmpeg dava erro, e a
    dissolvencia era descartada em silencio pelo except la' embaixo. O segmento tem
    exatamente a duracao do bloco, entao esse seek sempre acerta.
    """
    _run(["-ss", f"{max(0.0, dur - 0.05):.3f}", "-i", str(segmento),
          "-frames:v", "1", "-q:v", "2", str(saida)])


# O fade tem que zerar NO ULTIMO QUADRO da cauda, nao em DISSOLVE segundos. A cauda
# tem quadros(0.4) = 12 quadros, que cobrem 11/30 = 0.367s. Com d=0.4 o quadro 11 ainda
# saia com 8,6% de opacidade e a camada sumia de uma vez no quadro seguinte: um
# estalinho no fim de toda transicao. Com d = (12-1)/30 ela chega em zero sozinha.
FADE = (quadros(DISSOLVE) - 1) / FPS


def emendar(cauda, atual, saida):
    """Poe a CAUDA do bloco anterior por cima do atual, sumindo aos poucos.

    A cauda e' a continuacao do movimento do bloco que sai — nao os ultimos quadros
    dele. Com os ultimos quadros a imagem voltava 0.4s no tempo na troca.
    """
    fc = ["[1:v]format=rgba,fade=out:st=0:d=%.4f:alpha=1[ant]" % FADE,
          "[0:v][ant]overlay=0:0:eof_action=pass[v]"]
    _run(["-i", str(atual), "-i", str(cauda),
          "-filter_complex", ";".join(fc), "-map", "[v]",
          *X264, str(saida)])

def seg_avatar(avatar, inicio, dur, saida, vf=FIT):
    # -ss ANTES do -i: o ffmpeg pula direto pro ponto em vez de decodificar o arquivo
    # inteiro desde o comeco. Com re-encode continua no frame exato, e o lip-sync bate.
    _run(["-ss", f"{inicio:.3f}", "-i", str(avatar), "-an", "-vf", vf,
          "-frames:v", str(quadros(dur)), *X264, str(saida)])


def seg_imagem(img, dur, saida, variacao=0):
    q, vf = _kenburns(dur, variacao)
    # -loop 1 aqui e' seguro: perspective faz 1 quadro de saida por quadro de entrada.
    # (Com zoompan era proibido — ele fazia d quadros POR entrada: 1003s por imagem.)
    # -framerate ANTES do -i: imagem parada entra a 25 fps por padrao no ffmpeg. Com
    # isso o contador de quadros do filtro (on) so' chegava a 124 num bloco de 150, e
    # o zoom parava em 84% do percurso — dai' o pulo de 48px na troca de bloco.
    _run(["-framerate", str(FPS), "-loop", "1", "-t", f"{dur:.3f}", "-i", str(img),
          "-vf", vf, "-frames:v", str(q), *X264, str(saida)])


def seg_video(clipe, dur, saida, vf=None):
    # -stream_loop repete o clipe se ele for mais curto que o bloco
    _run(["-stream_loop", "-1", "-i", str(clipe), "-an",
          "-vf", vf or encaixe(clipe),
          "-frames:v", str(quadros(dur)), *X264, str(saida)])


def seg_card(camadas, dur, saida):
    """A capa entra caindo de cima enquanto o texto aparece em fade, logo depois."""
    cai, fade_capa, fade_txt = 0.55, 0.45, 0.65
    fc = [
        f"[1:v]fade=in:st=0.10:d={fade_capa}:alpha=1[capa]",
        f"[2:v]fade=in:st=0.55:d={fade_txt}:alpha=1[txt]",
        f"[0:v][capa]overlay=x=0:y='-70*max(0,1-(t-0.10)/{cai})':format=auto[a]",
        f"[a][txt]overlay=0:0,fps={FPS},setsar=1[v]",
    ]
    _run(["-loop", "1", "-t", f"{dur:.3f}", "-i", camadas["fundo"],
          "-loop", "1", "-t", f"{dur:.3f}", "-i", camadas["capa"],
          "-loop", "1", "-t", f"{dur:.3f}", "-i", camadas["texto"],
          "-filter_complex", ";".join(fc), "-map", "[v]",
          "-frames:v", str(quadros(dur)), *X264, str(saida)])


# ------------------------------------------------------------------ montagem
def _quantos_em_paralelo():
    """Quantos blocos renderizar ao mesmo tempo, conforme a maquina.

    Medido numa maquina de 32 nucleos:
      1 processo -> 64.4s  |  4 -> 26.9s (2.4x)  |  8 -> 25.8s  |  12 -> 24.5s
    Passar de 4 quase nao ajuda porque o proprio ffmpeg ja' espalha o filtro nas
    threads — mais processos so' disputam os mesmos nucleos. Por isso o teto e' 4.

    A conta e' nucleos/4: sobra CPU pra cada ffmpeg respirar. Num notebook de 4
    nucleos da' 1 (nada de paralelo), que e' o certo — la' rodar 4 juntos so'
    engasgaria a maquina inteira.
    """
    return max(1, min(4, (os.cpu_count() or 2) // 4))


EM_PARALELO = _quantos_em_paralelo()


def montar(plano_json, avatar, audio, clipes, saida, canal=None, tmp=None,
           on_status=None):
    plano = json.loads(Path(plano_json).read_text(encoding="utf-8"))
    avatar, audio = Path(avatar), Path(audio)
    if not avatar.exists():
        raise ErroMontagem("falta o avatar.mp4 — anexa ele na tela do vídeo.")
    if not audio.exists():
        raise ErroMontagem("falta o audio.mp3 — gera a narração primeiro.")

    tmp = Path(tmp or (Path(saida).parent / "_montagem"))
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    # ignore_errors=True e' proposital (arquivo aberto nao impede o resto), mas ele
    # falha CALADO. Se uma montagem foi interrompida, sobra ffmpeg segurando arquivo
    # aqui, o rmtree pula justamente esses, e a montagem seguinte ia juntar segmentos
    # que nunca foram gerados — quebrando 6 minutos depois, com erro incompreensivel.
    restos = [p.name for p in tmp.iterdir()]
    if restos:
        raise ErroMontagem(
            f"a pasta de trabalho nao ficou limpa ({len(restos)} arquivos presos). "
            "Provavelmente uma montagem anterior foi interrompida e ficou um ffmpeg "
            "rodando. Feche o app, abra o Gerenciador de Tarefas, encerre os processos "
            "ffmpeg.exe, apague a pasta _montagem e tente de novo.")

    camadas = card.montar(tmp, canal) if canal else None
    total = len(plano)
    # medido UMA vez: o avatar e' o mesmo arquivo do video inteiro
    vf_avatar = encaixe(avatar)

    # ---- 1. decide tudo antes de renderizar nada (so' contas, nao chama ffmpeg) ----
    tarefas, faltaram, variacao = [], 0, 0
    for i, b in enumerate(plano):
        n, tipo = b["n"], b["tipo"]
        # Cada bloco vai de onde ele comeca ate' onde o PROXIMO comeca. A duracao nao
        # e' b["dur"]: o SRT marca so' onde ha' fala, e entre um bloco e o outro sobra
        # a pausa da respiracao. Somadas davam 38s num video de 16min, e a imagem
        # acabava antes do audio.
        #
        # E o numero de quadros sai da POSICAO ABSOLUTA, nao da duracao. Arredondar
        # cada duracao separadamente empurrava sempre pro mesmo lado e o erro somava:
        # medido, 0,63s de atraso no fim do video. Assim o corte do bloco i cai sempre
        # em round(start*30) quadros, e um erro nunca passa pro bloco seguinte.
        fim = float(plano[i + 1]["start"]) if i + 1 < len(plano) else float(b["end"])
        q = max(2, round(fim * FPS) - round(float(b["start"]) * FPS))
        dur = q / FPS
        seg = tmp / f"seg_{n:03d}.mp4"
        t = {"n": n, "dur": dur, "seg": seg, "final": seg,
             "start": b["start"], "arquivo": None, "imagem": False, "variacao": 0}
        if tipo == "card" and camadas:
            t["como"] = "card"
        elif tipo == "avatar" or (tipo == "card" and not camadas):
            t["como"] = "avatar"
        else:
            clipe = _achar(clipes, n)
            if clipe is None:
                # sem o arquivo, mostra o avatar falando aquele trecho. Nunca uma tela
                # colorida de erro: o avatar sempre existe e parece intencional.
                t["como"] = "avatar"
                faltaram += 1
            elif clipe.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                t.update(como="imagem", arquivo=clipe, imagem=True, variacao=variacao)
                variacao += 1
            else:
                t.update(como="video", arquivo=clipe)
        tarefas.append(t)

    # ---- 2. os blocos, em paralelo ----
    feitos = [0]

    def render(t):
        if t["como"] == "card":
            seg_card(camadas, t["dur"], t["seg"])
        elif t["como"] == "avatar":
            seg_avatar(avatar, t["start"], t["dur"], t["seg"], vf_avatar)
        elif t["como"] == "imagem":
            seg_imagem(t["arquivo"], t["dur"], t["seg"], t["variacao"])
        else:
            seg_video(t["arquivo"], t["dur"], t["seg"])
        feitos[0] += 1
        if on_status and feitos[0] % 5 == 0:
            on_status(f"montando bloco {feitos[0]} de {total}…")

    with ThreadPoolExecutor(max_workers=EM_PARALELO) as ex:
        list(ex.map(render, tarefas))

    # ---- 3. dissolvencia entre blocos ----
    # TODA troca derrete, inclusive de e para o avatar. Duas excecoes:
    #   avatar -> avatar : sao pedacos seguidos do MESMO arquivo, ja' emendam sozinhos.
    #                      Derreter ali poria o avatar transparente por cima dele mesmo.
    #   card             : ele ja' tem a propria animacao de entrada dentro do seg_card.
    # Precisa ser uma segunda passada porque o fade usa o bloco anterior JA PRONTO — e
    # assim as duas passadas continuam paralelas, em vez de virar fila indiana.
    def derrete(i):
        t, ant = tarefas[i], tarefas[i - 1]
        if "card" in (t["como"], ant["como"]):
            return False
        if t["como"] == "avatar" and ant["como"] == "avatar":
            return False
        # os dois blocos precisam caber os 0,4s inteiros. Se um for mais curto, a cauda
        # sairia menor que o fade e a imagem sumiria de repente no meio da opacidade —
        # corte seco fica melhor que meia transicao.
        return t["dur"] >= DISSOLVE and ant["dur"] >= DISSOLVE

    emendas = [i for i in range(1, len(tarefas)) if derrete(i)]
    if emendas:
        if on_status:
            on_status(f"emendando {len(emendas)} transições…")

        def emenda(i):
            t, ant = tarefas[i], tarefas[i - 1]
            # arquivo NOVO, nunca por cima do original: a emenda seguinte esta' lendo
            # esse mesmo arquivo, e o Windows nao deixa substituir arquivo aberto.
            base = t["seg"].with_name(t["seg"].stem + "_c")
            saida = t["seg"].with_name(t["seg"].stem + "_e.mp4")
            try:
                if ant["como"] == "avatar":
                    # continua a fala de onde o bloco dele parou
                    cauda_avatar(avatar, ant["start"] + ant["dur"],
                                 base.with_suffix(".mp4"), vf_avatar)
                else:
                    if ant["como"] == "imagem":
                        fonte, parado = ant["arquivo"], False
                    else:                   # clipe: usa o ultimo quadro dele, parado
                        fonte, parado = base.with_suffix(".jpg"), True
                        # ant["seg"] e' o original, escrito na fase 2 e nunca mais
                        # tocado. ant["final"] pode estar sendo escrito agora por
                        # outra emenda.
                        ultimo_quadro(ant["seg"], ant["dur"], fonte)
                    cauda(fonte, ant["dur"], ant.get("variacao", 0),
                          base.with_suffix(".mp4"), parado=parado)
                emendar(base.with_suffix(".mp4"), t["seg"], saida)
                t["final"] = saida
            except Exception:
                # sem a emenda o corte fica seco, mas o video sai. Vale pra qualquer
                # erro, nao so' ErroMontagem: um disco cheio ou um arquivo travado numa
                # transicao nao pode jogar fora a montagem inteira que ja' rodou.
                pass

        with ThreadPoolExecutor(max_workers=EM_PARALELO) as ex:
            list(ex.map(emenda, emendas))

    # ---- 4. junta ----
    if on_status:
        on_status("juntando os blocos…")
    partes = [t["final"] for t in tarefas]
    lista = tmp / "lista.txt"
    lista.write_text("".join(f"file '{p.as_posix()}'\n" for p in partes), encoding="utf-8")
    mudo = tmp / "mudo.mp4"
    _run(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo)])

    if on_status:
        on_status("colando o áudio…")
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    _run(["-i", str(mudo), "-i", str(audio), "-map", "0:v", "-map", "1:a",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(saida)])

    shutil.rmtree(tmp, ignore_errors=True)
    dur_total = plano[-1]["end"] if plano else 0
    return {"saida": str(saida), "blocos": total, "faltaram": faltaram,
            "duracao": round(dur_total, 1)}
