# -*- coding: utf-8 -*-
"""Roteirista: le o .json de treinamento do modelo e escreve o roteiro novo com o Claude.

O .json de treinamento e' permissivo de proposito — voce cola o que tiver. Aceita:
  ["roteiro um...", "roteiro dois..."]
  [{"titulo": "...", "roteiro": "..."}, ...]        (ou narracao/script/texto/conteudo/...)
  {"roteiros": [...]}  {"scripts": [...]}  {"data": [...]}  {"items": [...]}
  {"video1": {...}, "video2": {...}}
"""
# O anthropic sozinho leva 4,0s pra importar — 73% da abertura do app, medido.
# Como ele so' serve pra chamar a API, o import mora dentro das funcoes: a janela
# abre na hora e a espera vai pro primeiro uso, onde 4s nao fazem falta perto dos
# minutos que a geracao leva.
import json
import re


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


def parse_blocos(texto):
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
            if len(corpo) >= MIN_CHARS:
                roteiros.append({"titulo": titulo, "texto": corpo})
            dentro = False
            continue
        if dentro:
            atual.append(linha)
    if dentro:
        raise ValueError("tem um bloco aberto com { que nunca fechou com }.")
    return roteiros


def parse_conteudo(texto):
    """Descobre sozinho o formato do arquivo: JSON ou blocos entre chaves."""
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("o arquivo está vazio.")
    try:
        return parse_treinamento(json.loads(texto))
    except json.JSONDecodeError:
        pass          # nao e' JSON — tenta o formato de blocos
    roteiros = parse_blocos(texto)
    if not roteiros:
        raise ValueError(
            "não entendi o arquivo. Use JSON, ou ponha cada roteiro entre chaves "
            "sozinhas na linha:\n{\nroteiro um\n}\n{\nroteiro dois\n}\n"
            f"(cada roteiro precisa de pelo menos {MIN_CHARS} caracteres)")
    return roteiros


def parse_treinamento(dados):
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
        if len(texto) >= MIN_CHARS:
            roteiros.append({"titulo": titulo, "texto": texto})

    if not roteiros:
        raise ValueError(f"nenhum roteiro encontrado (precisa de pelo menos {MIN_CHARS} "
                         "caracteres de texto por item).")
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
{desc}
⚠ ATENÇÃO AO NOME. Os roteiros de treinamento vendem o produto de OUTRA pessoa, com
outro nome e outro site. Aquilo é exemplo de FORMATO, não de conteúdo. É proibido
escrever o nome ou o endereço que aparecem nos roteiros de treino. O único nome que
pode sair no seu texto é "{nome}" e o único endereço é "{site}".

COMO ANUNCIAR — uma vez só, entre 10% e 20% do roteiro:

O anúncio não é um intervalo comercial. É uma história curta que explica POR QUE o
produto existe, e essa explicação é o que prova a autoridade do narrador. Observe como
os roteiros de treino fazem e reproduza o mecanismo:

1. Um motivo humano pra ter criado aquilo — alguém pediu, o conhecimento ia se perder,
   cansou de repetir a mesma resposta. Nunca "eu criei um produto incrível".
2. Uma piada com ele mesmo ou uma farpa carinhosa em alguém. Tira o cheiro de venda.
3. O nome do produto, dito com naturalidade, e onde achar: "{site}".
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


def bloco_produto(canal):
    """Escolhe qual das duas instruções entra no prompt."""
    nome = (canal or {}).get("produto_nome", "").strip()
    site = (canal or {}).get("produto_site", "").strip()
    if not (nome and site):
        return SEM_PRODUTO
    desc = (canal or {}).get("produto_desc", "").strip()
    return COM_PRODUTO.format(nome=nome, site=site,
                              desc=f"Do que se trata: {desc}\n" if desc else "")


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


def checar_produto(api_key, modelo, roteiro, canal):
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
        import anthropic
        cliente = anthropic.Anthropic(api_key=api_key)
        r = cliente.messages.create(
            model=modelo,
            max_tokens=2000,
            output_config={"format": {"type": "json_schema", "schema": CHECAGEM_SCHEMA}},
            messages=[{"role": "user", "content": CHECAGEM.format(roteiro=roteiro[:60000])}],
        )
        d = json.loads("".join(c.text for c in r.content if c.type == "text"))
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

Isso é intocável: sai exatamente como está aí, sem trocar e sem acrescentar. O RESTO
— profissão, origem, família, jeito de falar — você constrói livre, seguindo o molde
dos roteiros de treino.

⚠ Uma proibição só: não pegue emprestada a vida do narrador dos roteiros de treino.
O nome, a cidade, a esposa, o pai e a mãe que aparecem lá são de OUTRA pessoa. Se você
precisar de um detalhe desses, invente um coerente com a ficha acima — nunca copie o
dele nem faça a versão traduzida do dele.

Monte o bloco de identidade no ponto do roteiro em que os roteiros de treino fazem a
apresentação, e escreva do mesmo jeito que eles escrevem.
"""


def bloco_personagem(canal):
    ficha = (canal or {}).get("personagem", "").strip()
    # linhas do modelo que ficaram sem resposta ("Idade:") viram ruido no prompt
    linhas = [l for l in ficha.splitlines()
              if l.strip().rstrip(":") and not l.strip().endswith(":")]
    ficha = chr(10).join(linhas)
    return PERSONAGEM.format(ficha=ficha) if ficha else ""


def gerar_roteiro(api_key, modelo, titulo, dur_min, idioma, roteiros, alvo_chars,
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
                           corpo=corpo, produto=bloco_produto(canal),
                           personagem=bloco_personagem(canal))
    user = USER.format(titulo=titulo, dur=dur_min, alvo=alvo_chars, idioma=idioma)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    buf = []
    # streaming: max_tokens alto nao estoura timeout, e o front mostra o texto nascendo.
    # cache_control no system: o bloco de treino e' identico entre videos do mesmo canal,
    # entao do 2o video em diante o treino sai ~90% mais barato.
    with client.messages.stream(
        model=modelo,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                buf.append(event.delta.text)
                if on_delta:
                    on_delta("".join(buf))
        final = stream.get_final_message()

    if final.stop_reason == "refusal":
        motivo = getattr(getattr(final, "stop_details", None), "explanation", "") or ""
        raise RuntimeError("o modelo recusou esse pedido. " + motivo)

    texto = "".join(buf).strip()
    if not texto:
        raise RuntimeError("o modelo não devolveu texto (stop_reason=%s)." % final.stop_reason)

    # o limite no prompt é só um pedido, e o modelo estoura direto. Aqui a gente confere
    # e, se passou, manda cortar de verdade.
    maximo = int(alvo_chars * 1.10)
    if len(texto) > maximo:
        if on_delta:
            on_delta(texto)
        texto = enxugar(api_key, modelo, texto, maximo, idioma, on_delta=on_delta)
    return texto
