# -*- coding: utf-8 -*-
"""O estilo da casa. Igual pra todo canal — nao e' configuravel de proposito.

Os numeros de MISTURA nao foram chutados: saem da analise de um video de referencia
(20:04, 191 blocos, linha do tempo continua). Sao share por BLOCO, nao por tempo.

O SUFIXO existe porque os geradores puxam sozinhos pro look cinematografico (4K, bokeh,
color grading) e isso denuncia que e' IA. O sufixo empurra pro lado oposto: luz fraca e
chapada, cor suja, foto de camera basica. E' o que vende a ilusao de foto real.

ATENCAO — nao volte a palavra "camcorder" nem "home video" aqui. Elas traziam junto o
carimbo de data queimado no canto ("DEC 24 1998"): pro gerador a data faz parte da
estetica de camcorder, entao o "no text" nao segurava. O look agora e' de FOTO tirada
numa camera digital basica, que nao carimba nada.
"""

import re

# Share por bloco. Nao e' mais o do video de referencia (15/62/22): com aquilo o video
# virava enxurrada de imagem, uma por frase, e a maioria nao dizia nada. O avatar passou
# a ser o padrao e a imagem so' entra quando ganha o lugar.
MISTURA = {"avatar": 0.450, "imagem": 0.400, "video": 0.150}

# quantos b-rolls seguidos entre uma aparicao do avatar e a proxima (mediana medida: 4)
BROLLS_ENTRE_AVATARES = 4
ABERTURA_AVATAR_S = 8.8      # o video abre com o avatar segurando esse tanto

# Tamanho dos pedacos em que a narracao e' picada (vai pro DarkPlanner junto com o audio).
# Cada pedaco e' uma cena: e' esse numero que decide de quanto em quanto tempo a tela muda.
# Alvo = 6.3s, que e' o ritmo medido no video de referencia.
#   sem mandar nada -> 7.62s  (lento demais)
#   min=3 max=8     -> 5.28s  (rapido demais; o piso baixo deixa entrar pedaco de 3s)
#   min=5 max=8     -> 6.61s  <- o mais perto, e' o que usamos
BLOCO_MIN_S = 5
BLOCO_MAX_S = 8

# REGRA DE OURO DESTE SUFIXO: so' camera. Nunca cenario, nunca assunto, nunca nicho.
# Ele vai colado em TODOS os prompts de TODOS os canais — se listar "tabua de madeira,
# potes de vidro", o gerador poe isso em toda imagem (aconteceu) e um canal que nao
# seja de cozinha sai errado.
SUFIXO = (
    "Amateur snapshot taken in 2007 on a compact digital point-and-shoot camera. "
    "The subject fills the entire frame, photographed from close range. "
    "Even light, the subject evenly and clearly lit: no blown-out highlights, "
    "no harsh backlight, no dark corners. "
    "Flat natural color, slightly off auto white balance, small-sensor deep focus, "
    "mild noise and light JPEG softness. Ordinary and unstyled, nothing arranged "
    "for a photo. "
    "NOT cinematic: no studio lighting, no HDR, no bokeh, no drone, no film look, "
    "no lens flare, no styling. "
    "No date stamp, no timestamp, no burned-in date or time in the corner, "
    "no text, no captions, no watermark, no logo."
)


ENQUADRAMENTO = ("16:9 aspect ratio, full frame composition, no blurred background, "
                 "no square crop, no borders.")

# So' angulo e distancia. Luz e textura ja' vem no SUFIXO — repetir aqui e' o que
# entulhava o prompt e fazia o gerador tentar caber tudo no mesmo quadro.
MODIFICADORES_BONS = [
    "top-down", "directly overhead", "extreme close-up", "macro",
    "straight-on at eye level with the subject", "45-degree angle",
    "low angle close to the surface", "from just above it",
]

MODIFICADORES_PROIBIDOS = [
    "text", "sign", "label", "poster", "newspaper", "book page", "screen", "subtitle",
    "watermark", "logo", "price tag", "cinematic", "4K", "8K", "hyper detailed",
    "studio lighting", "drone", "aerial", "teal and orange", "bokeh", "film look",
    "date stamp", "timestamp", "camcorder", "VHS", "home video", "1080p footage",
]

# Valem pra QUALQUER canal. Nada aqui pode citar um nicho — o assunto sai do roteiro,
# nao daqui. Cada regra abaixo nasceu de um defeito medido, nao de palpite.
REGRAS = [
    "NUNCA peca texto na cena (placa, rotulo, embalagem escrita, jornal, tela, livro "
    "aberto, preco). O gerador rabisca letra errada e denuncia que e' IA.",
    "NUNCA peca look cinematografico: nada de drone, aereo, 4K, bokeh de cinema, "
    "iluminacao de estudio, hiper-nitido.",
    "NUNCA escreva camcorder, VHS, home video, 1080p footage nem nada que sugira "
    "filmadora antiga: o gerador queima a data no canto quando ve isso.",
    "NAO ESCREVA A LUZ. Nada de 'bright daylight', 'soft light', 'lit by a window'. "
    "A luz inteira ja' vem no sufixo; repetir aqui briga com ele e estoura a imagem. "
    "Medido: 99% dos prompts da 1a leva traziam luz propria.",
    "NAO TROQUE A COISA PELO QUE A GUARDA OU SUSTENTA. O recipiente vazio, a "
    "prateleira, a caixa fechada, a bancada, a maquina desligada nao sao o sujeito: "
    "o sujeito e' o que esta' dentro, em cima ou sendo feito. Medido no 1o video: em "
    "27 de 48 blocos a fala nomeava uma coisa e a imagem mostrou so' o vasilhame.",
    "FECHE O ENQUADRAMENTO. O sujeito ocupa o quadro inteiro. Plano do ambiente so' "
    "quando a narracao pedir o lugar — e' excecao, nao o normal.",
    "UM SUJEITO SO'. Nomeie A COISA e, no maximo, a superficie embaixo dela. Nao "
    "descreva o comodo, o que esta' ao fundo, ao lado, nem uma prateleira cheia. "
    "Expandir a cena e' o que deixou a 1a leva toda parecida.",
    "A IMAGEM PRECISA GANHAR O LUGAR DELA. O padrao e' o AVATAR. So' troque por "
    "imagem quando VER acrescenta ao que esta' sendo dito — quando a coisa e' o "
    "assunto daquele bloco e ver o formato, o estado ou o lugar dela muda o que a "
    "pessoa entende. Se a frase e' raciocinio, opiniao, contexto, transicao ou "
    "historia, nao ha' o que ver: e' avatar.",
    "NAO ILUSTRE PALAVRA CITADA DE PASSAGEM. O que decide nao e' a coisa ter sido "
    "nomeada, e' ela ser O ASSUNTO daquele bloco. A MESMA coisa merece imagem num "
    "video e nao merece noutro: se o video e' sobre ela, mostre sempre que ela "
    "aparecer; se ela so' passou no meio de uma frase sobre outra coisa, avatar. "
    "Uma imagem por substantivo enche o video de coisa que nao diz nada.",
    "QUANDO ENTRAR, seja o que a fala nomeia naquele bloco — nao o tema geral do "
    "video, nao um simbolo, nao um objeto de ambiente qualquer.",
    "FRASE ABSTRATA E' AVATAR, NAO IMAGEM. Tese, opiniao, 'aqui esta' uma coisa que', "
    "'ninguem faz isso por acaso', a apresentacao do narrador: nesses blocos escolha "
    "tipo avatar. Inventar um objeto generico pra ilustrar ideia e' o que enche o "
    "video de bugiganga aleatoria.",
    "FRASE QUE NOMEIA UM LUGAR E' PLANO ABERTO: o lugar visto de fora e de longe, "
    "com o que estiver em volta. Lugar nao se mostra em macro.",
    "VIDEO QUANDO O MOVIMENTO E' O ASSUNTO DA FRASE: algo escorrendo, fervendo, "
    "girando, caindo, sendo montado, gente andando, uma mao completando um gesto. "
    "Se a frase fala de uma coisa PARADA, e' imagem — e imagem e' o padrao; video "
    "e' a excecao com motivo.",
    "VARIE O ANGULO: de cima a prumo, macro rente, reto na altura do objeto, 45 "
    "graus. Repetir o mesmo angulo bloco apos bloco faz o video parecer a mesma "
    "foto o tempo todo.",
    "CURTO. Ate' umas 15 palavras. Prompt comprido faz o gerador tentar caber tudo "
    "e nada fica em primeiro plano.",
    "MAO NO QUADRO E' EXCECAO. So' quando a acao nao existe sem ela. Na duvida, "
    "mostre so' a coisa. Nunca alguem de frente falando: esse e' o avatar.",
    "A cena tem que caber na duracao do bloco: um bloco de 4s nao comporta uma acao "
    "com comeco, meio e fim.",
]


# Luz que a IA insiste em escrever na cena. O SUFIXO ja' manda a luz, igual pra todo
# bloco; escrever de novo aqui da' duas ordens ao gerador e estoura a imagem.
LUZ = re.compile(
    r"^\s*(the\s+)?(very\s+|quite\s+)?"
    r"(soft|bright|warm|cool|natural|dim|even|diffuse|indoor|overhead|gentle|pale|"
    r"low|flat|muted|golden|harsh|strong)?\s*"
    r"(day\s?light|sun\s?light|light(ing)?|illumination)\s*$", re.I)
LUZ_TRECHO = re.compile(
    r"\b(lit by|illuminated by|light from|daylight from|sunlight from|"
    r"from a (kitchen )?window|through a window|in soft light|in natural light|"
    r"in (soft|bright|warm|natural) daylight)\b", re.I)


# adjetivo de luz que sobra pendurado depois de cortar o trecho ("..., warm" )
ADJ_SOLTO = re.compile(
    r"[\s,;]*(soft|bright|warm|cool|natural|dim|even|diffuse|indoor|overhead|"
    r"gentle|pale|low|flat|muted|golden|harsh|strong)\s*$", re.I)


def limpar_cena(texto):
    """Tira a luz que a IA escreveu dentro da cena.

    O SUFIXO ja' define a luz, igual pra todo bloco. Quando o diretor escreve
    "soft daylight" tambem, o gerador recebe duas ordens de luz e a imagem estoura.
    Medido na 1a leva: 99% dos prompts traziam luz propria. Mesmo com a regra escrita
    no prompt do diretor, 30% ainda traziam — por isso a limpeza aqui e' mecanica.
    """
    saida = []
    for parte in (texto or "").split(","):
        parte = parte.strip()
        if not parte or LUZ.match(parte):
            continue                      # o trecho inteiro era luz
        m = LUZ_TRECHO.search(parte)
        if m:
            parte = parte[:m.start()].strip().rstrip(",;")
        anterior = None
        while parte and parte != anterior:  # "..., warm light from X" -> "..." 
            anterior, parte = parte, ADJ_SOLTO.sub("", parte).strip()
        if parte:
            saida.append(parte)
    return ", ".join(saida) if saida else (texto or "").strip()


def linha_flow(prompt_imagem, prompt_movimento=""):
    """Monta a linha do prompts_flow.txt no formato que o DarkPlanner lê no multiprompt.

    [I] e [V] sao atalhos DELE. Vao na MESMA linha:
      so' imagem: [I] <cena>. <sufixo> <enquadramento>
      com video : [I] <cena>. <sufixo> [V] <movimento>      <- sem o enquadramento
    """
    base = limpar_cena(prompt_imagem).rstrip(".")
    linha = f"[I] {base}. {SUFIXO}"
    mov = (prompt_movimento or "").strip()
    return f"{linha} [V] {mov}" if mov else f"{linha} {ENQUADRAMENTO}"
