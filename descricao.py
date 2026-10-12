# -*- coding: utf-8 -*-
"""Descricao do YouTube: escrita pelo Claude Code imitando o MODELO DE DESCRICAO do canal.

As regras sao as do descricao_projeto.txt (o projeto do Claude que fazia isso a mao),
sem a parte de conversa: aqui o app ja' entrega tudo de uma vez — a ficha do narrador,
o produto e o link do canal, o titulo e o roteiro DESTE video.

Os timestamps (se o modelo usa) saem dos tempos REAIS da narracao, lidos do blocos.srt.
O projeto antigo estimava por caractere (810 por minuto) e pedia pra conferir no video;
aqui o tempo de cada frase ja' e' conhecido.
"""
import re
from pathlib import Path

import claude_code

MIN_CHARS = 50            # descricao de video pode ser curta; abaixo disso e' sobra
MAX_MODELOS = 12

SYSTEM = """Você escreve a DESCRIÇÃO dos vídeos de um canal do YouTube, imitando fielmente o
modelo do canal. Abaixo estão {n} descrições REAIS que servem de modelo.

═══ O MOLDE ═══

As descrições de modelo não são exemplos genéricos: são a definição da voz do canal.
Extraia delas e reproduza:

- O TAMANHO. As do modelo têm em média {media} caracteres. Fique perto dessa média.
  Quem manda é o modelo, não o seu gosto.

- AS DUAS PRIMEIRAS LINHAS. É só isso que aparece antes do "mostrar mais". Veja o que
  as descrições do modelo põem ali (uma pergunta, a promessa do vídeo, a frase de
  abertura da narração) e faça igual. Nunca comece com saudação genérica, com o nome
  do canal, nem com "neste vídeo você vai aprender" se o modelo não começa assim.

- A ESTRUTURA. Em quantos blocos a descrição se divide, em que ordem, e o que vai em
  cada um: resumo, lista do que o vídeo cobre, bloco do produto, pedido de inscrição,
  aviso, hashtags. Reproduza os MESMOS blocos, na MESMA ordem.

- O VOCABULÁRIO E A CADÊNCIA. Comprimento das frases, formalidade, primeira pessoa,
  perguntas retóricas, emoji (se o modelo usa: quantos e onde; se não usa: nenhum).

- OS ELEMENTOS RECORRENTES. Pedido de inscrição, chamada pro comentário, aviso legal,
  hashtags, timestamps — se aparecem no modelo, aparecem na sua, no mesmo ponto e no
  mesmo formato. Se NÃO aparecem lá, você também não inventa.

═══ REGRAS ═══

1. Escreva INTEIRAMENTE em {idioma} — texto, listas, chamada pro comentário e
   hashtags, tudo. Nada de hashtag em inglês num canal de outro idioma.
2. A descrição é DESTE vídeo. Tudo sai do roteiro abaixo: os assuntos, os números, os
   nomes, a promessa da abertura. Não invente nada que não esteja lá e não descreva um
   vídeo genérico do nicho.
3. Não copie frases inteiras das descrições do modelo. Copie a FORMA, não o conteúdo.
4. Entregue APENAS o texto da descrição. Nada de "aqui está a descrição", nada de
   comentário seu, e NADA de markdown: o YouTube não renderiza ** nem #, aquilo aparece
   cru na tela.
5. Nenhum endereço de internet além do link do produto informado abaixo. Nem site, nem
   rede social, nem link de afiliado que apareça nas descrições do modelo.

═══ QUEM NARRA ═══

{ficha}
Esses dados são intocáveis. Não pegue emprestada a vida do narrador das descrições de
modelo: o nome, a cidade, a família e o produto que aparecem lá são de OUTRA pessoa. Se
a descrição de modelo assina com um nome, a sua assina com o nome da ficha.

{produto}
═══ TIMESTAMPS — só se o modelo tiver ═══

Se as descrições do modelo NÃO têm timestamps, a sua também não tem.
Se têm, use os tempos REAIS da narração que vêm junto com o roteiro (cada linha começa
com o minuto:segundo em que aquela fala começa). O primeiro é sempre 0:00. Use o mesmo
formato do modelo (0:00 ou 00:00), a mesma quantidade de marcações e títulos curtos no
mesmo estilo.

--- DESCRIÇÕES DE MODELO DO CANAL ---

{corpo}

--- FIM DAS DESCRIÇÕES DE MODELO ---"""

COM_PRODUTO = """═══ O PRODUTO DO CANAL ═══

O ÚNICO produto que existe neste canal é:
  Nome: {nome}
  Link: {site}

⚠ As descrições de modelo vendem o produto de OUTRA pessoa, com outro nome e outro
endereço. É proibido escrever o nome ou o endereço que aparecem lá. O único nome que
pode sair é "{nome}" e o único endereço é o link acima.

Ponha o produto ONDE a descrição de modelo põe o dela, do mesmo tamanho — normalmente
uma linha dizendo o que é, o link embaixo, e acabou. O link sai INTEIRO e sozinho na
linha, sem encurtador e sem texto colado nele. Não liste características, não prometa
resultado, não fale em preço, não use palavra de propaganda ("exclusivo",
"revolucionário", "imperdível", "garantido"). Uma vez só — repita no fim apenas se o
modelo repete.
"""

SEM_PRODUTO = """═══ ESTE CANAL NÃO VENDE NADA ═══

Nenhum nome de produto, nenhum endereço de internet, nenhum "link na descrição",
nenhum "saiba mais em". As descrições de modelo provavelmente vendem um livro ou
produto: IGNORE esse bloco, mas não deixe um buraco no lugar dele. Ali a descrição
PEDE alguma coisa: mantenha o pedido e tire a venda — peça a inscrição e faça uma
pergunta concreta, tirada DESTE vídeo, pra pessoa responder nos comentários.
"""

USER = """TÍTULO DO VÍDEO: {titulo}

ROTEIRO DO VÍDEO{com_tempos}:
{roteiro}

Escreva a descrição deste vídeo."""


def _mmss(s):
    s = int(round(float(s)))
    h, m, seg = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{seg:02d}" if h else f"{m}:{seg:02d}"


def roteiro_com_tempos(srt_path):
    """O roteiro como ele foi NARRADO: uma linha por bloco, com o minuto em que comeca."""
    try:
        import diretor
        blocos = diretor.parse_srt(srt_path)
    except Exception:
        return ""
    return "\n".join(f"[{_mmss(b['start'])}] {b['texto']}" for b in blocos)


def _ficha(canal):
    ficha = (canal or {}).get("personagem", "").strip()
    linhas = [l for l in ficha.splitlines()
              if l.strip().rstrip(":") and not l.strip().endswith(":")
              and "(um fato por linha)" not in l]
    if not linhas:
        return f"Idioma: {(canal or {}).get('idioma', '')}\n"
    return "\n".join(linhas) + "\n"


def gerar(modelo, canal, titulo, roteiro, modelos, srt_path=""):
    """modelos = [{titulo, texto}] do modelo de descricao. Devolve o texto pronto."""
    usados = modelos[:MAX_MODELOS]
    if not usados:
        raise ValueError("o modelo de descrição desse canal está vazio.")
    media = round(sum(len(m["texto"]) for m in usados) / len(usados))
    corpo = "\n\n".join(f"{{\n{m['texto']}\n}}" for m in usados)
    nome = (canal or {}).get("produto_nome", "").strip()
    site = (canal or {}).get("produto_site", "").strip()
    produto = COM_PRODUTO.format(nome=nome, site=site) if (nome and site) else SEM_PRODUTO
    sistema = SYSTEM.format(n=len(usados), media=media,
                            idioma=(canal or {}).get("idioma", "") or "o idioma da ficha",
                            ficha=_ficha(canal), produto=produto, corpo=corpo)
    tempos = roteiro_com_tempos(srt_path) if srt_path and Path(srt_path).exists() else ""
    pedido = USER.format(titulo=titulo,
                         com_tempos=" (cada linha com o tempo real da narração)" if tempos else "",
                         roteiro=tempos or roteiro)
    texto = claude_code.escrever(sistema, pedido, modelo=modelo)
    # rede de seguranca: markdown aparece cru no YouTube
    texto = re.sub(r"\*\*(.+?)\*\*", r"\1", texto)
    texto = re.sub(r"^#{1,6}\s+", "", texto, flags=re.M)
    return texto.strip().strip('"').strip()
