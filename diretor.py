# -*- coding: utf-8 -*-
"""Direcao: le o blocos.srt e decide o que aparece na tela em cada bloco.

Entra: o SRT de blocos que o DarkPlanner devolveu junto com o audio.
Sai: os arquivos que o montador e o Flow esperam —
  plano.json        alimenta o montador
  prompts_flow.txt  cola no multiprompt do DarkPlanner (uma linha [I] por imagem)
  flow_map.csv      renomeia os downloads na ordem certa
  preview.txt       confere o plano com o olho

A direcao NAO decide quanto dura cada bloco — isso ja veio pronto do SRT. Ela decide
o TIPO de cada bloco (avatar, imagem ou card) e escreve os prompts de imagem.
So' imagem: o b-roll nao tem mais video.
"""
import csv
import json
import re
from pathlib import Path


import estilo

LOTE = 40          # blocos por chamada; acima disso a saida fica longa e cara de refazer


# ---------------------------------------------------------------- SRT
def parse_srt(caminho):
    """SRT -> [{n, start, end, dur, texto}] com tempo em segundos."""
    txt = Path(caminho).read_text(encoding="utf-8-sig")
    padrao = re.compile(
        r"(\d+)\s*\n(\d\d):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d+)\s*\n(.*?)"
        r"(?=\n\s*\n|\Z)", re.S)
    blocos = []
    for m in padrao.finditer(txt):
        g = m.groups()
        ini = int(g[1]) * 3600 + int(g[2]) * 60 + int(g[3]) + int(g[4]) / 1000
        fim = int(g[5]) * 3600 + int(g[6]) * 60 + int(g[7]) + int(g[8]) / 1000
        blocos.append({"n": int(g[0]), "start": round(ini, 3), "end": round(fim, 3),
                       "dur": round(fim - ini, 3),
                       "texto": " ".join(g[9].split())})
    if not blocos:
        raise ValueError("não consegui ler nenhum bloco desse SRT.")
    return blocos


# ---------------------------------------------------------------- prompt do diretor
SYSTEM = """Você é o diretor de fotografia de um canal do YouTube narrado, estilo "faceless".

O vídeo já existe como narração: uma lista de blocos com tempo exato e o texto falado
em cada um. Sua tarefa é decidir O QUE APARECE NA TELA em cada bloco e escrever os
prompts de IMAGEM.

═══ OS TIPOS ═══

avatar — o narrador aparece falando. Use para: a abertura, apresentações pessoais,
         opiniões, viradas de assunto, o fecho. É a âncora que costura o vídeo.
imagem — uma FOTO parada (o montador aplica zoom lento por cima). Não existe vídeo:
         todo b-roll é imagem.
{tipo_card}

═══ A MISTURA ALVO ═══

Aproximadamente: {p_avatar}% avatar · {p_imagem}% imagem.
É uma base, não uma cota rígida — o conteúdo manda. Mas não fuja muito.
Avatar e imagem se alternam: entre uma aparição do avatar e a próxima entram 1 ou
{entre} imagens. E o avatar não fica mais que uns {avatar_max} segundos seguidos na tela —
num trecho longo de fala abstrata, intercale uma imagem do assunto.

═══ O LOOK ═══

FOTO REALISTA DOCUMENTAL — nem cinematográfica, nem caseira e degradada. Parece foto de
verdade, tirada por um fotógrafo de reportagem na altura dos olhos: luz NATURAL (dia
nublado suave, luz da janela da cozinha ou da garagem), cores fiéis, textura real de
pele, tecido, madeira, metal. Pessoas comuns e críveis (rugas, mãos calejadas, roupa de
trabalho), cenário do dia a dia do país de quem narra. LIMPO E CUIDADO: panelas, fogão
e bancada como numa casa bem cuidada — nunca encardidos. O OPOSTO de render 3D,
ilustração, comercial de estúdio ou foto hiper-polida.

═══ COMO ESCREVER O prompt_imagem ═══

Em INGLÊS. A cena concreta e visual: distância e assunto na primeira parte, o ângulo,
e a LUZ do lugar no fim, em poucas palavras. Sem ponto final.
Use estes modificadores quando couberem: {mods}
NUNCA escreva estas palavras no prompt: {proibidos}

Os exemplos abaixo são de canais diferentes de propósito, e em distâncias diferentes.
Copie a FORMA — uma distância dita na primeira palavra, um assunto, o ângulo, a luz do
lugar, curto — nunca o conteúdo.

  "Macro of a thick pat of butter half sunk in a bowl of clear water, soft kitchen window light"
  "Close-up of a slice of fried bologna in a clean black cast iron pan, from the side, overcast daylight"
  "Medium shot of an older man's hands lifting a heavy pot off a stove, seen from the side, kitchen window light"
  "Wide shot of a tidy farmhouse kitchen with a pot steaming on the stove, soft morning light"
  "Macro of a bolt head on a car engine block, garage window light"
  "Medium shot of an older man in work gloves tightening a bolt under a raised car, from behind, workshop lamp light"
  "Wide shot of a small home garage with a car up on the lift, overcast daylight through the open door"
  "Close-up of a coil of rope on a boat deck, from above, overcast daylight"

Exemplos do tom ERRADO, todos tirados de uma leva real:
  "Close-up of a rustic pantry shelf lined with glass jars of preserved vegetables and
   dried beans, a small basket of potatoes beside them, soft daylight"
   -> uma prateleira cheia não é close: são dez assuntos e nenhum principal
  "Close-up of a worn notebook lying closed on a wooden kitchen table, a pencil resting
   beside it, bright daylight from a kitchen window"
   -> caderno, lápis, mesa e janela. Era pra ser só o caderno preenchendo o quadro
  "Close-up of a plain empty stoneware pot sitting on a wooden table"
   -> a fala daquele bloco era sobre MANTEIGA. Você trocou a coisa pelo vasilhame vazio
  "Close-up of an old iron stove with a bolt visible on its side"
   -> objeto de ambiente escolhido ao acaso porque a fala era abstrata. Mostre a coisa
      concreta do assunto mais próximo
  "Close-up of a greasy, burnt, crusted frying pan on a dirty stove"
   -> a fala não era sobre sujeira. Panela e fogão aparecem limpos e bem cuidados

NÃO escreva o sufixo de estilo nem a câmera — eles são acrescentados depois,
automaticamente.

═══ UM TRECHO INTEIRO, DIRIGIDO CERTO ═══

Isto é a abertura de UM vídeo real, bloco a bloco. Não é um roteiro do canal e não
é um molde a seguir: é só para você ver COMO se decide bloco a bloco — quando é
avatar, quando é plano aberto, quando são mãos. A sequência de planos aqui serve a
ESTE texto; o seu texto pede outra.

  "The pan came up out of a cardboard box in a basement in Iowa."
      avatar — ele está se apresentando ao assunto

  "A 9x13 aluminum pan dented along one edge with a strip of masking tape underneath."
      imagem · top-down da forma virada, a fita aparecendo, luz da janela do porão

  "On the tape in black marker the name Toliffson with one line drawn through it."
      imagem · MESMA fita, agora de lado e mais perto, o nome fora de foco
      >>> escrita nunca legível: a IA erra letra e idioma

  "That is a pan that outlived one woman and got handed to another."
      avatar — é a tese do bloco, não uma coisa

  "I have pulled a pan taped like that out of four houses in three states."
      imagem · plano aberto de pessoas entrando num salão de igreja, dia nublado

  "Different churches, same strip of tape, every time a 9x13."
      imagem · de lado, três formas iguais sobre uma mesa, luz de janela

  "Nobody tapes her own name to a pan she uses at home."
      avatar — é tese, não é coisa. Não invente objeto pra ilustrar ideia

  "You do that for one reason."
      imagem · mãos de uma senhora colando a fita na forma, de lado, luz da cozinha
      >>> mãos fazendo a tarefa: o momento exato do gesto

  "The house belonged to Vera Howland."
      avatar

  "87 when she died, belonged to Emanuel Lutheran for 61 years."
      imagem · PLANO ABERTO, uma igreja de longe, árvores e a estrada, dia nublado
      >>> lugar não se mostra em macro

  "I do the bedrooms first, then the closets, then the basement."
      imagem · um homem mais velho de costas carregando uma caixa num corredor de casa

  "The pan was in the basement."
      avatar

  "What was in the kitchen was better."
      imagem · a geladeira da cozinha, média distância, livros coloridos em cima

  "On top of the refrigerator there were nine spiralbound cookbooks."
      imagem · MESMOS livros, close, as capas sem escrita legível

  "Here is a thing about those books I have never heard anybody say out loud."
      avatar — abre um argumento, não descreve coisa


═══ REGRAS DURAS ═══

{regras}

═══ SAÍDA ═══

Um objeto por bloco recebido, na mesma ordem, com o mesmo "n". Não pule blocos,
não invente blocos."""

# so' entra no prompt quando o canal tem produto cadastrado
TIPO_CARD = """card   — o cartão do produto do canal. Marque TODOS OS BLOCOS SEGUIDOS do
         anúncio, não só um. Deixe prompt_imagem vazio — o cartão é desenhado pelo
         programa, não gerado.

         O anúncio quase nunca cabe num bloco só. Ele costuma cair em dois ou três:
         um que diz o nome e o endereço, outro que diz que o cartão está na tela, outro
         que manda apontar o celular. Marque a sequência inteira. O cartão traz um QR
         CODE, e quem está vendo precisa de uns {alvo} segundos pra pegar o telefone e
         enquadrar. Um bloco de três segundos não serve pra nada.

         Comece no primeiro bloco em que ele oferece o produto e pare quando a soma das
         durações passar de {alvo} segundos, ou quando o assunto voltar pro vídeo —
         o que vier primeiro. É UMA sequência no vídeo inteiro, não várias.

         O produto deste canal é "{nome}" ({site}).
         Ache o bloco do anúncio pelo SENTIDO, não por busca de palavra: a transcrição
         pode ter escrito o nome junto ou separado. É o trecho onde ele oferece o produto
         ao espectador e cita o site.
         Menções de passagem depois ("tem uma página no meu livro sobre isso") NÃO levam
         card — continuam sendo avatar ou imagem normal.
         Se nenhum bloco deste lote for o anúncio, simplesmente não use "card"."""

def _schema(tem_produto):
    return {
    "type": "object",
    "properties": {
        "blocos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "tipo": {"type": "string",
                             "enum": ["avatar", "imagem"] + (["card"] if tem_produto else [])},
                    "prompt_imagem": {"type": "string"},
                },
                "required": ["n", "tipo", "prompt_imagem"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["blocos"],
    "additionalProperties": False,
    }


def _system(canal=None):
    nome = (canal or {}).get("produto_nome", "").strip()
    site = (canal or {}).get("produto_site", "").strip()
    return SYSTEM.format(
        tipo_card=(TIPO_CARD.format(nome=nome, site=site, alvo=int(estilo.CARD_ALVO_S))
               if (nome and site) else ""),
        p_avatar=round(estilo.MISTURA["avatar"] * 100),
        p_imagem=round(estilo.MISTURA["imagem"] * 100),
        entre=estilo.BROLLS_ENTRE_AVATARES,
        avatar_max=estilo.AVATAR_MAX_S,
        mods=", ".join(estilo.MODIFICADORES_BONS),
        proibidos=", ".join(estilo.MODIFICADORES_PROIBIDOS),
        regras="\n".join(f"- {r}" for r in estilo.REGRAS),
    )


def dirigir(modelo, blocos, tema="", on_status=None, canal=None):
    """Manda os blocos em lotes pro Claude Code e devolve a decisão de cada um."""
    import claude_code
    sistema = _system(canal)
    tem_produto = bool((canal or {}).get("produto_nome") and (canal or {}).get("produto_site"))
    decisoes = {}
    total = len(blocos)

    for i in range(0, total, LOTE):
        lote = blocos[i:i + LOTE]
        if on_status:
            on_status(f"dirigindo blocos {lote[0]['n']}–{lote[-1]['n']} de {total}…")
        contexto = f"TEMA DO VÍDEO: {tema}\n\n" if tema else ""
        posicao = ("Estes são os PRIMEIROS blocos do vídeo — o primeiro deve ser avatar."
                   if i == 0 else
                   "Estes são os ÚLTIMOS blocos — feche com o avatar."
                   if i + LOTE >= total else
                   "Estes são blocos do meio do vídeo.")
        linhas = "\n".join(
            f'{b["n"]} | {b["dur"]:.1f}s | {b["texto"]}' for b in lote)
        # o --json-schema do Claude Code garante que volta JSON valido no formato pedido —
        # e' o que resolve o "JSON incompleto, tentando de novo" que o 100k sofria.
        r = claude_code.escrever(
            sistema,
            f"{contexto}{posicao}\n\nBLOCOS (n | duração | texto falado):\n{linhas}",
            modelo=modelo, schema=_schema(tem_produto))
        for d in r.get("blocos", []):
            decisoes[d["n"]] = d

    faltando = [b["n"] for b in blocos if b["n"] not in decisoes]
    if faltando:
        raise RuntimeError(f"a direção não devolveu {len(faltando)} bloco(s): "
                           f"{faltando[:10]}{'…' if len(faltando) > 10 else ''}")
    return montar_plano(blocos, decisoes)


def montar_plano(blocos, decisoes):
    """Decisoes por bloco -> plano.json. Serve tanto pra direcao da API quanto pra
    direcao feita a mao (as decisoes sao o mesmo dict {n: {tipo, prompt_imagem}}).

    O card e' UM so' no video inteiro, e cobre o ANUNCIO INTEIRO, nao um bloco. Quando o
    anuncio caia em tres blocos e so' o primeiro valia, o cartao ficava 3,3s na tela —
    tempo nenhum pra alguem apontar o celular no QR. Agora aceito blocos SEGUIDOS ate'
    juntar CARD_ALVO_S, e o montador junta tudo num segmento so'. Os lotes nao se
    enxergam: se um segundo lote marcar card depois que o anuncio acabou, vira avatar.
    """
    card_s, card_aberto, card_fechado = 0.0, False, False
    plano = []
    for b in blocos:
        d = decisoes[b["n"]]
        tipo = d["tipo"] if d["tipo"] in ("avatar", "imagem", "card") else "imagem"
        if tipo == "card":
            if card_fechado or card_s >= estilo.CARD_ALVO_S:
                tipo = "avatar"
            else:
                card_aberto = True
                card_s += float(b.get("dur") or 0)
        elif card_aberto:
            card_fechado = True
        prompt = (d.get("prompt_imagem") or "").strip() if tipo == "imagem" else ""
        if tipo == "imagem" and not prompt:
            tipo = "avatar"           # imagem sem prompt nao tem o que gerar
        plano.append({**b,
                      "tipo": tipo,
                      "fonte": "ia",          # tudo gerado; nao usamos banco de imagens
                      "prompt_imagem": prompt,
                      "qr": False,
                      "arquivo": (f'bloco_{b["n"]:03d}.jpg' if tipo == "imagem" else
                                  "card_produto.png" if tipo == "card" else "")})
    _esticar_card(plano)
    return plano


def _esticar_card(plano):
    """Garante o cartao CARD_ALVO_S na tela. Se o anuncio falado foi curto, o cartao
    continua por cima dos blocos seguintes ate' fechar o tempo. Mede como o montador
    corta: do inicio do 1o bloco de card ate' o inicio do bloco depois do ultimo.
    Nunca pega o ultimo bloco do video (o fechamento e' do avatar)."""
    cards = [i for i, p in enumerate(plano) if p["tipo"] == "card"]
    if not cards:
        return
    a, z = cards[0], cards[-1]

    def na_tela(z):
        fim = plano[z + 1]["start"] if z + 1 < len(plano) else plano[z]["end"]
        return float(fim) - float(plano[a]["start"])

    while na_tela(z) < estilo.CARD_ALVO_S and z + 1 < len(plano) - 1:
        z += 1
        plano[z].update(tipo="card", prompt_imagem="", arquivo="card_produto.png")


# ---------------------------------------------------------------- saidas
ICONE = {"avatar": "AVATAR", "imagem": "IMG   ", "card": "CARD  "}


def escrever_saidas(plano, pasta):
    """Grava os arquivos no formato que o montador e o Flow esperam."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    (pasta / "plano.json").write_text(
        json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")

    # imagem gerada por IA -> Flow. A ORDEM aqui e' a ordem dos downloads.
    ia = [b for b in plano if b["tipo"] == "imagem" and b["fonte"] == "ia"]
    with open(pasta / "prompts_flow.txt", "w", encoding="utf-8") as f:
        for b in ia:
            f.write(estilo.linha_flow(b["prompt_imagem"]) + "\n")

    with open(pasta / "flow_map.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "bloco", "arquivo_esperado", "tipo", "prompt"])
        for i, b in enumerate(ia, 1):
            w.writerow([i, b["n"], b["arquivo"], b["tipo"], estilo.linha_flow(b["prompt_imagem"])])

    conta = {t: sum(1 for b in plano if b["tipo"] == t) for t in ("avatar", "imagem", "card")}
    with open(pasta / "preview.txt", "w", encoding="utf-8") as f:
        f.write(f"PLANO DE MONTAGEM — {len(plano)} blocos "
                f"({conta['avatar']} avatar / {len(ia)} imagem / {conta['card']} card)\n")
        f.write("=" * 70 + "\n")
        for b in plano:
            # ordem = o numero com que o arquivo vai voltar do DarkPlanner
            ordem = next((i for i, x in enumerate(ia, 1) if x["n"] == b["n"]), None)
            marca = ICONE[b["tipo"]] + (f"  #{ordem}" if ordem else "")
            f.write(f'[{b["n"]:03d}] {b["start"]:7.1f}-{b["end"]:7.1f}s '
                    f'({b["dur"]:.1f}s) {marca}\n')
            f.write(f'      "{b["texto"][:110]}"\n')
            if b["prompt_imagem"]:
                f.write(f'      -> {b["prompt_imagem"][:150]}\n')

    return {"blocos": len(plano), "avatar": conta["avatar"], "imagem": conta["imagem"],
            "card": conta["card"], "flow": len(ia), "pasta": str(pasta)}
