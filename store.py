# -*- coding: utf-8 -*-
"""Persistencia do YOUTUBE FARM: presets, canais e videos num unico db.json.

Simples de proposito: um lock, um arquivo, escrita atomica. Nada de banco.
"""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from caminhos import dir_dados

DATA = dir_dados() / "data"
PRESETS_DIR = DATA / "presets"
DB = DATA / "db.json"
CONFIG = DATA / "config.json"

VAZIO = {"presets": [], "canais": [], "videos": []}

# Produto do canal (ebook, curso...). TUDO opcional: canal sem produto gera roteiro
# normal, sem anuncio e sem card. As cores sao as do card de referencia.
PRODUTO_VAZIO = {
    "produto_nome": "",
    "produto_desc": "",
    "produto_site": "",
    "produto_capa": "",        # arquivo em data/capas/
    "cor_fundo": "#7A3320",
    "cor_destaque": "#E3A63C",
}

# So' os tres dados que a IA inventava diferente a cada video. Sao exatamente os que dao
# pra tirar de uma FOTO do personagem, que e' como a ficha e' preenchida: o usuario copia
# o modelo, anexa o avatar no Claude e cola a resposta de volta aqui.
# Profissao NAO entra: nao da' pra deduzir de uma foto, e vem do molde sozinha — nos 3
# roteiros do canal de referencia o bloco de profissao e' identico palavra por palavra.
MODELO_PERSONAGEM = """Nome:
Idade:
Onde ele mora / a região:"""

CONFIG_PADRAO = {
    "anthropic_key": "",
    "darkplanner_key": "",
    "modelo": "claude-opus-5",
    # medido de verdade: um roteiro de 19.189 chars virou 1418s de narração = 812 chars/min.
    # O chute inicial era 1100 e entregava 23min pra um pedido de 16.
    "chars_por_minuto": 810,
    "port": 8777,
}


def _agora():
    return time.time()


def _id():
    return uuid.uuid4().hex[:8]


def slug(texto):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (texto or "").strip().lower()).strip("-")
    return s or "sem-nome"


class Store:
    def __init__(self):
        self._lock = threading.RLock()
        DATA.mkdir(parents=True, exist_ok=True)
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        self.db = self._ler(DB, VAZIO)
        for k, v in VAZIO.items():
            self.db.setdefault(k, list(v))
        self.cfg = self._ler(CONFIG, CONFIG_PADRAO)
        for k, v in CONFIG_PADRAO.items():
            self.cfg.setdefault(k, v)
        self._gravar(CONFIG, self.cfg)

    # ---------- io ----------
    def _ler(self, path, padrao):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return json.loads(json.dumps(padrao))

    def _gravar(self, path, obj):
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def salvar(self):
        with self._lock:
            self._gravar(DB, self.db)

    def salvar_cfg(self):
        with self._lock:
            self._gravar(CONFIG, self.cfg)

    # ---------- config ----------
    def get_cfg(self):
        with self._lock:
            return dict(self.cfg)

    def set_cfg(self, patch):
        with self._lock:
            for k, v in (patch or {}).items():
                if k in CONFIG_PADRAO:
                    self.cfg[k] = v
            self.salvar_cfg()
            return dict(self.cfg)

    # ---------- presets ----------
    def presets(self):
        with self._lock:
            return list(self.db["presets"])

    def preset(self, pid):
        with self._lock:
            return next((p for p in self.db["presets"] if p["id"] == pid), None)

    def add_preset(self, nome, roteiros, arquivo_origem=""):
        """roteiros = lista de {titulo, texto} ja normalizada pelo roteirista."""
        with self._lock:
            pid = _id()
            nome_arq = f"{slug(nome)}-{pid}.json"
            self._gravar(PRESETS_DIR / nome_arq, {"nome": nome, "roteiros": roteiros})
            p = {
                "id": pid,
                "nome": nome.strip(),
                "arquivo": nome_arq,
                "origem": arquivo_origem,
                "n_roteiros": len(roteiros),
                "n_chars": sum(len(r["texto"]) for r in roteiros),
                "criado_em": _agora(),
            }
            self.db["presets"].append(p)
            self.salvar()
            return p

    def roteiros_do_preset(self, pid):
        p = self.preset(pid)
        if not p:
            return []
        try:
            d = json.loads((PRESETS_DIR / p["arquivo"]).read_text(encoding="utf-8"))
            return d.get("roteiros", [])
        except Exception:
            return []

    def del_preset(self, pid):
        with self._lock:
            p = self.preset(pid)
            if not p:
                return False
            if any(c.get("preset_id") == pid for c in self.db["canais"]):
                return "em-uso"
            try:
                (PRESETS_DIR / p["arquivo"]).unlink()
            except Exception:
                pass
            self.db["presets"] = [x for x in self.db["presets"] if x["id"] != pid]
            self.salvar()
            return True

    # ---------- canais ----------
    def canais(self):
        with self._lock:
            out = []
            for c in self.db["canais"]:
                c = dict(c)
                p = self.preset(c.get("preset_id"))
                c["preset_nome"] = p["nome"] if p else "(modelo removido)"
                c["n_videos"] = sum(1 for v in self.db["videos"] if v["canal_id"] == c["id"])
                out.append(c)
            return out

    def canal(self, cid):
        with self._lock:
            c = next((x for x in self.db["canais"] if x["id"] == cid), None)
            if not c:
                return None
            c = dict(c)
            p = self.preset(c.get("preset_id"))
            c["preset_nome"] = p["nome"] if p else "(modelo removido)"
            return c

    def add_canal(self, nome, idioma, preset_id):
        with self._lock:
            c = {
                "id": _id(),
                "nome": nome.strip(),
                "idioma": idioma.strip(),
                "preset_id": preset_id,
                "voz_id": "",          # escolhida depois, na tela do canal
                "voz_nome": "",
                "personagem": "",      # quem narra: preenchido pelo MODELO_PERSONAGEM
                **PRODUTO_VAZIO,
                "criado_em": _agora(),
            }
            self.db["canais"].append(c)
            self.salvar()
            return c

    def editar_canal(self, cid, campos):
        """So mexe nos campos editaveis — nunca no id, preset ou data."""
        editaveis = {"nome", "idioma", "voz_id", "voz_nome", "personagem", *PRODUTO_VAZIO}
        with self._lock:
            c = next((x for x in self.db["canais"] if x["id"] == cid), None)
            if not c:
                return None
            for k, v in (campos or {}).items():
                if k in editaveis:
                    c[k] = v.strip() if isinstance(v, str) else v
            self.salvar()
            return dict(c)

    def tem_produto(self, canal):
        """O anuncio so' entra se tiver nome E site — sem os dois nao ha' o que anunciar."""
        return bool((canal or {}).get("produto_nome") and (canal or {}).get("produto_site"))

    def set_voz(self, cid, voz_id, voz_nome):
        with self._lock:
            c = next((x for x in self.db["canais"] if x["id"] == cid), None)
            if not c:
                return None
            c["voz_id"] = voz_id
            c["voz_nome"] = voz_nome
            self.salvar()
            return dict(c)

    def del_canal(self, cid):
        with self._lock:
            self.db["canais"] = [x for x in self.db["canais"] if x["id"] != cid]
            self.db["videos"] = [v for v in self.db["videos"] if v["canal_id"] != cid]
            self.salvar()
            return True

    # ---------- videos ----------
    def videos(self, cid=None):
        with self._lock:
            vs = [v for v in self.db["videos"] if cid is None or v["canal_id"] == cid]
            return sorted(vs, key=lambda v: v["criado_em"], reverse=True)

    def video(self, vid):
        with self._lock:
            v = next((x for x in self.db["videos"] if x["id"] == vid), None)
            return dict(v) if v else None

    def add_video(self, canal_id, titulo, dur):
        with self._lock:
            v = {
                "id": _id(),
                "canal_id": canal_id,
                "titulo": titulo.strip(),
                "dur": int(dur),
                "estado": "fila",       # fila | gerando | pronto | erro  (roteiro)
                "roteiro": "",
                "erro": "",
                "n_chars": 0,
                "alvo_chars": 0,
                # etapa 2: narracao. A API traz o audio e o SRT de blocos juntos.
                "audio_estado": "nao",  # nao | gerando | pronto | erro
                "audio_msg": "",
                "audio_erro": "",
                "audio_path": "",
                "srt_path": "",
                "pasta": "",
                # aviso da checagem de produto (roteiro vendeu algo que o canal nao tem)
                "aviso": "",
                # etapa 3: direcao
                "direcao_estado": "nao",   # nao | gerando | pronto | erro
                "direcao_msg": "",
                "direcao_erro": "",
                "direcao_resumo": {},
                # etapa 4/5: os arquivos que vem de fora (HeyGen e DarkPlanner)
                "avatar_path": "",
                "pasta_dark": "",
                "broll_resumo": {},
                # etapa 6: a montagem final
                "montagem_estado": "nao",   # nao | montando | pronto | erro
                "montagem_msg": "",
                "montagem_erro": "",
                "montagem_saida": "",
                "montagem_faltaram": 0,   # blocos sem imagem que o avatar cobriu
                "criado_em": _agora(),
            }
            self.db["videos"].append(v)
            self.salvar()
            return v

    def up_video(self, vid, **campos):
        """Atualiza um video. So grava no disco quando o estado muda ou termina —
        durante o streaming o texto vive em memoria (senao seria 1 write por chunk)."""
        with self._lock:
            v = next((x for x in self.db["videos"] if x["id"] == vid), None)
            if not v:
                return None
            v.update(campos)
            if (campos.get("estado") in ("pronto", "erro", "gerando")
                    or campos.get("audio_estado") in ("pronto", "erro", "gerando")
                    or campos.get("direcao_estado") in ("pronto", "erro", "gerando")
                    or campos.get("montagem_estado") in ("pronto", "erro", "montando")
                    or "avatar_path" in campos or "pasta_dark" in campos):
                self.salvar()
            return dict(v)

    def del_video(self, vid):
        with self._lock:
            self.db["videos"] = [v for v in self.db["videos"] if v["id"] != vid]
            self.salvar()
            return True
