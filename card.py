# -*- coding: utf-8 -*-
"""O card do produto: fundo colorido, capa do ebook e o texto.

Sai em TRES camadas PNG, nao numa imagem so'. E' o que permite animar depois no ffmpeg:
a capa entra caindo de cima enquanto o texto aparece em fade, um pouco atrasado.

  fundo.png   opaco, a cor do canal em degrade
  capa.png    so' a capa, transparente no resto
  texto.png   so' o texto, transparente no resto
"""
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
}
IDIOMA = {"português": "pt", "portugues": "pt", "english": "en", "deutsch": "de",
          "español": "es", "espanol": "es", "français": "fr", "francais": "fr",
          "italiano": "it", "nederlands": "nl", "polski": "pl"}


def kicker_do_idioma(idioma):
    return KICKER.get(IDIOMA.get((idioma or "").strip().lower(), "en"), KICKER["en"])


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
    texto = _camada_texto(
        kicker_do_idioma(canal.get("idioma")),
        nome,
        (canal.get("produto_desc") or "").strip(),
        site,
        _rgb(canal.get("cor_destaque"), (227, 166, 60)),
        tem_capa,
    )
    saidas = {}
    for chave, img in (("fundo", fundo), ("capa", capa), ("texto", texto)):
        p = pasta / f"card_{chave}.png"
        (img.convert("RGB") if chave == "fundo" else img).save(p)
        saidas[chave] = str(p)
    saidas["tem_capa"] = tem_capa
    return saidas
