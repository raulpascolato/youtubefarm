# -*- coding: utf-8 -*-
"""Direcao: le o blocos.srt e decide o que aparece na tela em cada bloco.

Entra: o SRT de blocos que o DarkPlanner devolveu junto com o audio.
Sai: os 5 arquivos, no mesmo formato do 100k —
  plano.json        alimenta o montador
  prompts_flow.txt  cola no batch do Flow (uma linha [I] por prompt)
  flow_map.csv      renomeia os downloads na ordem certa
  reais_map.csv     blocos que precisam de material REAL (stock), nao de IA
  preview.txt       confere o plano com o olho

A direcao NAO decide quanto dura cada bloco — isso ja veio pronto do SRT. Ela decide
o TIPO de cada bloco e escreve os prompts.
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
prompts de geração.

═══ OS TIPOS ═══

avatar — o narrador aparece falando. Use para: a abertura, apresentações pessoais,
         opiniões, viradas de assunto, o fecho. É a âncora que costura o vídeo.
imagem — uma foto parada (o montador aplica zoom lento por cima). É a maioria.
video  — filmagem com movimento real DENTRO da cena (mãos mexendo, vapor subindo,
         alguém girando um objeto na luz). Use só quando o movimento for o assunto.
{tipo_card}

═══ A MISTURA ALVO ═══

Aproximadamente: {p_avatar}% avatar · {p_imagem}% imagem · {p_video}% vídeo.
É uma base, não uma cota rígida — o conteúdo manda. Mas não fuja muito.
O avatar volta a cada {entre} b-rolls mais ou menos, em blocos isolados.
Imagem é o padrão; só escolha vídeo quando algo precisa se mexer.

═══ COMO ESCREVER O prompt_imagem ═══

Em INGLÊS. Descreva a cena concreta e visual, com enquadramento e luz. Sem ponto final.
Use estes modificadores quando couberem: {mods}
NUNCA escreva estas palavras no prompt: {proibidos}

Os exemplos abaixo são de canais diferentes de propósito, e em distâncias diferentes.
Copie a FORMA — uma distância dita na primeira palavra, um assunto, curto, sem luz —
nunca o conteúdo.

  "Macro of a thick pat of butter half sunk in a bowl of clear water"
  "Close-up of a slice of fried bologna in a black cast iron pan"
  "Medium shot of two hands lifting a heavy pot off a stove, seen from the side"
  "Wide shot of a small farm kitchen with a pot steaming on the stove"
  "Macro of a rusted bolt head on a car engine block"
  "Medium shot of a man from behind tightening a bolt under a raised car"
  "Wide shot of a repair shop with a car up on the lift"
  "Close-up of a coil of frayed rope on a boat deck"

Exemplos do tom ERRADO, todos tirados de uma leva real:
  "Close-up of a rustic pantry shelf lined with glass jars of preserved vegetables and
   dried beans, a small basket of potatoes beside them, soft daylight"
   -> uma prateleira cheia não é close, e a luz não é sua pra escrever
  "Close-up of a worn notebook lying closed on a wooden kitchen table, a pencil resting
   beside it, bright daylight from a kitchen window"
   -> dois objetos, a mesa, a janela e a luz. Era pra ser só o caderno preenchendo o quadro
  "Close-up of a plain empty stoneware pot sitting on a wooden table"
   -> a fala daquele bloco era sobre MANTEIGA. Você trocou a coisa pelo vasilhame vazio
  "Close-up of an old iron stove with a bolt visible on its side"
   -> objeto de ambiente escolhido ao acaso porque a fala era abstrata. Mostre a coisa
      concreta do assunto mais próximo

NÃO escreva o sufixo de estilo — ele é acrescentado depois, automaticamente.

═══ COMO ESCREVER O prompt_movimento ═══

Só para tipo "video". Uma frase curta em inglês dizendo o que se MOVE, sabendo que a
imagem já existe e vai ser animada. Sem luz, sem cenário, só o movimento. Exemplos:
  "Steam rising slowly off the surface, handheld slightly unsteady"
  "Syrup drips thickly down both sides, static composition"
  "The wheel turns half a rotation, handheld slightly trembling"
Para avatar e imagem, deixe vazio.

═══ UM TRECHO INTEIRO, DIRIGIDO CERTO ═══

Isto é a abertura de UM vídeo real, bloco a bloco. Não é um roteiro do canal e não
é um molde a seguir: é só para você ver COMO se decide bloco a bloco — quando é
avatar, quando é plano aberto, quando é vídeo. A sequência de planos aqui serve a
ESTE texto; o seu texto pede outra.

  "The pan came up out of a cardboard box in a basement in Iowa."
      avatar — ele está se apresentando ao assunto

  "A 9x13 aluminum pan dented along one edge with a strip of masking tape underneath."
      imagem · top-down da forma virada, a fita aparecendo

  "On the tape in black marker the name Toliffson with one line drawn through it."
      imagem · MESMA fita, agora de lado e mais perto, só o nome riscado

  "Above that in a different hand it said Howland."
      imagem · MESMA fita, mais perto ainda, o segundo nome

  "That is a pan that outlived one woman and got handed to another."
      imagem · uma senhora de costas segurando a forma na cozinha

  "I have pulled a pan taped like that out of four houses in three states."
      vídeo · pessoas andando em frente a um celeiro
      >>> é vídeo porque a frase é sobre um movimento, não porque é importante

  "Different churches, same strip of tape, every time a 9x13."
      imagem · top-down de três formas iguais sobre uma mesa

  "Nobody tapes her own name to a pan she uses at home."
      avatar — é tese, não é coisa. Não invente objeto pra ilustrar ideia

  "You do that for one reason."
      imagem · close da forma com uma mão colando a fita

  "The house belonged to Vera Howland."
      imagem · PLANO ABERTO de uma casa simples de roça, vista da rua

  "87 when she died, belonged to Emanuel Lutheran for 61 years."
      imagem · PLANO ABERTO, uma igreja de longe, árvores e a estrada
      >>> lugar não se mostra em macro

  "I do the bedrooms first, then the closets, then the basement."
      vídeo · um homem de costas andando pela cozinha

  "The pan was in the basement."
      imagem · um canto de porão com caixas e vidros, altura do olho

  "What was in the kitchen was better."
      imagem · a geladeira da cozinha, média distância, livros coloridos em cima

  "On top of the refrigerator there were nine spiralbound cookbooks."
      imagem · MESMA geladeira, close nos livros

  "the kind a church sells for $3 to put a roof on the fellowship hall."
      imagem · MESMOS livros, close ainda maior, um só deles

  "Here is a thing about those books I have never heard anybody say out loud."
      avatar — abre um argumento, não descreve coisa


═══ REGRAS DURAS ═══

{regras}

═══ SAÍDA ═══

Um objeto por bloco recebido, na mesma ordem, com o mesmo "n". Não pule blocos,
não invente blocos."""

# so' entra no prompt quando o canal tem produto cadastrado
TIPO_CARD = """card   — o cartão do produto do canal. Use em EXATAMENTE UM bloco do vídeo inteiro:
         aquele em que o narrador ANUNCIA o produto e diz o site. Deixe prompt_imagem e
         prompt_movimento vazios — o cartão é desenhado pelo programa, não gerado.

         O produto deste canal é "{nome}" ({site}).
         Ache o bloco do anúncio pelo SENTIDO, não por busca de palavra: a transcrição
         pode ter escrito o nome junto ou separado. É o trecho onde ele oferece o produto
         ao espectador e cita o site.
         Menções de passagem depois ("tem uma página no meu livro sobre isso") NÃO levam
         card — continuam sendo avatar ou b-roll normal.
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
                             "enum": ["avatar", "imagem", "video"] + (["card"] if tem_produto else [])},
                    "prompt_imagem": {"type": "string"},
                    "prompt_movimento": {"type": "string"},
                },
                "required": ["n", "tipo", "prompt_imagem", "prompt_movimento"],
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
        tipo_card=TIPO_CARD.format(nome=nome, site=site) if (nome and site) else "",
        p_avatar=round(estilo.MISTURA["avatar"] * 100),
        p_imagem=round(estilo.MISTURA["imagem"] * 100),
        p_video=round(estilo.MISTURA["video"] * 100),
        entre=estilo.BROLLS_ENTRE_AVATARES,
        mods=", ".join(estilo.MODIFICADORES_BONS),
        proibidos=", ".join(estilo.MODIFICADORES_PROIBIDOS),
        regras="\n".join(f"- {r}" for r in estilo.REGRAS),
    )


def dirigir(api_key, modelo, blocos, tema="", on_status=None, canal=None):
    """Manda os blocos em lotes e devolve a decisão de cada um."""
    import anthropic
    cliente = anthropic.Anthropic(api_key=api_key)
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
        # streaming: o SDK recusa max_tokens alto sem stream (a chamada pode passar de
        # 10 min). O output_config com json_schema garante que o texto volta JSON valido —
        # e' o que resolve o "JSON incompleto, tentando de novo" que o 100k sofria.
        with cliente.messages.stream(
            model=modelo,
            max_tokens=32000,
            system=[{"type": "text", "text": sistema,
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema",
                                      "schema": _schema(tem_produto)}},
            messages=[{"role": "user", "content":
                       f"{contexto}{posicao}\n\nBLOCOS (n | duração | texto falado):\n{linhas}"}],
        ) as fluxo:
            final = fluxo.get_final_message()
        bruto = "".join(c.text for c in final.content if c.type == "text")
        for d in json.loads(bruto).get("blocos", []):
            decisoes[d["n"]] = d

    faltando = [b["n"] for b in blocos if b["n"] not in decisoes]
    if faltando:
        raise RuntimeError(f"a direção não devolveu {len(faltando)} bloco(s): "
                           f"{faltando[:10]}{'…' if len(faltando) > 10 else ''}")

    # o card e' UM so' no video inteiro. Os lotes nao se enxergam, entao se dois lotes
    # marcarem card, o primeiro vale e os outros viram avatar (e' onde ele esta falando).
    ja_teve_card = False
    plano = []
    for b in blocos:
        d = decisoes[b["n"]]
        tipo = d["tipo"]
        if tipo == "card":
            if ja_teve_card:
                tipo = "avatar"
            else:
                ja_teve_card = True
        plano.append({**b,
                      "tipo": tipo,
                      "fonte": "ia",          # tudo gerado; nao usamos banco de imagens
                      "prompt_imagem": (d.get("prompt_imagem") or "").strip()
                                       if tipo not in ("avatar", "card") else "",
                      "prompt_movimento": (d.get("prompt_movimento") or "").strip()
                                          if tipo == "video" else "",
                      "qr": False,
                      "arquivo": (f'bloco_{b["n"]:03d}.mp4'
                                  if tipo in ("imagem", "video") else
                                  "card_produto.png" if tipo == "card" else "")})
    return plano


# ---------------------------------------------------------------- saidas
ICONE = {"avatar": "AVATAR", "imagem": "IMG   ", "video": "VIDEO ", "card": "CARD  "}


def escrever_saidas(plano, pasta):
    """Grava os 5 arquivos, no formato que o montador e o Flow esperam."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    (pasta / "plano.json").write_text(
        json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")

    # b-roll gerado por IA -> Flow. A ORDEM aqui e' a ordem dos downloads.
    ia = [b for b in plano if b["tipo"] in ("imagem", "video") and b["fonte"] == "ia"]
    with open(pasta / "prompts_flow.txt", "w", encoding="utf-8") as f:
        for b in ia:
            f.write(estilo.linha_flow(b["prompt_imagem"], b["prompt_movimento"]) + "\n")

    with open(pasta / "flow_map.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "bloco", "arquivo_esperado", "tipo", "prompt"])
        for i, b in enumerate(ia, 1):
            w.writerow([i, b["n"], b["arquivo"], b["tipo"],
                        estilo.linha_flow(b["prompt_imagem"], b["prompt_movimento"])])

    conta = {t: sum(1 for b in plano if b["tipo"] == t)
             for t in ("avatar", "imagem", "video", "card")}
    with open(pasta / "preview.txt", "w", encoding="utf-8") as f:
        f.write(f"PLANO DE MONTAGEM — {len(plano)} blocos "
                f"({conta['avatar']} avatar / {len(ia)} b-roll / {conta['card']} card)\n")
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
            if b["prompt_movimento"]:
                f.write(f'      ~> {b["prompt_movimento"][:150]}\n')

    return {"blocos": len(plano), "avatar": conta["avatar"], "imagem": conta["imagem"],
            "video": conta["video"], "card": conta["card"], "flow": len(ia),
            "pasta": str(pasta)}
