# -*- coding: utf-8 -*-
"""Roteirista: le o .json de treinamento do modelo e escreve o roteiro novo com o Claude
(o Claude Code logado no PC — ver claude_code.py; nao usa mais a API).

O .json de treinamento e' permissivo de proposito — voce cola o que tiver. Aceita:
  ["roteiro um...", "roteiro dois..."]
  [{"titulo": "...", "roteiro": "..."}, ...]        (ou narracao/script/texto/conteudo/...)
  {"roteiros": [...]}  {"scripts": [...]}  {"data": [...]}  {"items": [...]}
  {"video1": {...}, "video2": {...}}
"""
import json
import re

import claude_code


# chaves aceitas pro texto do roteiro, em ordem de preferencia
CHAVES_TEXTO = ("roteiro", "narracao", "narração", "script", "texto", "conteudo",
                "conteúdo", "transcript", "transcricao", "transcrição", "content", "body")
CHAVES_TITULO = ("titulo", "título", "title", "nome", "tema", "assunto")
CHAVES_LISTA = ("roteiros", "scripts", "videos", "vídeos", "data", "items", "itens",
                "exemplos", "treinamento", "dataset")

MIN_CHARS = 200   # abaixo disso nao e' roteiro de treino, e' sobra


def _texto_de(obj):
    """Extrai (titulo, texto) de um item do json, seja ele string ou dict."""
    if isinstance(obj, str):
        return "", obj
    if isinstance(obj, dict):
        texto = ""
        for k in CHAVES_TEXTO:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                texto = v
                break
        if not texto:
            # nenhuma chave conhecida: pega a maior string do dict
            candidatos = [v for v in obj.values() if isinstance(v, str)]
            if candidatos:
                texto = max(candidatos, key=len)
        titulo = ""
        for k in CHAVES_TITULO:
            v = obj.get(k)
            if isinstance(v, str) and v.strip() and v.strip() != texto.strip():
                titulo = v.strip()
                break
        return titulo, texto
    return "", ""


def parse_blocos(texto, minimo=MIN_CHARS):
    """Formato de TEXTO (nao e' JSON): cada roteiro fica entre chaves sozinhas na linha.

        {
        roteiro um, do jeito que voce colou, com aspas e quebras de linha a vontade
        }

        {
        # Titulo opcional na 1a linha
        roteiro dois
        }

    Existe porque colar 19 mil caracteres dentro de JSON obriga a escapar toda aspa e
    trocar cada quebra de linha por \\n. Aqui o texto entra cru.
    """
    roteiros = []
    dentro = False
    atual = []
    for linha in texto.splitlines():
        marca = linha.strip()
        if not dentro and marca == "{":
            dentro, atual = True, []
            continue
        if dentro and marca == "}":
            corpo = "\n".join(atual).strip()
            titulo = ""
            if corpo.startswith("#"):
                cabeca, _, resto = corpo.partition("\n")
                titulo, corpo = cabeca.lstrip("#").strip(), resto.strip()
            if len(corpo) >= minimo:
                roteiros.append({"titulo": titulo, "texto": corpo})
            dentro = False
            continue
        if dentro:
            atual.append(linha)
    if dentro:
        raise ValueError("tem um bloco aberto com { que nunca fechou com }.")
    return roteiros


def parse_conteudo(texto, minimo=MIN_CHARS):
    """Descobre sozinho o formato do arquivo: JSON ou blocos entre chaves.
    `minimo` e' o tamanho minimo de cada item (descricao de video e' mais curta)."""
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("o arquivo está vazio.")
    try:
        return parse_treinamento(json.loads(texto), minimo)
    except json.JSONDecodeError:
        pass          # nao e' JSON — tenta o formato de blocos
    roteiros = parse_blocos(texto, minimo)
    if not roteiros:
        raise ValueError(
            "não entendi o arquivo. Use JSON, ou ponha cada texto entre chaves "
            "sozinhas na linha:\n{\ntexto um\n}\n{\ntexto dois\n}\n"
            f"(cada um precisa de pelo menos {minimo} caracteres)")
    return roteiros


def parse_treinamento(dados, minimo=MIN_CHARS):
    """json cru -> [{titulo, texto}]. Levanta ValueError com motivo legivel."""
    bruto = dados
    if isinstance(bruto, dict):
        for k in CHAVES_LISTA:
            if isinstance(bruto.get(k), (list, dict)):
                bruto = bruto[k]
                break
    if isinstance(bruto, dict):
        bruto = list(bruto.values())
    if isinstance(bruto, str):
        bruto = [bruto]
    if not isinstance(bruto, list):
        raise ValueError("o .json precisa ser uma lista de roteiros (ou um objeto com "
                         "uma lista dentro, ex: {\"roteiros\": [...]}).")

    roteiros = []
    for item in bruto:
        titulo, texto = _texto_de(item)
        texto = (texto or "").strip()
        if len(texto) >= minimo:
            roteiros.append({"titulo": titulo, "texto": texto})

    if not roteiros:
        raise ValueError(f"nenhum texto encontrado (precisa de pelo menos {minimo} "
                         "caracteres por item).")
    return roteiros


# ---------------------------------------------------------------- geracao

SYSTEM = """Você é o roteirista de um canal do YouTube. Sua única função é escrever a NARRAÇÃO completa de um vídeo novo, imitando fielmente o modelo do canal.

Abaixo estão {n} roteiros REAIS deste canal. Eles não são exemplos genéricos: são a definição da voz do canal. Estude-os como um molde.

O que você deve extrair deles e reproduzir:
- O TIPO DE ABERTURA: como o primeiro parágrafo entra no assunto, que promessa faz, que gancho segura o espectador.
- A ESTRUTURA DO MEIO: como o conteúdo é dividido, o ritmo em que os assuntos entram, como cada bloco começa e emenda no próximo.
- O TIPO DE FECHAMENTO: como o vídeo resolve o gancho da abertura e como se despede.
- O VOCABULÁRIO E A CADÊNCIA: comprimento das frases, nível de formalidade, gírias e maneirismos, uso de primeira pessoa, perguntas retóricas, repetições.
- OS ELEMENTOS RECORRENTES: pedidos de inscrição, menções a produto, chamadas para o comentário — se aparecem nos roteiros de treino, devem aparecer no novo, nos mesmos pontos.
- OS DISPOSITIVOS ESTRUTURAIS, que são o que separa um roteiro bom de uma lista: um sistema de classificação aplicado a TODOS os itens (nos roteiros de treino cada vídeo inventa o SEU: função social, veredito, procedência...) — escolha UM para este vídeo, anuncie antes do item nº 1 e aplique em todos, sempre com a mesma palavra; a direção da contagem (subindo ou descendo, igual à dos roteiros de treino); e toda promessa feita na abertura tem que ser PAGA no fim, com a coisa concreta prometida.

REGRAS:
1. Escreva INTEIRAMENTE em {idioma}.
2. Entregue APENAS o texto corrido da narração. Nada de títulos de seção, marcações de cena, rubricas, colchetes, timestamps ou comentários seus.
3. Não copie frases inteiras dos roteiros de treino. Copie a FORMA, não o conteúdo — o assunto novo é outro.
4. COMPRIMENTO — restrição dura, não sugestão:
   MÍNIMO {minimo} caracteres · ALVO {alvo} · MÁXIMO {maximo} caracteres.

   Passar do máximo é um erro tão grave quanto entregar curto. O vídeo tem duração
   contratada: cada {cpm} caracteres viram 1 minuto de narração, então {alvo}
   caracteres = {dur} minutos. Um roteiro 50% maior vira um vídeo 50% mais longo.

   Se o título promete uma quantidade de itens (ex: "25 receitas"), divida o
   orçamento entre eles: {alvo} caracteres no TOTAL, não por item. Com muitos itens
   cada um fica curto — isso é o esperado, não um defeito.

   O QUE NUNCA ENCOLHE, nem pra caber no limite:
   - o gancho da abertura e a promessa que ele faz
   - a virada do meio
   - o fechamento, incluindo a resolução do gancho lá do começo
   - o ponto-chave de cada item: a informação que a pessoa veio buscar
   Isso sai inteiro, no tamanho que precisar. É o que segura o espectador.

   O QUE ENCOLHE quando falta espaço:
   - exemplos extras além do primeiro
   - histórias de apoio que só reforçam algo já dito
   - adjetivo, descrição de cenário, frase que reafirma o parágrafo anterior

   Antes de encerrar, estime quanto escreveu. Se passou do máximo, corte SÓ da
   segunda lista. Item com pouco espaço vira: o ponto-chave dito de forma direta,
   sem a história em volta — nunca um item pela metade nem um item cortado fora.
5. Mantenha o mesmo grau de concretude dos roteiros de treino: se eles usam números, nomes, datas e detalhes específicos, o seu também usa.

═══ RETENÇÃO — REGRAS MEDIDAS NOS VÍDEOS DO PRÓPRIO CANAL ═══

Estas regras vêm da curva de retenção de vídeos reais deste canal e valem ACIMA do molde:
onde o molde e estas regras discordarem, siga estas regras. Elas falam de FORMA, nunca
de assunto.

1. O CONTEÚDO COMEÇA CEDO. A primeira informação útil (a parte 1, o item nº 1) começa
   até 12% do roteiro. Medido: nos vídeos em que ela só chegava aos 23–26% (3:35–4:00
   de vídeo), o público foi embora esperando. Tudo o que vem antes cabe nesses 12%:
   gancho até 5%; o objeto/cenário até 3%; apresentação do narrador em no máximo duas
   frases; o anúncio das partes em duas frases; o pedido de inscrição em uma.
   Não existe bloco de família/parente separado antes do conteúdo. Se a história de um
   parente serve ao vídeo, ela entra em uma ou duas frases dentro do gancho, ou mais
   tarde, no meio, como recompensa (ver regra 5).

2. A RESPOSTA SÓ NA SEÇÃO DELA. O truque, o segredo, a peça guardada pro fim — o que o
   título e o gancho prometem — não pode ser dito nem insinuado de um jeito que dê pra
   adivinhar antes da seção final. No gancho, no objeto e na apresentação você pode
   dizer o RESULTADO ("nunca caiu uma crosta") e o ERRO de todo mundo; nunca o que a
   pessoa fazia de certo ("ela nunca apertava", "ela levava ao forno"). Se o título já
   entrega parte da resposta, o gancho abre uma pergunta NOVA que o título não responde
   e segura essa resposta até o fim. Medido: o vídeo que disse a resposta no primeiro
   minuto perdeu mais da metade de quem ainda assistia entre 3:00 e 3:40.

3. O GANCHO TEM UM FATO E UMA CONTRADIÇÃO NAS DUAS PRIMEIRAS FRASES. Uma coisa concreta e
   verificável (uma pessoa com nome ou ofício, um lugar, um número, um objeto) e uma
   afirmação que contraria o que o espectador acha. Descrição do erro, no máximo três
   frases antes da virada. Medido: abrir com nove frases descrevendo o fracasso deu 49%
   de público aos 30 segundos; abrir com uma pessoa, um lugar, um número e uma frase que
   contraria o senso comum deu 70%.
   Ainda no gancho, prometa duas ou três recompensas ESPECÍFICAS do meio e do fim pelo
   número ou pela posição, como os roteiros de treino fazem ("a parte 4 é a que quase
   todo mundo erra", "a 6 vai parecer piada até eu explicar"). Promessa genérica ("no
   fim eu conto o segredo") não segura ninguém.

4. O PRODUTO VEM DEPOIS DO PRIMEIRO VALOR. O anúncio (ou, sem produto, o bloco de
   inscrição/comentário) entra logo DEPOIS da parte 1, nunca entre o gancho e o
   primeiro conteúdo, e cabe em cerca de 400 caracteres com piada e tudo.

5. UM RE-GANCHO A CADA ~2.000 CARACTERES (mais ou menos a cada duas partes, ~2 minutos).
   Uma frase de progresso + uma promessa concreta do que vem ("três partes feitas; a
   próxima é a que estraga a maioria sem ninguém perceber"), ou a volta ao objeto/pessoa
   da abertura com um detalhe NOVO que só agora faz sentido. Nunca passe de ~2.500
   caracteres sem uma frase que puxe o espectador pra frente. Medido: os vídeos do canal
   tinham zero re-ganchos no meio e a curva só descia.

6. CADA PARTE ABRE PELO QUE SE VÊ. Primeira frase: o erro visível ou o resultado. Depois
   o que fazer. Depois o porquê, em no máximo três ou quatro frases — de preferência uma
   comparação do dia a dia em vez de um parágrafo de física. Nenhuma parte passa de
   ~1.500 caracteres, e alterne partes curtas e longas.

7. O FIM É CURTO. A seção do truque começa entre 70% e 78% do roteiro e, depois que ele é
   entregue, sobram no máximo 15%: a parte honesta em até três pontos curtos, a
   recapitulação em até seis frases curtas (ou nenhuma), a "uma coisa só" em uma ou duas
   frases, o objeto final e a pergunta pros comentários. Medido: com 28–36% do vídeo
   sobrando depois do truque, o público saía assim que ele era entregue.

8. TERMINE COM UMA PONTE PRO PRÓXIMO VÍDEO, como os roteiros de treino em lista fazem:
   o assunto do próximo e uma coisa concreta e misteriosa que vai aparecer nele ("e tem
   uma coisa que estava em toda casa e que ninguém come mais no café — quando eu disser
   o que é, você vai achar que é brincadeira"). Uma promessa, não um "se inscreva".

{personagem}
{produto}
--- ROTEIROS DE TREINAMENTO DO CANAL ---

{corpo}

--- FIM DOS ROTEIROS DE TREINAMENTO ---"""


# Os roteiros de treino quase sempre vem de um canal que VENDE alguma coisa, e as
# mencoes ao produto estao espalhadas por eles. Sem instrucao explicita a IA copia esse
# padrao e inventa um produto que nao existe. Por isso os dois blocos abaixo.
COM_PRODUTO = """═══ O PRODUTO DESTE CANAL ═══

O ÚNICO produto que existe neste canal é:
  Nome: {nome}
  Site: {site}

⚠ ATENÇÃO AO NOME. Os roteiros de treinamento vendem o produto de OUTRA pessoa, com
outro nome e outro site. Aquilo é exemplo de FORMATO, não de conteúdo. É proibido
escrever o nome ou o endereço que aparecem nos roteiros de treino. O único nome que
pode sair no seu texto é "{nome}" e o único endereço é "{site}".

COMO ANUNCIAR — uma vez só, entre 10% e 20% do roteiro:

ANTES DE ESCREVER, PROCURE O GANCHO QUE JÁ ESTÁ NO SEU PRÓPRIO ROTEIRO.
Leia o que você já escreveu e veja se o narrador mencionou alguma coisa que tenha
a ver com o produto — um caderno onde ele anota, uma lata, um costume dele, uma
pergunta que alguém fez a ele. Quase sempre tem, porque o produto nasceu da mesma
vida que o roteiro conta. O anúncio sai DALI e não parece colado.
Se o gancho estiver alguns pontos fora da janela de 10% a 20%, vá até ele. A janela
é o alvo; o gancho é melhor que o alvo. Só não passe da metade do vídeo.
Se não houver gancho nenhum, aí sim escreva o anúncio do zero, dentro da janela.
Em qualquer caso, o anúncio vem DEPOIS da primeira parte de conteúdo, nunca antes dela:
quem ainda não recebeu nada não fica pra ouvir uma oferta.

O anúncio não é um intervalo comercial. É uma história curta que explica POR QUE o
produto existe, e essa explicação é o que prova a autoridade do narrador. Observe como
os roteiros de treino fazem e reproduza o mecanismo:

1. Um motivo humano pra ter criado aquilo — alguém pediu, o conhecimento ia se perder,
   cansou de repetir a mesma resposta. Nunca "eu criei um produto incrível".
2. Uma piada com ele mesmo ou uma farpa carinhosa em alguém. Tira o cheiro de venda.
3. O nome do produto, dito com naturalidade, e onde achar: "{site}". Escreva o
   endereço exatamente assim: nunca "https://" e nunca "www" na frente. Isso vai ser
   FALADO por uma voz.
   Durante o anúncio inteiro aparece na tela um cartão com a capa, o endereço e um
   QR CODE, e ele fica {seg} SEGUNDOS — o tempo de alguém pegar o telefone e
   enquadrar o código. Então escreva o anúncio PARA esses {seg} segundos: diga o nome,
   diga o endereço, e só então mande apontar a câmera do celular pro código que está
   na tela, ou pegar o link na descrição.
   TAMANHO: do momento em que ele diz o nome do produto até o fim do anúncio (antes
   do "voltando"), escreva PELO MENOS {chars} caracteres — é isso que dá {seg}
   segundos de fala. Menos que isso e o cartão some antes de dar tempo. Preencha com
   o que o produto TEM de concreto ligado a este vídeo, nunca repetindo o endereço.
   Não amontoe as três coisas numa frase só nem jogue o "aponta o celular" como
   remendo no fim. Sem insistir, e sem repetir o endereço depois.
4. Saída rápida. Uma frase curta e volta pro assunto ("Enfim, voltando").

NÃO liste características, não prometa resultado, não fale em preço, não use palavra de
propaganda ("exclusivo", "revolucionário", "imperdível"). O produto tem que soar como
consequência natural da experiência do narrador, não como o objetivo do vídeo.

DEPOIS DO ANÚNCIO: pode citar de passagem quando for natural ("tem uma página sobre isso
lá"), mas NUNCA repita o endereço nem o convite. Uma vez só no vídeo inteiro.

"""

SEM_PRODUTO = """═══ ESTE CANAL NÃO VENDE NADA ═══

Os roteiros de treinamento mencionam um livro/produto do autor. IGNORE essas menções.

Atenção: elas não estão ali só pra vender — elas provam que o narrador tem conhecimento
acumulado e organizado. Se você simplesmente apagar, o roteiro perde autoridade.
Então MANTENHA O EFEITO e troque a origem:

  onde o modelo diria  "tem uma página no meu livro sobre isso"
  você diz             "anotei isso num caderno que carrego há trinta anos"

NUNCA cite livro à venda, produto, curso, site, link, "descrição" ou "comentário fixado".
Nenhum nome de produto e nenhum endereço de internet pode aparecer no texto.

E o momento onde os roteiros de treino fazem o anúncio NÃO pode virar um buraco. Nesse
ponto do vídeo eles pedem inscrição e comentário junto com o produto — mantenha essa
parte. Peça pra pessoa se inscrever, e faça uma pergunta concreta pra ela responder nos
comentários (de onde está assistindo, se tem um desses em casa, o que aconteceu com ela).
O roteiro tem que ficar cheio ali, só que sem nada à venda.

"""

USER = """Escreva a narração completa do próximo vídeo deste canal.

TÍTULO DO VÍDEO: {titulo}
DURAÇÃO ALVO: {dur} minutos de narração (~{alvo} caracteres)
IDIOMA: {idioma}

Siga o molde dos roteiros de treinamento: mesmo tipo de abertura, mesma estrutura de meio, mesmo tipo de fechamento. Comece direto pela primeira palavra da narração."""

# quanto de treino cabe no prompt sem virar desperdicio (o contexto e' 1M, mas
# 6 roteiros longos ja ensinam o molde melhor que 40)
MAX_ROTEIROS = 6
MAX_CHARS_TREINO = 260_000


def montar_treino(roteiros):
    """Escolhe os roteiros de treino: os mais longos primeiro (sao os mais completos)."""
    ordenados = sorted(roteiros, key=lambda r: len(r["texto"]), reverse=True)
    usados, total = [], 0
    for r in ordenados[:MAX_ROTEIROS]:
        if total + len(r["texto"]) > MAX_CHARS_TREINO:
            break
        usados.append(r)
        total += len(r["texto"])
    return usados or ordenados[:1]


def bloco_produto(canal, cpm=1060):
    """Escolhe qual das duas instruções entra no prompt."""
    nome = (canal or {}).get("produto_nome", "").strip()
    site = (canal or {}).get("produto_site", "").strip()
    if not (nome and site):
        return SEM_PRODUTO
    import estilo
    # no roteiro o endereco entra curto: e' texto pra ser FALADO, nao pra clicar
    site = re.sub(r"^(https?://)?(www\.)?", "", site, flags=re.I).rstrip("/")
    seg = int(estilo.CARD_ALVO_S)
    # o trecho do cartao tem que DURAR na fala: segundos -> caracteres no ritmo do canal
    return COM_PRODUTO.format(nome=nome, site=site, seg=seg,
                              chars=round(cpm * seg / 60 / 10) * 10)


CHECAGEM = """Leia o roteiro abaixo e extraia UM fato: o narrador anuncia um produto
PRÓPRIO ao espectador (livro, ebook, curso, guia) — mandando comprar, baixar, acessar um
site, ver o link na descrição ou no comentário fixado?

Cuidado com o falso positivo: um livro como OBJETO da história ("um livro antigo de
registros", "li num livro de referência") NÃO é anúncio. Só conta produto DO PRÓPRIO
NARRADOR oferecido a quem assiste.

Se houver anúncio, copie exatamente o nome do produto e o endereço de internet ditos.

ROTEIRO:
{roteiro}"""

CHECAGEM_SCHEMA = {
    "type": "object",
    "properties": {
        "anuncia": {"type": "boolean"},
        "nome_citado": {"type": "string", "description": "nome do produto, ou vazio"},
        "site_citado": {"type": "string", "description": "endereço citado, ou vazio"},
        "trecho": {"type": "string", "description": "o trecho do anúncio, ou vazio"},
    },
    "required": ["anuncia", "nome_citado", "site_citado", "trecho"],
    "additionalProperties": False,
}


def _cru(s):
    """Só letras e números, minúsculo — pra comparar 'The Rust Ledger' com 'rust ledger'
    e 'https://Rustledger.com/' com 'rustledger.com'."""
    s = re.sub(r"^https?://", "", (s or "").strip().lower()).rstrip("/")
    s = re.sub(r"^www\.", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _combina(a, b):
    a, b = _cru(a), _cru(b)
    return bool(a and b and (a in b or b in a))


def checar_produto(modelo, roteiro, canal):
    """Depois de gerar: o roteiro anunciou o que devia? Devolve o aviso (ou '').

    Cobre os dois lados:
      - canal SEM produto que mesmo assim saiu vendendo algo;
      - canal COM produto cujo roteiro anunciou OUTRO produto (vazamento do treino,
        que vende o produto de outra pessoa) ou esqueceu de anunciar.

    Pergunta pra IA em vez de procurar palavra: busca literal daria falso positivo em
    "livro antigo de registros" e nem funcionaria num canal em outro idioma.
    """
    nome = (canal or {}).get("produto_nome", "").strip()
    site = (canal or {}).get("produto_site", "").strip()
    try:
        d = claude_code.escrever("", CHECAGEM.format(roteiro=roteiro[:60000]),
                                 modelo=modelo, schema=CHECAGEM_SCHEMA)
    except Exception:
        return ""      # a checagem e' um extra: se falhar, nao atrapalha a geracao

    anuncia = bool(d.get("anuncia"))
    n_dito, s_dito = (d.get("nome_citado") or ""), (d.get("site_citado") or "")
    trecho = (d.get("trecho") or "").strip()
    cauda = f' Trecho: "{trecho[:200]}"' if trecho else ""

    if not (nome and site):
        if anuncia:
            return ("Esse roteiro anuncia um produto, mas o canal não tem produto "
                    "cadastrado." + cauda)
        return ""

    # o canal TEM produto
    if not anuncia:
        return (f'O canal vende "{nome}", mas o roteiro não anunciou em lugar nenhum.')
    if not (_combina(n_dito, nome) or _combina(s_dito, site)):
        return (f'O roteiro anunciou "{n_dito or s_dito}" em vez de "{nome}" '
                f'({site}) — provavelmente copiou o produto dos roteiros de treino.'
                + cauda)
    return ""


PERSONAGEM = """═══ QUEM NARRA ESTE CANAL ═══

Estes são os dados do narrador. Ele é o MESMO em todos os vídeos do canal:

{ficha}

Isso é intocável: sai exatamente como está aí, sem trocar e sem acrescentar. Se a ficha
traz família e história, é ESSA a família e ESSA a história — é a mesma que está no
produto do canal, e quem compra vai ler. O que a ficha não diz — jeito de falar,
detalhes do dia a dia — você constrói livre, seguindo o molde dos roteiros de treino,
sem nunca contradizer a ficha.

A FICHA É CONSULTA, NÃO TEXTO PRA RECITAR. Use um detalhe dela só onde os roteiros de
treino usariam um detalhe parecido: na apresentação, numa lembrança da família, numa
história que o assunto do vídeo pede. Num vídeo entram poucos detalhes — os que servem
àquele assunto —, nunca a ficha inteira. Mas quando um detalhe de família ou de história
aparecer, ele tem que ser o da ficha.

⚠ Uma proibição só: não pegue emprestada a vida do narrador dos roteiros de treino.
O nome, a cidade, a esposa, o pai e a mãe que aparecem lá são de OUTRA pessoa. Se você
precisar de um detalhe que a ficha não dá, invente um coerente com ela — nunca copie o
dele nem faça a versão traduzida do dele. A ÚNICA exceção é o que está escrito na ficha:
o que a ficha diz vale, mesmo que se pareça com a vida do narrador de treino.

Monte o bloco de identidade no ponto do roteiro em que os roteiros de treino fazem a
apresentação, e escreva do mesmo jeito que eles escrevem.
"""


def bloco_personagem(canal):
    ficha = (canal or {}).get("personagem", "").strip()
    # linhas do modelo que ficaram sem resposta ("Idade:") viram ruido no prompt
    linhas = [l for l in ficha.splitlines()
              if l.strip().rstrip(":") and not l.strip().endswith(":")
              and "(um fato por linha)" not in l]
    # cabecalho de familia sem nenhum fato embaixo e' o modelo colado sem preencher
    if linhas and linhas[-1].strip().startswith("Família e história"):
        linhas.pop()
    ficha = chr(10).join(linhas)
    return PERSONAGEM.format(ficha=ficha) if ficha else ""


ENXUGAR = """Este roteiro passou do tamanho permitido. Reescreva ele INTEIRO, mais curto.

TAMANHO ATUAL: {atual} caracteres
LIMITE:        {maximo} caracteres
TEM QUE SAIR:  {sobra} caracteres — cerca de {pct}% do texto

Escreva em {idioma}. Isto NÃO é um resumo: é o mesmo roteiro, mais enxuto.

MANTENHA, sem exceção:
- o gancho da abertura, inteiro, com a promessa que ele faz
- TODOS os itens/tópicos, na mesma ordem, nenhum a menos
- o ponto-chave de cada item: a informação que a pessoa veio buscar
- a virada do meio
- o fechamento, com a resolução do gancho lá do começo
- o anúncio do produto e as chamadas de inscrição/comentário, se houver
- a voz do narrador: mesmas expressões, mesmo ritmo de frase

CORTE daqui, nesta ordem:
1. exemplos além do primeiro de cada ponto
2. histórias de apoio que só reforçam algo já dito
3. adjetivos, descrições de cenário, frases que reafirmam o parágrafo anterior
4. rodeios antes de chegar ao ponto de cada item

Item com pouco espaço vira o ponto-chave dito de forma direta, sem a história em
volta. Nunca um item pela metade, nunca um item removido.

Devolva SÓ o roteiro final. Sem comentários, sem contagem, sem explicação.

--- ROTEIRO A ENCURTAR ---
{texto}"""


def enxugar(modelo, texto, maximo, idioma, on_delta=None, tentativas=2):
    """Pedir educadamente não bastou: o modelo estoura o limite com frequência.
    Aqui a gente MEDE e manda cortar, dizendo quantos caracteres precisam sair.
    Cada passada custa uma geração a mais — só roda quando realmente passou."""
    for _ in range(tentativas):
        if len(texto) <= maximo:
            break
        sobra = len(texto) - maximo
        novo = claude_code.escrever("", ENXUGAR.format(
            atual=len(texto), maximo=maximo, sobra=sobra,
            pct=round(100 * sobra / len(texto)), idioma=idioma, texto=texto),
            modelo=modelo, on_delta=on_delta)
        # se a "correção" veio maior ou absurdamente curta, descarta e fica com o que tinha
        if not novo or len(novo) >= len(texto) or len(novo) < maximo * 0.5:
            break
        texto = novo
    return texto


def gerar_roteiro(modelo, titulo, dur_min, idioma, roteiros, alvo_chars,
                  on_delta=None, canal=None):
    """Gera o roteiro em streaming. on_delta(texto_parcial_acumulado) e' chamado a cada
    pedaco. Devolve o texto final."""
    usados = montar_treino(roteiros)
    partes = []
    for i, r in enumerate(usados, 1):
        cabeca = f"### ROTEIRO DE TREINO {i}"
        if r.get("titulo"):
            cabeca += f" — {r['titulo']}"
        partes.append(f"{cabeca}\n\n{r['texto']}")
    corpo = "\n\n".join(partes)

    system = SYSTEM.format(n=len(usados), idioma=idioma, alvo=alvo_chars,
                           minimo=int(alvo_chars * 0.85),
                           maximo=int(alvo_chars * 1.10),
                           cpm=round(alvo_chars / max(1, dur_min)), dur=dur_min,
                           corpo=corpo,
                           produto=bloco_produto(canal, round(alvo_chars / max(1, dur_min))),
                           personagem=bloco_personagem(canal))
    user = USER.format(titulo=titulo, dur=dur_min, alvo=alvo_chars, idioma=idioma)

    # o Claude Code manda o texto em pedacos: o front mostra o roteiro nascendo
    texto = claude_code.escrever(system, user, modelo=modelo, on_delta=on_delta)

    # o limite no prompt é só um pedido, e o modelo estoura direto. Aqui a gente confere
    # e, se passou, manda cortar de verdade.
    maximo = int(alvo_chars * 1.10)
    if len(texto) > maximo:
        if on_delta:
            on_delta(texto)
        texto = enxugar(modelo, texto, maximo, idioma, on_delta=on_delta)
    return texto
