# -*- coding: utf-8 -*-
"""Onde o narrador fala e onde ele para, lido do AUDIO — nao do SRT.

O SRT do DarkPlanner corta por duracao, nao por frase. Medido no video de 17min:
36% dos blocos terminavam no MEIO de uma frase e 40 blocos tinham DUAS frases dentro.
Na tela isso vira imagem que troca no meio de um pensamento e imagem que fica parada
enquanto o assunto ja' mudou.

A ideia aqui: o audio sabe a verdade. Silencio de 0,2s pra cima e' pausa de respiracao,
e fim de frase quase sempre cai numa. Medido no mesmo video: 81% dos fins de frase
estao a menos de 0,30s de uma pausa real, 93% a menos de 0,50s.

Entao da' pra REFAZER os blocos: quebra a narracao em frases, agrupa as frases dentro
da janela de duracao que o canal usa, e poe cada fronteira na pausa real mais proxima.
O tempo total nao muda em nenhum milissegundo — so' as fronteiras internas mudam.
"""
import re
import subprocess
from pathlib import Path

from caminhos import ffmpeg

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# -30dB / 0,2s: medido nas tres combinacoes (-35/0.15, -30/0.20, -25/0.25) no audio real.
# A de -25dB pegava respiracao no meio de frase como se fosse pausa; a de -35dB perdia
# pausa curta entre frases. Esta acha 430 pausas num audio de 14 minutos.
RUIDO_DB = -30
PAUSA_MIN_S = 0.20

# Ate' onde vale procurar uma pausa pra encaixar o fim de frase. Acima disso a pausa
# achada nao tem nada a ver com aquela frase e mexer so' piora.
BUSCA_S = 0.60

FIM_DE_FRASE = ".!?…"
# quando a frase nao cabe na janela, quebra aqui — na ordem de preferencia
RESPIRO = [";", ":", "—", ",", " – "]


def pausas(audio):
    """Os instantes de silencio no audio, em segundos. Devolve o MEIO de cada pausa.

    O meio, nao o comeco: cortar no comeco do silencio corta junto o finalzinho da
    ultima silaba, e cortar no fim ja' come o ataque da proxima palavra.
    """
    r = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(audio), "-af",
         f"silencedetect=noise={RUIDO_DB}dB:d={PAUSA_MIN_S}", "-f", "null", "-"],
        capture_output=True, text=True, creationflags=SEM_JANELA)
    saida = r.stderr or ""
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", saida)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", saida)]
    return sorted((a + b) / 2 for a, b in zip(ini, fim))


def _encaixar(t, ps, limite=BUSCA_S):
    """A pausa mais proxima de t. Se nao houver nenhuma perto, devolve t sem mexer."""
    melhor, dist = t, limite
    # lista pequena (centenas) e chamada poucas vezes: varrer e' mais claro que bisect
    for p in ps:
        d = abs(p - t)
        if d < dist:
            melhor, dist = p, d
        elif p > t + limite:
            break
    return melhor


def _frases(blocos):
    """Os blocos do SRT viram uma lista de frases com tempo de inicio e fim.

    O tempo de cada frase sai por interpolacao de CARACTERE dentro do bloco: o SRT so'
    da' o tempo do bloco inteiro, e nao existe marcacao por palavra. E' aproximacao,
    por isso o resultado passa pelo _encaixar depois — a pausa real corrige o erro.
    """
    saida = []
    for b in blocos:
        texto = b["texto"].strip()
        if not texto:
            continue
        n, ini, dur = len(texto), b["start"], b["end"] - b["start"]
        corte, pedacos = 0, []
        for m in re.finditer(r"[" + re.escape(FIM_DE_FRASE) + r"]+(?=\s|$)", texto):
            pedacos.append((corte, m.end()))
            corte = m.end()
        if corte < n:                     # sobra sem pontuacao = frase que continua
            pedacos.append((corte, n))
        for a, z in pedacos:
            t = texto[a:z].strip()
            if not t:
                continue
            saida.append({"texto": t,
                          "start": ini + dur * a / n,
                          "end": ini + dur * z / n,
                          "fecha": t.endswith(tuple(FIM_DE_FRASE))})
    # frase partida entre dois blocos do SRT: junta de novo
    juntas = []
    for f in saida:
        if juntas and not juntas[-1]["fecha"]:
            juntas[-1]["texto"] += " " + f["texto"]
            juntas[-1]["end"] = f["end"]
            juntas[-1]["fecha"] = f["fecha"]
        else:
            juntas.append(f)
    return juntas


def _partir(frase, maximo):
    """Frase comprida demais pra um bloco: quebra num respiro (; : — ,).

    Sem isso uma frase de 20s viraria um bloco de 20s, com a mesma imagem parada o
    tempo todo. Se nao houver respiro nenhum, deixa passar comprida — melhor um bloco
    longo do que um corte no meio de uma palavra.
    """
    if frase["end"] - frase["start"] <= maximo:
        return [frase]
    texto, n = frase["texto"], len(frase["texto"])
    dur = frase["end"] - frase["start"]
    meio = None
    for marca in RESPIRO:
        pos = [m.end() for m in re.finditer(re.escape(marca), texto)]
        # o respiro mais perto do meio do texto: divide em duas metades parecidas
        perto = [p for p in pos if 0.25 * n < p < 0.75 * n]
        if perto:
            meio = min(perto, key=lambda p: abs(p - n / 2))
            break
    if meio is None:
        return [frase]
    t = frase["start"] + dur * meio / n
    a = {"texto": texto[:meio].strip(), "start": frase["start"], "end": t, "fecha": False}
    b = {"texto": texto[meio:].strip(), "start": t, "end": frase["end"], "fecha": frase["fecha"]}
    return _partir(a, maximo) + _partir(b, maximo)


def alinhar(blocos, audio, minimo, maximo):
    """Refaz os blocos do SRT em cima de FRASES, com as fronteiras em pausa real.

    Devolve a lista no mesmo formato do parse_srt. O primeiro comeca onde o primeiro
    comecava e o ultimo termina onde o ultimo terminava: a duracao total e' a mesma,
    senao o audio e o video sairiam de sincronia.
    """
    if not blocos:
        return blocos
    fs = _frases(blocos)
    if not fs:
        return blocos
    curtas = []
    for f in fs:
        curtas.extend(_partir(f, maximo))

    # agrupa frases ate' encher a janela. Uma frase sozinha ja' passando do minimo
    # vira um bloco; abaixo disso junta com a proxima.
    grupos, atual = [], None
    for f in curtas:
        if atual is None:
            atual = dict(f)
            continue
        if (f["end"] - atual["start"]) <= maximo and (atual["end"] - atual["start"]) < minimo:
            atual["texto"] += " " + f["texto"]
            atual["end"] = f["end"]
        else:
            grupos.append(atual)
            atual = dict(f)
    if atual:
        grupos.append(atual)
    # ultimo grupo curto demais: gruda no anterior, senao sobra um pisca no fim
    if len(grupos) > 1 and (grupos[-1]["end"] - grupos[-1]["start"]) < minimo / 2:
        grupos[-2]["texto"] += " " + grupos[-1]["texto"]
        grupos[-2]["end"] = grupos[-1]["end"]
        grupos.pop()

    ps = pausas(audio)
    inicio, fim_total = blocos[0]["start"], blocos[-1]["end"]
    cortes = [inicio]
    for g in grupos[1:]:
        t = _encaixar(g["start"], ps) if ps else g["start"]
        # nunca deixa um corte passar do anterior nem invadir o fim do audio
        cortes.append(min(max(t, cortes[-1] + 0.20), fim_total - 0.20))
    cortes.append(fim_total)

    saida = []
    for i, g in enumerate(grupos):
        saida.append({"n": i + 1,
                      "start": round(cortes[i], 3),
                      "end": round(cortes[i + 1], 3),
                      "dur": round(cortes[i + 1] - cortes[i], 3),
                      "texto": g["texto"]})
    return saida


# ------------------------------------------------------------------ aparar as pausas
# Quanto de pausa fica de pe'. Medido nos dois videos reais: 27-28% do arquivo e'
# silencio, e aparar tudo para 0,35s economiza ~10% da duracao (85s num audio de 14min)
# sem soar apressado — a pausa mediana ja' e' 0,39-0,51s, entao a maioria quase nao muda
# e a economia vem das longas.
PAUSA_MAX_S = 0.35


def silencios(audio):
    """[(inicio, fim)] de cada silencio do audio, em segundos."""
    r = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(audio), "-af",
         f"silencedetect=noise={RUIDO_DB}dB:d={PAUSA_MIN_S}", "-f", "null", "-"],
        capture_output=True, text=True, creationflags=SEM_JANELA)
    saida = r.stderr or ""
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", saida)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", saida)]
    return list(zip(ini, fim))


def _formato(audio):
    """(taxa de amostragem, canais) do arquivo, lidos do cabecalho pelo ffmpeg."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(audio)],
                       capture_output=True, text=True, creationflags=SEM_JANELA)
    t = r.stderr or ""
    m = re.search(r"Audio:.*?(\d{4,6}) Hz,\s*(mono|stereo|(\d)(?:\.\d)? channels)", t)
    if not m:
        return 44100, 1
    canais = 1 if m.group(2) == "mono" else 2 if m.group(2) == "stereo" else int(m.group(3))
    return int(m.group(1)), canais


def _tempo_srt(s):
    h = int(s // 3600); mnt = int((s % 3600) // 60)
    seg = s - h * 3600 - mnt * 60
    return f"{h:02d}:{mnt:02d}:{int(seg):02d},{round((seg % 1) * 1000):03d}"


def escrever_srt(blocos, caminho):
    """Grava a lista de blocos de volta no formato SRT."""
    partes = []
    for i, b in enumerate(blocos, 1):
        partes.append(f"{i}\n{_tempo_srt(b['start'])} --> {_tempo_srt(b['end'])}\n"
                      f"{b['texto']}\n")
    Path(caminho).write_text("\n".join(partes), encoding="utf-8")
    return caminho


def aparar(audio, blocos, saida_audio, maximo=PAUSA_MAX_S, on_status=None):
    """Encurta as pausas longas do audio E reescreve os tempos dos blocos junto.

    As duas metades andam juntas de proposito. Cortar so' o audio e' a parte facil e e'
    o que toda ferramenta pronta faz — mas o blocos.srt continuaria com os tempos
    velhos, e a direcao e a montagem leem dele. Um audio 85s mais curto com um SRT
    intacto desmonta o video inteiro.

    De cada pausa maior que `maximo` sai o MIOLO, deixando `maximo/2` de cada lado.
    Cortar pelo meio nunca encosta no ataque nem na cauda das palavras em volta.

    Devolve (blocos_novos, quanto_encurtou_em_segundos).
    """
    audio = Path(audio)
    fora = []                                   # os trechos que somem, em segundos
    for a, b in silencios(audio):
        if b - a > maximo:
            fora.append((a + maximo / 2, b - maximo / 2))
    if not fora:
        return list(blocos), 0.0

    if on_status:
        on_status(f"cortando {len(fora)} pausas…")
    taxa, canais = _formato(audio)
    bpq = 2 * canais                            # s16le: 2 bytes por canal por amostra
    r = subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(audio),
         "-f", "s16le", "-acodec", "pcm_s16le", "-ar", str(taxa), "-ac", str(canais), "-"],
        capture_output=True, creationflags=SEM_JANELA)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "ignore")[-300:]
                           or "nao consegui ler o audio")
    cru = r.stdout

    # remonta o audio pulando os trechos de fora. Fatia de bytes, sem numpy: o app
    # instala so' anthropic/fastapi/uvicorn/pywebview/pillow, e nao vale mais uma
    # dependencia pra quem for receber isso pra fazer uma conta que e' de indice.
    pedacos, cursor = [], 0
    for a, b in fora:
        ia, ib = int(a * taxa) * bpq, int(b * taxa) * bpq
        if ia > cursor:
            pedacos.append(cru[cursor:ia])
        cursor = max(cursor, ib)
    pedacos.append(cru[cursor:])
    novo = b"".join(pedacos)

    if on_status:
        on_status("regravando o audio…")
    w = subprocess.run(
        [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "s16le", "-ar", str(taxa), "-ac", str(canais), "-i", "-",
         "-c:a", "libmp3lame", "-b:a", "192k", str(saida_audio)],
        input=novo, capture_output=True, creationflags=SEM_JANELA)
    if w.returncode != 0:
        raise RuntimeError((w.stderr or b"").decode("utf-8", "ignore")[-300:]
                           or "nao consegui gravar o audio novo")

    # e agora os tempos. Cada instante anda para tras o tanto que foi cortado ANTES
    # dele; um instante que caia dentro de um corte vai parar na borda dele.
    def mover(t):
        gasto = 0.0
        for a, b in fora:
            if t >= b:
                gasto += b - a
            elif t > a:
                return a - gasto
            else:
                break
        return t - gasto

    novos = []
    for i, bl in enumerate(blocos):
        ini, fim = mover(bl["start"]), mover(bl["end"])
        if fim - ini < 0.05:                    # bloco que virou nada: nao acontece com
            fim = ini + 0.05                    # pausa, mas nao deixo duracao zero passar
        novos.append({"n": i + 1, "start": round(ini, 3), "end": round(fim, 3),
                      "dur": round(fim - ini, 3), "texto": bl["texto"]})
    encurtou = sum(b - a for a, b in fora)
    return novos, encurtou
