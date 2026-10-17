# -*- coding: utf-8 -*-
"""O estilo da casa. Igual pra todo canal — nao e' configuravel de proposito.

SO' IMAGEM. O b-roll e' 100% imagem gerada (Flow so' imagem, nada de Veo); o movimento
vem do Ken Burns do montador. Nao existe mais bloco de video.

O LOOK e' o do preset "realista_imagem" (engenharia reversa de um canal alemao de
oficina): FOTO DOCUMENTAL REALISTA, nitida, luz natural, cor fiel. Substituiu o look de
filmadora velha (luz estourada, cor lavada, grao), que fazia tudo parecer SUJO — as
panelas e as cozinhas pareciam encardidas e o publico reclamava.
"""

# Share por BLOCO. Do preset: na referencia o avatar ocupava ~47% do tempo, alternando
# com trechos de imagem de ~7s.
MISTURA = {"avatar": 0.45, "imagem": 0.55}

# Quantas imagens seguidas entre uma aparicao do avatar e a proxima. Na referencia eram
# 76 trechos de avatar contra 77 de imagem (~91 imagens): quase sempre 1, as vezes 2.
BROLLS_ENTRE_AVATARES = 2

# Trecho de avatar seguido mais longo, em segundos (avatar_max_seg do preset).
AVATAR_MAX_S = 15

# Quanto tempo o cartao do produto fica na tela. Nao e' gosto: o cartao traz um QR, e
# quem esta' vendo precisa pegar o celular, abrir a camera e enquadrar. Medido num video
# real, o anuncio caiu em tres blocos do SRT e o cartao ficou 3,3s — nao da' pra ninguem.
# Dez segundos era o minimo; o usuario pediu 15 (2026-10-16). O roteiro escreve o
# anuncio pra durar isso e a direcao estica o cartao pros blocos seguintes se faltar.
CARD_ALVO_S = 15

# Tamanho dos pedacos em que a narracao e' picada (vai pro DarkPlanner junto com o audio).
# Cada pedaco e' uma cena: e' esse numero que decide de quanto em quanto tempo a tela muda.
# Alvo = 6.3s, que e' o ritmo medido no video de referencia.
#   sem mandar nada -> 7.62s  (lento demais)
#   min=3 max=8     -> 5.28s  (rapido demais; o piso baixo deixa entrar pedaco de 3s)
#   min=5 max=8     -> 6.61s  <- o mais perto, e' o que usamos
BLOCO_MIN_S = 5
BLOCO_MAX_S = 8

# REGRA DE OURO DESTE SUFIXO: so' o LOOK da foto. Nunca cenario, nunca assunto, nunca
# nicho. Ele vai colado em TODOS os prompts de TODOS os canais — se listar "tabua de
# madeira, potes de vidro", o gerador poe isso em toda imagem (aconteceu) e um canal que
# nao seja de cozinha sai errado. Texto exato do preset "realista_imagem".
SUFIXO = (
    "Photorealistic candid documentary photograph taken with a full-frame camera and a "
    "35mm lens at eye level, natural soft daylight, true-to-life colors, realistic skin "
    "and material textures, real everyday setting, sharp focus on the subject, background "
    "also in focus. Not cinematic, no color grading, no HDR, no studio lighting, not a 3D "
    "render, not CGI, not an illustration. No readable text, no logos, no captions, no "
    "watermark."
)

ENQUADRAMENTO = ("16:9 aspect ratio, full frame composition, no blurred background, "
                 "no square crop, no borders.")

# De onde a camera olha. A distancia (macro/close/medio/aberto) e' escolha separada.
# Oito angulos DIFERENTES entre si: a lista antiga tinha tres jeitos de dizer "de cima"
# e o video saia com camera de cima o tempo todo.
ANGULOS = [
    "from directly above, looking straight down",
    "from the side, at the same height as the subject",
    "from the front, straight on",
    "at a 45-degree angle from above",
    "from below, close to the surface it rests on",
    "from behind, over the shoulder of whoever is there",
    "three-quarter view, the subject turned slightly away",
    "from one end, looking along its length",
]

# Do preset. O sufixo ja' garante o look; estes o diretor usa POR PLANO, quando cabem.
MODIFICADORES_BONS = [
    "eye-level shot", "natural soft overcast daylight", "garage window light",
    "kitchen window light", "hands doing a task", "older man in work clothes",
    "work gloves", "weathered real objects", "everyday rural setting",
    "natural depth, background in focus",
] + ANGULOS

MODIFICADORES_PROIBIDOS = [
    "text", "sign", "label", "logo", "watermark", "subtitle", "writing", "cinematic",
    "HDR", "drone", "aerial", "teal and orange", "studio lighting",
    "professional color grade", "hyperrealistic", "8K", "ultra sharp", "3D render", "CGI",
    "illustration", "painting", "cartoon", "oversaturated", "fisheye", "plastic skin",
    # o look antigo de filmadora: e' exatamente o que deixava tudo com cara de sujo
    "camcorder", "VHS", "grainy",
]

# Valem pra QUALQUER canal. Nada aqui pode citar um nicho — o assunto sai do roteiro,
# nao daqui. Cada regra nasceu de um defeito medido ou do preset realista_imagem.
REGRAS = [
    "NUNCA peca texto legivel na cena (placa, rotulo, embalagem escrita, preco, jornal, "
    "tela, livro aberto, legenda). O gerador erra letra e idioma e denuncia que e' IA. "
    "Caderno, papel ou prancheta PODEM aparecer, mas com a escrita fora de foco, ilegivel.",
    "NUNCA peca look cinematografico ou artificial: nada de drone, aereo, teal-and-orange, "
    "iluminacao de estudio, HDR, render 3D, CGI, ilustracao, pintura, desenho, pele de "
    "plastico, cor saturada demais.",
    "NAO ESCREVA A CAMERA. O sufixo ja' diz que e' foto documental full-frame 35mm, igual "
    "pra todo bloco. Repetir aqui (camera, lente, 'photorealistic') so' briga com ele.",
    "ESCREVA A LUZ DO LUGAR, em poucas palavras no fim da cena: dia nublado, luz da janela "
    "da cozinha, luz da janela da garagem, fim de tarde, lampada de oficina. E' NATURAL e "
    "COERENTE com o lugar — nunca luz de estudio, nunca luz dramatica.",
    "LIMPO E CUIDADO, NUNCA ENCARDIDO. Panela, bancada, fogao, louca e ferramenta aparecem "
    "como numa casa bem cuidada: usados de verdade, mas limpos. Desgaste honesto (madeira "
    "gasta, ferro preto curado) pode; sujeira, gordura velha, ferrugem e bagunca NAO, a nao "
    "ser que a fala seja exatamente sobre isso.",
    "CENARIO DO PAIS DO ROTEIRO. A cozinha, a casa, a rua e as pessoas tem que ser do pais "
    "e da regiao de quem narra (uma cozinha de fazenda alema nao tem cara de americana).",
    "ANCORE NO LITERAL. A imagem mostra a coisa que a frase nomeia, do jeito mais imediato: "
    "fala 'o balde', mostra o balde em uso; fala 'a frigideira', mostra a frigideira com o "
    "que esta' sendo feito nela.",
    "IMAGEM PARADA: escolha o MOMENTO mais expressivo — a mao no meio do gesto, o resultado "
    "pronto, o ponto exato que a frase descreve. O movimento vem do Ken Burns do montador.",
    "MAOS FAZENDO A TAREFA sao bem-vindas: em plano medio ou fechado, a mao segurando a "
    "ferramenta, mexendo a panela, cortando. Pessoa mais velha trabalhando DE LADO ou DE "
    "COSTAS, nunca olhando pra camera e nunca falando: quem fala de frente e' o avatar.",
    "NAO TROQUE A COISA PELO QUE A GUARDA OU SUSTENTA. O recipiente vazio, a "
    "prateleira, a caixa fechada, a bancada, a maquina desligada nao sao o sujeito: "
    "o sujeito e' o que esta' dentro, em cima ou sendo feito. Medido no 1o video: em "
    "27 de 48 blocos a fala nomeava uma coisa e a imagem mostrou so' o vasilhame.",
    "VARIE A DISTANCIA, NAO SO' O ANGULO. Close nao pode ser o padrao de tudo: trinta "
    "closes seguidos cansam mesmo cada um sendo bonito. Alterne entre quatro distancias "
    "ao longo do video, mais ou menos em partes iguais:\n"
    "      MACRO   — a coisa bem de perto, mas INTEIRA e reconhecivel\n"
    "      CLOSE   — a coisa inteira preenchendo o quadro\n"
    "      MEDIO   — a coisa mais as maos ou a pessoa que a manuseia, de lado ou de costas\n"
    "      ABERTO  — o lugar onde aquilo acontece, com a coisa dentro dele\n"
    "   Diga a distancia na primeira palavra do prompt. Nunca use a mesma duas vezes "
    "seguidas.",
    "UM ASSUNTO SO' POR IMAGEM, seja qual for a distancia. No macro e no close, a "
    "coisa e a superficie embaixo dela. No medio, a coisa e quem a manuseia. No "
    "aberto, o lugar com a coisa dentro. O que nao pode e' listar tres objetos "
    "soltos e um fundo cheio — ai' o gerador nao sabe o que e' o principal.",
    "AS IMAGENS SAO DO ASSUNTO DO CANAL, NAO DE QUALQUER PALAVRA DITA. Antes de "
    "comecar, diga a si mesmo em uma frase do que este canal trata — sai do roteiro "
    "e do titulo. So' vira imagem o que PERTENCE a esse assunto. Se o canal "
    "e' de comida, sao os alimentos, os ingredientes, o prato, o preparo. Se e' de "
    "ferramenta, sao as ferramentas e as pecas. Cada canal tem as suas.",
    "OBJETO DE APOIO NAO E' ASSUNTO, mesmo sendo concreto e mesmo tendo sido nomeado. "
    "A narracao cita o tempo todo coisas que so' seguram a frase de pe'. O teste e' um "
    "so': isso e' uma das coisas de que o canal trata, ou so' apareceu porque a frase "
    "precisava citar? Se for a segunda, e' AVATAR.",
    "SE A NARRACAO PARA NUM OBJETO DE APOIO, O BLOCO E' AVATAR — mesmo que desse pra "
    "desenhar, mesmo que a frase descreva aquilo em detalhe. O narrador falando cobre "
    "esse trecho melhor do que qualquer imagem. So' volte pra imagem quando a fala voltar "
    "pro assunto do canal.",
    "NA DUVIDA, AVATAR. Uma imagem do assunto errado e' pior que o narrador falando: "
    "ela rouba a atencao e nao entrega nada.",
    "FRASE ABSTRATA E' AVATAR, NAO IMAGEM. Tese, opiniao, 'aqui esta' uma coisa que', "
    "'ninguem faz isso por acaso', a apresentacao do narrador: nesses blocos escolha "
    "tipo avatar. Inventar um objeto generico pra ilustrar ideia e' o que enche o "
    "video de bugiganga aleatoria.",
    "FRASE QUE NOMEIA UM LUGAR E' PLANO ABERTO: o lugar visto de fora e de longe, "
    "com o que estiver em volta. Lugar nao se mostra em macro.",
    "LISTA VIRA UMA IMAGEM POR ITEM. Quando a narracao enumera, cada item ganha o seu "
    "bloco com a sua imagem, na ordem em que sao ditos.",
    "CENA COM GENTE E' CENA, NAO OBJETO. Quando a narracao conta alguem fazendo alguma "
    "coisa — a mae no fogao, o pai na lavoura, a mulher servindo a mesa — mostre A "
    "PESSOA FAZENDO AQUILO, de costas ou de lado. Nao troque por um close do objeto.",
    "TEMPO E LUGAR SE MOSTRAM COM LUGAR. Quando a fala e' sobre uma epoca, uma data, "
    "um ano, uma cidade ou 'naquele tempo', mostre o lugar em plano aberto: a casa, a "
    "rua, a lavoura, a fachada.",
    "NAO DEIXE MONOTONO. Se voce ja' usou o mesmo tipo de plano nos ultimos blocos, "
    "mude: alterne close de coisa, maos trabalhando, plano aberto de lugar, macro de "
    "detalhe.",
    "VARIE O ANGULO — E ELE E' ESCOLHA SEPARADA DA DISTANCIA. Toda imagem tem as "
    "duas coisas: A QUE DISTANCIA (macro/close/medio/aberto) e DE ONDE A CAMERA OLHA. "
    "Rode entre os angulos da lista sem repetir o mesmo em blocos seguidos. DE CIMA no "
    "maximo em 1 de cada 5 imagens: um video inteiro visto de cima parece catalogo.",
    "CURTO. Ate' umas 20 palavras, contando a luz. Prompt comprido faz o gerador tentar "
    "caber tudo e nada fica em primeiro plano.",
    "MACRO E' DE COISA, NUNCA DE SUPERFICIE. De perto a coisa tem que continuar "
    "RECONHECIVEL: da' pra nomear o sujeito numa palavra? 'sal', 'cerveja', 'faca' passa. "
    "'o fundo do recipiente', 'a pelicula em cima da tabua' NAO passa — isso e' "
    "superficie, e de perto vira textura abstrata. Se for superficie, suba pra CLOSE.",
    "CADA BLOCO E' UMA FRASE INTEIRA — a imagem e' DAQUELA FRASE, nao do paragrafo. "
    "Leia a frase do bloco e pergunte: do que ELA fala? Se a frase mudou de coisa, a "
    "imagem muda junto; se ela nao fala de nada mostravel, e' AVATAR.",
]


def linha_flow(prompt_imagem):
    """A linha do prompts_flow.txt no formato que o DarkPlanner le' no multiprompt.

    [I] e' o atalho DELE pra imagem. So' imagem: nao existe mais o [V] de video.
      [I] <cena>. <sufixo> <enquadramento>
    """
    base = (prompt_imagem or "").strip().rstrip(".")
    return f"[I] {base}. {SUFIXO} {ENQUADRAMENTO}"
