# -*- coding: utf-8 -*-
"""O card do produto: fundo colorido, capa do ebook e o texto.

Sai em TRES camadas PNG, nao numa imagem so'. E' o que permite animar depois no ffmpeg:
a capa entra caindo de cima enquanto o texto aparece em fade, um pouco atrasado.

  fundo.png   opaco, a cor do canal em degrade
  capa.png    so' a capa, transparente no resto
  texto.png   so' o texto, transparente no resto
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

L, A = 1920, 1080          # o card ocupa a tela inteira

# medidas tiradas do card de referencia, em fracao da tela
CAPA_X, CAPA_Y = 0.130, 0.189
CAPA_L, CAPA_A = 0.242, 0.632
TXT_X = 0.427
TXT_TOPO = 0.270

# Listas de tentativa: a 1a que existir na maquina vence. O app vai rodar no PC dos
# outros, e nao da' pra empacotar Georgia/Segoe junto (sao fontes licenciadas da
# Microsoft) — entao a saida e' ter alternativa.
F = "C:/Windows/Fonts/"
SERIF = [F + "georgiab.ttf", F + "timesbd.ttf", F + "constanb.ttf", F + "arialbd.ttf"]
SANS = [F + "segoeui.ttf", F + "calibri.ttf", F + "arial.ttf", F + "tahoma.ttf"]
SANS_BOLD = [F + "segoeuib.ttf", F + "calibrib.ttf", F + "arialbd.ttf", F + "tahomabd.ttf"]
SANS_SEMI = [F + "seguisb.ttf", F + "segoeuib.ttf", F + "calibrib.ttf", F + "arialbd.ttf"]

# "o livro de onde ele lê" — segue o idioma do canal
KICKER = {
    "en": "THE BOOK HE READS FROM",
    "pt": "O LIVRO DE ONDE ELE TIRA ISSO",
    "de": "DAS BUCH, AUS DEM ER LIEST",
    "es": "EL LIBRO DEL QUE LEE",
    "fr": "LE LIVRE DONT IL PARLE",
    "it": "IL LIBRO DA CUI LEGGE",
    "nl": "HET BOEK WAARUIT HIJ LEEST",
    "pl": "KSIĄŻKA, Z KTÓREJ CZYTA",
    "sv": "BOKEN HAN LÄSER UR",
    "da": "BOGEN HAN LÆSER FRA",
    "no": "BOKEN HAN LESER FRA",
    "fi": "KIRJA, JOSTA HÄN LUKEE",
}
# Este mapa e' irmao do ISO do server.py e vive separado so' porque o card nao importa o
# servidor. Os dois precisam cobrir os MESMOS idiomas: faltava aqui sueco, dinamarques e
# noruegues, e um canal nesses idiomas ganhava o texto em INGLES no card, calado.
# A linha embaixo do QR. Traduzida igual ao KICKER — e, igual a ele, estas sao
# traducoes minhas: vale conferir com alguem que fale, porque isso sai queimado no video.
ESCANEIE = {
    "en": "SCAN WITH YOUR PHONE",
    "pt": "APONTE A CÂMERA DO CELULAR",
    "de": "MIT DEM HANDY SCANNEN",
    "es": "ESCANEA CON EL MÓVIL",
    "fr": "SCANNEZ AVEC VOTRE TÉLÉPHONE",
    "it": "INQUADRA CON IL TELEFONO",
    "nl": "SCAN MET JE TELEFOON",
    "pl": "ZESKANUJ TELEFONEM",
    "sv": "SKANNA MED MOBILEN",
    "da": "SCAN MED TELEFONEN",
    "no": "SKANN MED MOBILEN",
    "fi": "SKANNAA PUHELIMELLA",
}

IDIOMA = {"português": "pt", "portugues": "pt", "inglês": "en", "ingles": "en",
          "alemão": "de", "alemao": "de", "espanhol": "es", "francês": "fr",
          "frances": "fr", "italiano": "it", "holandês": "nl", "holandes": "nl",
          "polonês": "pl", "polones": "pl", "sueco": "sv", "dinamarquês": "da",
          "dinamarques": "da", "norueguês": "no", "noruegues": "no",
          "finlandês": "fi", "finlandes": "fi",
          # nomes antigos, pros canais criados antes desta lista
          "english": "en", "deutsch": "de", "español": "es", "espanol": "es",
          "français": "fr", "francais": "fr", "nederlands": "nl", "polski": "pl",
          "svenska": "sv", "dansk": "da", "norsk": "no", "suomi": "fi"}


# "by Otis Granger". O nome sai da FICHA do narrador — em todo canal ele e' a mesma
# pessoa que assina o produto, entao nao faz sentido digitar isso de novo no cadastro.
# Polones e finlandes ficam SEM preposicao de proposito: la' a autoria se escreve so'
# com o nome (o finlandes usaria caso genitivo, e um "by" solto soa traduzido).
ASSINATURA = {"en": "by", "pt": "por", "de": "von", "es": "por", "fr": "par",
              "it": "di", "nl": "door", "sv": "av", "da": "af", "no": "av",
              "pl": "", "fi": ""}


def _nome_da_ficha(personagem):
    """O 'Nome:' da ficha. A ficha e' texto livre, entao le' linha a linha."""
    for linha in (personagem or "").splitlines():
        if linha.strip().lower().startswith("nome:"):
            return linha.split(":", 1)[1].strip()
    return ""


def assinatura(canal):
    """A linha de autoria do cartao. Vazia se a ficha nao tiver nome preenchido."""
    nome = _nome_da_ficha((canal or {}).get("personagem"))
    if not nome:
        return ""
    iso = IDIOMA.get(((canal or {}).get("idioma") or "").strip().lower(), "en")
    return f"{ASSINATURA.get(iso, 'by')} {nome}".strip()


def kicker_do_idioma(idioma):
    return KICKER.get(IDIOMA.get((idioma or "").strip().lower(), "en"), KICKER["en"])


def escaneie_do_idioma(idioma):
    return ESCANEIE.get(IDIOMA.get((idioma or "").strip().lower(), "en"), ESCANEIE["en"])


def _rgb(h, padrao=(122, 51, 32)):
    h = (h or "").strip().lstrip("#")
    if len(h) != 6:
        return padrao
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return padrao


def _fonte(candidatas, tam):
    for c in (candidatas if isinstance(candidatas, (list, tuple)) else [candidatas]):
        try:
            return ImageFont.truetype(c, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _largura(d, txt, f):
    return d.textbbox((0, 0), txt, font=f)[2]


def _quebrar(d, txt, f, limite):
    linhas, atual = [], ""
    for p in txt.split():
        teste = f"{atual} {p}".strip()
        if _largura(d, teste, f) <= limite or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _cabe(d, txt, tam_ini, caminho, limite, max_linhas):
    """Diminui a fonte ate o texto caber nas linhas permitidas — titulo comprido
    nao pode estourar pra fora da tela."""
    tam = tam_ini
    while tam > 20:
        f = _fonte(caminho, tam)
        linhas = _quebrar(d, txt, f, limite)
        if len(linhas) <= max_linhas:
            return f, linhas
        tam -= 4
    return _fonte(caminho, tam), _quebrar(d, _fonte(caminho, tam) and txt, _fonte(caminho, tam), limite)


def _fundo(cor):
    """Degrade radial: mais claro no meio-esquerda, escurecendo pras bordas."""
    r, g, b = cor
    peq = Image.new("RGB", (96, 54))
    px = peq.load()
    cx, cy = 0.42 * 96, 0.45 * 54
    maxd = (96 ** 2 + 54 ** 2) ** 0.5
    for y in range(54):
        for x in range(96):
            dist = (((x - cx) ** 2 + (y - cy) ** 2) ** 0.5) / maxd
            k = 1.18 - 0.85 * dist          # 1.18 no centro -> ~0.5 nos cantos
            px[x, y] = (min(255, int(r * k)), min(255, int(g * k)), min(255, int(b * k)))
    return peq.resize((L, A), Image.LANCZOS).convert("RGBA")


def _camada_capa(caminho_capa):
    camada = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    if not caminho_capa or not Path(caminho_capa).exists():
        return camada, False
    try:
        capa = Image.open(caminho_capa).convert("RGBA")
    except Exception:
        return camada, False
    cx, cy = int(CAPA_X * L), int(CAPA_Y * A)
    cl, ca = int(CAPA_L * L), int(CAPA_A * A)
    capa.thumbnail((cl, ca), Image.LANCZOS)
    x = cx + (cl - capa.width) // 2
    y = cy + (ca - capa.height) // 2
    # sombra pra capa descolar do fundo
    sombra = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rectangle([x + 10, y + 18, x + capa.width + 10, y + capa.height + 18],
                                     fill=(0, 0, 0, 130))
    camada = Image.alpha_composite(camada, sombra.filter(ImageFilter.GaussianBlur(22)))
    camada.paste(capa, (x, y), capa)
    return camada, True


# O canto de baixo a direita estava vazio. O QR mora ali: longe do texto, longe da capa,
# e grande o bastante pra ler de longe numa TV.
QR_LADO = 232                      # o desenho do QR, em pixels
# Com margem 150 o QR encostava na ultima palavra da descricao. Agora ele vai pro canto
# de verdade: a margem de baixo conta o BLOCO INTEIRO (QR + espaco + legenda), senao a
# legenda e' que ficava colada na borda.
QR_MARGEM_D, QR_MARGEM_B = 80, 76
QR_VAO, QR_LEGENDA = 26, 24        # espaco ate' a legenda e altura dela


def _camada_qr(site, destaque):
    """O QR do site, com a legenda embaixo. Devolve None se nao der pra gerar.

    Fundo claro e modulos escuros, nao o contrario: leitor de celular espera essa
    polaridade, e invertido muita camera simplesmente nao engata.
    """
    try:
        import segno
    except ImportError:
        return None                # sem a biblioteca o card sai sem QR, e nao quebra
    endereco = site if "://" in site else "https://" + site
    try:
        # error='m' aguenta ~15% do codigo sujo — serve pra tela, onde a compressao
        # do video come os cantos dos modulos.
        qr = segno.make(endereco, error="m")
    except Exception:
        return None
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=2, dark="#201A16", light="#F2EDE7")
    buf.seek(0)
    desenho = Image.open(buf).convert("RGBA").resize((QR_LADO, QR_LADO), Image.NEAREST)
    return desenho


def _colar_qr(camada, site, destaque, idioma):
    """Cola o QR e a legenda no canto de baixo a direita da camada de texto."""
    desenho = _camada_qr(site, destaque)
    if desenho is None:
        return
    x = L - QR_MARGEM_D - QR_LADO
    y = A - QR_MARGEM_B - QR_LEGENDA - QR_VAO - QR_LADO
    # uma moldura clara atras, pra o QR nao encostar no fundo escuro e perder contraste
    d = ImageDraw.Draw(camada)
    d.rounded_rectangle([x - 14, y - 14, x + QR_LADO + 14, y + QR_LADO + 14],
                        radius=10, fill=(242, 237, 231, 255))
    camada.paste(desenho, (x, y), desenho)
    f = _fonte(SANS_SEMI, 22)
    texto = escaneie_do_idioma(idioma)
    larg = d.textlength(texto, font=f)
    d.text((x + (QR_LADO - larg) / 2, y + QR_LADO + QR_VAO), texto, font=f,
           fill=destaque + (255,))


def _camada_seta(destaque):
    """A setinha que aponta pro QR. Camada propria porque o montador a anima sozinha.

    Fica a' ESQUERDA do QR apontando pra direita: ali e' espaco vazio do cartao, entao
    ela nao briga com a descricao nem com o endereco.
    """
    camada = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    qx = L - QR_MARGEM_D - QR_LADO
    qy = A - QR_MARGEM_B - QR_LEGENDA - QR_VAO - QR_LADO
    cy = qy + QR_LADO // 2                   # na altura do meio do QR
    # 34px deixava a ponta a 4px da moldura do QR no pico do balanco (que vai ate'
    # +16px) — de longe parecia que a seta encostava. 56px mantem 22px de folga.
    ponta = qx - 56                          # onde a ponta para
    corpo, alt = 54, 30                      # comprimento da haste e meia-altura
    d.polygon([(ponta, cy), (ponta - alt, cy - alt), (ponta - alt, cy + alt)],
              fill=destaque + (255,))
    d.rounded_rectangle([ponta - alt - corpo, cy - 7, ponta - alt + 6, cy + 7],
                        radius=7, fill=destaque + (255,))
    return camada


def _camada_texto(kicker, titulo, descricao, site, destaque, tem_capa):
    camada = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    x = int(TXT_X * L) if tem_capa else int(0.10 * L)
    limite = L - x - int(0.08 * L)
    y = int(TXT_TOPO * A)

    if kicker:
        f = _fonte(SANS_SEMI, 27)
        d.text((x, y), kicker.upper(), font=f, fill=destaque + (255,),
               spacing=4, features=None)
        y += 62

    f_tit, linhas = _cabe(d, (titulo or "").upper(), 86, SERIF, limite, 3)
    alt = f_tit.size + 16
    for ln in linhas:
        d.text((x, y), ln, font=f_tit, fill=(255, 255, 255, 255))
        y += alt
    y += 30

    d.rectangle([x, y, x + 96, y + 3], fill=destaque + (255,))
    y += 44

    if descricao:
        f_d = _fonte(SANS, 34)
        for ln in _quebrar(d, descricao, f_d, limite)[:3]:
            d.text((x, y), ln, font=f_d, fill=(232, 226, 222, 245))
            y += 48
    y += 26

    if site:
        d.text((x, y), site, font=_fonte(SANS_BOLD, 42), fill=destaque + (255,))
    return camada


def montar(pasta, canal, tamanho=(L, A)):
    """Gera as três camadas em `pasta`. Devolve os caminhos, ou None se não há produto."""
    nome = (canal or {}).get("produto_nome", "").strip()
    site = (canal or {}).get("produto_site", "").strip()
    if not (nome and site):
        return None
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    fundo = _fundo(_rgb(canal.get("cor_fundo"), (122, 51, 32)))
    capa, tem_capa = _camada_capa(canal.get("_capa_path"))
    destaque = _rgb(canal.get("cor_destaque"), (227, 166, 60))
    texto = _camada_texto(
        kicker_do_idioma(canal.get("idioma")),
        nome,
        # o campo manual manda; vazio, entra a assinatura automatica
        (canal.get("produto_desc") or "").strip() or assinatura(canal),
        site,
        destaque,
        tem_capa,
    )
    # o QR entra na mesma camada do texto: assim ele aparece junto, no mesmo fade
    _colar_qr(texto, site, destaque, canal.get("idioma"))
    # a seta e' camada SEPARADA porque o montador a balanca; o resto fica parado
    seta = _camada_seta(destaque)
    saidas = {}
    for chave, img in (("fundo", fundo), ("capa", capa), ("texto", texto),
                       ("seta", seta)):
        p = pasta / f"card_{chave}.png"
        (img.convert("RGB") if chave == "fundo" else img).save(p)
        saidas[chave] = str(p)
    saidas["tem_capa"] = tem_capa
    return saidas
