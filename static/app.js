/* YOUTUBE FARM — front */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const IDIOMAS = ["Português", "English", "Deutsch", "Español", "Français",
                 "Italiano", "Nederlands", "Polski", "Svenska", "Dansk", "Norsk"];

/* faixa fixa de duração — o app nunca escreve fora disso (o servidor também barra) */
const DURACOES = [16, 17, 18, 19, 20];

/* caracteres por minuto de narração — vem dos Ajustes, com o valor medido de padrão */
const CPM = () => Number(st.cfg?.chars_por_minuto) || 810;

/* como o card fica montado, pra pessoa ver antes de preencher os campos */
const EXEMPLO_CARD = "https://postimg.cc/NycMRpb1";

/* abre FORA da janela: um link comum trocaria a interface do app pela página */
function abrirLink(url) {
  if (window.pywebview?.api) window.pywebview.api.abrir_link(url);
  else window.open(url, "_blank");
}

const st = { canais: [], modelos: [], cfg: {}, canal: null, videos: [], video: null };
let timer = null;

/* ---------------- rede ---------------- */
async function api(url, opts = {}) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.ok === false) throw new Error(d.erro || `erro ${r.status}`);
  return d;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("aberto");
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove("aberto"), 2600);
}

/* ---------------- navegação ---------------- */
function irPara(nome) {
  $$(".view").forEach(v => v.classList.remove("ativo"));
  $("#view-" + nome)?.classList.add("ativo");
  const tab = { canais: "canais", canal: "canais", video: "canais", vozes: "canais",
                modelos: "modelos", ajustes: "ajustes" }[nome];
  $$(".tab").forEach(t => t.classList.toggle("ativo", t.dataset.tab === tab));
  $("#rolagem").scrollTop = 0;
  pararPolling();
}

$$(".tab").forEach(t => t.onclick = () => {
  const n = t.dataset.tab;
  if (n === "canais") verCanais();
  if (n === "modelos") verModelos();
  if (n === "ajustes") verAjustes();
});

document.addEventListener("click", e => {
  const g = e.target.closest("[data-go]");
  if (g) { if (g.dataset.go === "canais") verCanais(); return; }
  const a = e.target.closest("[data-act]");
  if (!a) return;
  ({
    "novo-canal": sheetNovoCanal,
    "novo-modelo": sheetNovoModelo,
    "novo-video": sheetNovoVideo,
    "apagar-canal": apagarCanal,
    "editar-canal": sheetEditarCanal,
    "salvar-cfg": salvarCfg,
  })[a.dataset.act]?.();
});

/* ---------------- menu do botão direito ---------------- */
function menuContexto(evento, itens) {
  evento.preventDefault();
  const m = $("#menu-ctx");
  m.innerHTML = itens.map((it, i) =>
    `<button data-i="${i}" class="${it.perigo ? "perigo" : ""}">${esc(it.texto)}</button>`).join("");
  m.classList.add("aberto");
  // não deixa vazar pra fora da janela
  m.style.left = Math.min(evento.clientX, innerWidth - m.offsetWidth - 8) + "px";
  m.style.top = Math.min(evento.clientY, innerHeight - m.offsetHeight - 8) + "px";
  m.onclick = e => {
    const b = e.target.closest("button");
    if (b) itens[+b.dataset.i].acao();
  };
}
const fecharMenuCtx = () => $("#menu-ctx").classList.remove("aberto");
document.addEventListener("click", fecharMenuCtx);
document.addEventListener("contextmenu", e => {
  if (!e.target.closest("[data-video]")) fecharMenuCtx();
});
window.addEventListener("blur", fecharMenuCtx);

/* ---------------- cursor na barra do textarea ---------------- */
/* O cursor de texto do <textarea> vale pra CAIXA INTEIRA, inclusive a faixa onde a
   barra de rolagem desce. Normalmente nao incomoda porque o Windows desenha a barra
   por cima, com seta propria — mas a gente estilizou ela com ::-webkit-scrollbar, e
   ai o Chromium passa a desenhar como parte do elemento: o I-beam fica em cima dela.
   Nao existe seletor de cursor por regiao da barra, entao a saida e' medir: a barra
   ocupa offsetWidth - clientWidth px na direita (7 quando aparece, 0 quando nao). */
document.addEventListener("mousemove", e => {
  const t = e.target;
  if (!t || t.tagName !== "TEXTAREA") return;
  const barra = t.offsetWidth - t.clientWidth;
  const naBarra = barra > 0 && e.clientX >= t.getBoundingClientRect().right - barra;
  const quer = naBarra ? "default" : "";
  if (t.style.cursor !== quer) t.style.cursor = quer;
});

/* ---------------- alerta ---------------- */
/* o confirm() do navegador mostra "127.0.0.1:8777 diz" — feio num app nativo */
function confirmar(titulo, texto = "", ok = "OK", perigo = true) {
  return new Promise(resolve => {
    $("#alerta-titulo").textContent = titulo;
    $("#alerta-texto").textContent = texto;
    $("#alerta-texto").style.display = texto ? "" : "none";
    const sim = $("#alerta-sim"), nao = $("#alerta-nao");
    sim.textContent = ok;
    sim.classList.toggle("perigo", perigo);
    $("#alerta").classList.add("aberto");
    $("#alerta-fundo").classList.add("aberto");
    const fechar = v => {
      $("#alerta").classList.remove("aberto");
      $("#alerta-fundo").classList.remove("aberto");
      resolve(v);
    };
    sim.onclick = () => fechar(true);
    nao.onclick = () => fechar(false);
    $("#alerta-fundo").onclick = () => fechar(false);
  });
}

/* ---------------- sheet ---------------- */
let sheetOK = null;
function abrirSheet(titulo, html, onOK, okLabel = "OK") {
  $("#sheet-titulo").textContent = titulo;
  $("#sheet-corpo").innerHTML = html;
  $("#sheet-ok").textContent = okLabel;
  sheetOK = onOK;
  $("#backdrop").classList.add("aberto");
  $("#sheet").classList.add("aberto");
  setTimeout(() => $("#sheet-corpo input, #sheet-corpo textarea")?.focus(), 320);
}
function fecharSheet() {
  $("#backdrop").classList.remove("aberto");
  $("#sheet").classList.remove("aberto");
  sheetOK = null;
}
$("#sheet-cancel").onclick = fecharSheet;
$("#backdrop").onclick = fecharSheet;
$("#sheet-ok").onclick = async () => {
  if (!sheetOK) return;
  const btn = $("#sheet-ok");
  btn.disabled = true;
  try { await sheetOK(); } catch (e) { toast(e.message); } finally { btn.disabled = false; }
};

/* ================= CANAIS ================= */
async function verCanais() {
  irPara("canais");
  st.canal = null;              // saiu do canal: nada dele deve sobrar na memória
  st.canais = await api("/api/canais");
  const el = $("#lista-canais");
  if (!st.canais.length) {
    el.innerHTML = `<div class="vazio">Nenhum canal ainda.<br>Toque em <b>+</b> pra criar o primeiro.</div>`;
    return;
  }
  el.innerHTML = `<div class="group">` + st.canais.map(c => `
    <button class="row" onclick="verCanal('${c.id}')">
      <div class="av">${esc((c.nome || "?").trim()[0].toUpperCase())}</div>
      <div class="row-corpo">
        <div class="row-titulo">${esc(c.nome)}</div>
        <div class="row-sub">${esc(c.idioma)} · ${esc(c.preset_nome)} · ${c.n_videos} vídeo${c.n_videos === 1 ? "" : "s"}</div>
      </div>
      <div class="chevron"></div>
    </button>`).join("") + `</div>`;
}

function sheetNovoCanal() {
  if (!st.modelos.length) return toast("Cria um modelo primeiro (aba Modelos).");
  capaPendente = null;
  sheetCanal(null);
}

function sheetEditarCanal() { capaPendente = null; sheetCanal(st.canal); }

/* O que o usuário já digitou, guardado enquanto ele sai pra escolher a voz. A capa fica
   aqui como objeto porque um <input type=file> não pode ser repreenchido por código. */
let capaPendente = null;

/* O modelo vem do servidor (store.MODELO_PERSONAGEM) pra existir num lugar so': o mesmo
   texto alimenta o prompt do roteirista e o arquivo do projeto do Claude.
   O botao COPIA um pedido pronto: voce cola no Claude, descreve o personagem, ele
   devolve a ficha preenchida e voce cola de volta na caixa aqui. */
async function copiarModeloPersona() {
  const idioma = ($("#ec-idioma")?.value || "").trim();
  const pedido = [
    "Vou anexar a foto do narrador do meu canal do YouTube. Preencha a ficha dele.",
    idioma ? `Idioma do canal: ${idioma}` : "Idioma do canal: (escreva aqui)",
    "",
    "A idade sai da foto. O nome você inventa, já no idioma do canal, e tem que",
    "combinar com a idade e a região de quem aparece na imagem.",
    "",
    "Responda SÓ a ficha preenchida, uma linha por item, sem comentário nenhum",
    "antes nem depois, e sem deixar linha em branco.",
    "",
    st.cfg?.modelo_personagem || "",
  ].join("\n");
  try {
    await navigator.clipboard.writeText(pedido);
    toast("Copiado — cole no Claude com a foto");
  } catch (e) { toast("Não consegui copiar"); }
}

function lerFormCanal() {
  const v = id => $("#" + id)?.value ?? "";
  return {
    nome: v("ec-nome"), idioma: v("ec-idioma"),
    preset_id: v("ec-preset"), _editando: $("#ec-preset") ? null : st.canal?.id,
    produto_nome: v("ec-pnome"), produto_site: v("ec-psite"), produto_desc: v("ec-pdesc"),
    cor_fundo: v("ec-fundo"), cor_destaque: v("ec-destaque"),
    voz_id: $("#ec-voz")?.dataset.id || "", voz_nome: $("#ec-voz")?.dataset.nome || "",
    produto_capa: $("#ec-capa-sub")?.dataset.tinha || "",
    personagem: v("ec-persona"),
  };
}

/* mesmo formulário pros dois casos: o que muda é o seletor de modelo (só na criação,
   porque trocar o modelo de um canal com vídeos prontos bagunçaria o histórico) */
function sheetCanal(canal) {
  const novo = !canal?.id;
  const c = canal || { nome: "", idioma: "", produto_nome: "", produto_site: "",
                       produto_desc: "", cor_fundo: "#7A3320", cor_destaque: "#E3A63C",
                       produto_capa: "", voz_id: "", voz_nome: "", personagem: "" };
  abrirSheet(novo ? "Novo canal" : "Editar canal", `
    <div class="group-label">Canal</div>
    <div class="group">
      <label class="row field"><span class="field-nome">Nome</span>
        <input id="ec-nome" value="${esc(c.nome)}" placeholder="Bodo" autocomplete="off"></label>
      <label class="row field"><span class="field-nome">Idioma</span>
        <input id="ec-idioma" list="idiomas" value="${esc(c.idioma)}"
          placeholder="Deutsch" autocomplete="off"></label>
      ${novo ? `<label class="row field"><span class="field-nome">Modelo</span>
        <select id="ec-preset">${st.modelos.map(p =>
          `<option value="${p.id}">${esc(p.nome)}</option>`).join("")}</select>
      </label>` : ""}
      <button class="row" id="ec-voz" data-id="${esc(c.voz_id || "")}"
              data-nome="${esc(c.voz_nome || "")}" onclick="escolherVozNoForm()">
        <span class="field-nome">Voz</span>
        <span class="row-valor crescivel ${c.voz_nome ? "" : "vazio-valor"}">${
          c.voz_nome ? esc(c.voz_nome) : "escolher"}</span>
        <div class="chevron"></div>
      </button>
    </div>
    <datalist id="idiomas">${IDIOMAS.map(i => `<option value="${i}">`).join("")}</datalist>

    <div class="group-label">Personagem</div>
    <div class="group">
      <label class="row field">
        <textarea id="ec-persona" placeholder="Quem narra os vídeos deste canal"
          style="min-height:168px">${esc(c.personagem || "")}</textarea></label>
    </div>
    <div class="group-nota">Preenchido uma vez, vale para todos os vídeos do canal. Sem
      isso a IA inventa um nome, uma idade e uma história novos a cada vídeo.</div>
    <div class="pad">
      <button class="btn secundario" onclick="copiarModeloPersona()">Copiar modelo pro Claude</button>
    </div>

    <div class="group-label">Produto — opcional</div>
    <div class="group">
      <label class="row field"><span class="field-nome">Nome</span>
        <input id="ec-pnome" value="${esc(c.produto_nome)}" placeholder="The Barn Find Bible"></label>
      <label class="row field"><span class="field-nome">Site</span>
        <input id="ec-psite" value="${esc(c.produto_site)}" placeholder="barnfindbible.com"></label>
      <label class="row field">
        <textarea id="ec-pdesc" placeholder="Descrição curta (aparece no card)"
          style="min-height:56px">${esc(c.produto_desc)}</textarea></label>
      <label class="row field"><span class="field-nome">Cor do fundo</span>
        <input id="ec-fundo" type="color" value="${esc(c.cor_fundo || "#7A3320")}"></label>
      <label class="row field"><span class="field-nome">Cor do destaque</span>
        <input id="ec-destaque" type="color" value="${esc(c.cor_destaque || "#E3A63C")}"></label>
      <input type="file" id="ec-capa" accept="image/png,image/jpeg,image/webp" hidden>
      <button class="row" onclick="document.getElementById('ec-capa').click()">
        <div class="row-corpo">
          <div class="row-titulo">Capa</div>
          <div class="row-sub" id="ec-capa-sub">${c.produto_capa
            ? "anexada" : "1000 × 1500 px, proporção 2:3"}</div>
        </div>
        <div class="row-valor">${c.produto_capa ? "trocar" : "anexar"}</div>
      </button>
    </div>
    <div class="group-nota">Deixe vazio se o canal não vende nada — o roteiro sai sem
      anúncio e sem card. Quando preenchido, o card aparece uma vez, no momento em que a
      narração anuncia o produto.</div>
    <div class="pad">
      <button class="btn secundario" onclick="abrirLink('${EXEMPLO_CARD}')">
        Ver exemplo do card</button>
    </div>`,
    async () => {
      const d = lerFormCanal();
      const campos = {
        nome: d.nome, idioma: d.idioma,
        produto_nome: d.produto_nome, produto_site: d.produto_site,
        produto_desc: d.produto_desc,
        cor_fundo: d.cor_fundo, cor_destaque: d.cor_destaque,
        voz_id: d.voz_id, voz_nome: d.voz_nome, personagem: d.personagem,
      };
      let alvo = c;
      if (novo) {
        alvo = await api("/api/canais", { method: "POST", body: {
          nome: d.nome, idioma: d.idioma, preset_id: d.preset_id }});
      }
      await api(`/api/canais/${alvo.id}/editar`, { method: "POST", body: campos });
      const f = capaPendente || $("#ec-capa").files[0];
      if (f) {
        const b64 = await new Promise(r => {
          const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(f);
        });
        await api(`/api/canais/${alvo.id}/capa`, { method: "POST",
                                                   body: { nome: f.name, conteudo: b64 } });
      }
      capaPendente = null;
      fecharSheet();
      novo ? verCanais() : verCanal(alvo.id);
      toast(novo ? "Canal criado" : "Canal salvo");
    }, novo ? "Criar" : "Salvar");

  if (capaPendente) $("#ec-capa-sub").textContent = "✓ " + capaPendente.name;
  $("#ec-capa").onchange = e => {
    const f = e.target.files[0];
    if (f) { capaPendente = f; $("#ec-capa-sub").textContent = "✓ " + f.name; }
  };
}

/* ================= CANAL ================= */
async function verCanal(cid) {
  st.canal = await api("/api/canais/" + cid);
  irPara("canal");
  $("#canal-nav-titulo").textContent = st.canal.nome;
  $("#canal-titulo").textContent = st.canal.nome;
  await carregarVideos();
}

async function carregarVideos() {
  if (!st.canal) return;
  st.videos = await api(`/api/canais/${st.canal.id}/videos`);
  const el = $("#lista-videos");
  if (!st.videos.length) {
    el.innerHTML = `<div class="vazio">Nenhum vídeo ainda.</div>`;
  } else {
    el.innerHTML = `<div class="group-label">Vídeos</div><div class="group">` +
      st.videos.map(v => `
      <button class="row" data-video="${esc(v.id)}" onclick="verVideo('${v.id}')">
        <div class="row-corpo">
          <div class="row-titulo">${esc(v.titulo)}</div>
          <div class="row-sub">${v.dur} min · ${
            v.estado === "gerando" ? `escrevendo… ${v.n_chars.toLocaleString("pt-BR")} caracteres`
            : v.estado === "pronto" ? `${v.n_chars.toLocaleString("pt-BR")} caracteres`
            : v.estado === "erro" ? "falhou" : "na fila"}</div>
        </div>
        ${v.estado === "gerando" ? `<div class="spinner"></div>`
          : `<span class="badge ${v.estado}">${
              v.estado === "pronto" ? "pronto" : v.estado === "erro" ? "erro" : "fila"}</span>`}
        <div class="chevron"></div>
      </button>`).join("") + `</div>`;
  }
  el.oncontextmenu = e => {
    const linha = e.target.closest("[data-video]");
    if (!linha) return;
    const v = st.videos.find(x => x.id === linha.dataset.video);
    menuContexto(e, [{ texto: "Apagar vídeo", perigo: true,
                       acao: () => apagarVideo(v.id, v.titulo) }]);
  };
  if (st.videos.some(v => v.estado === "gerando" || v.estado === "fila")) {
    agendar(carregarVideos, 1500);
  }
}

function sheetNovoVideo() {
  abrirSheet("Criar vídeo", `
    <div class="segmented" id="nv-modo">
      <button class="seg ativo" data-v="gerar">Gerar roteiro</button>
      <button class="seg" data-v="colar">Já tenho o roteiro</button>
    </div>
    <div class="group-label">Vídeo</div>
    <div class="group">
      <label class="row field">
        <textarea id="nv-titulo" placeholder="Título do vídeo"
          style="min-height:52px"></textarea></label>
    </div>
    <div id="nv-gerar">
      <div class="group-label">Duração</div>
      <div class="segmented" id="nv-dur">
        ${DURACOES.map((m, i) => `<button class="seg ${i === 0 ? "ativo" : ""}"
          data-v="${m}">${m}</button>`).join("")}
      </div>
    </div>
    <div id="nv-colar" hidden>
      <div class="group-label">Roteiro</div>
      <div class="group">
        <label class="row field">
          <textarea id="nv-roteiro" placeholder="Cola aqui o roteiro pronto"
            style="min-height:120px"></textarea></label>
      </div>
      <div class="group-nota" id="nv-conta">A duração sai do tamanho do texto.</div>
      <div class="tabela-ref" id="nv-tabela">
        <div class="cabeca"><b>duração</b><span>caracteres</span></div>
        ${DURACOES.map(m => `
        <div data-min="${m}"><b>${m} min</b><span>${(m * CPM()).toLocaleString("pt-BR")}</span></div>`
        ).join("")}</div>
    </div>`,
    async () => {
      const colando = $("#nv-modo .seg.ativo").dataset.v === "colar";
      await api("/api/videos", { method: "POST", body: {
        canal_id: st.canal.id,
        titulo: $("#nv-titulo").value,
        dur: $("#nv-dur .seg.ativo").dataset.v,
        roteiro: colando ? $("#nv-roteiro").value : "",
      }});
      fecharSheet();
      carregarVideos();
      toast(colando ? "Roteiro salvo" : "Escrevendo o roteiro…");
    }, "Criar");

  const marcar = (grupo, botao) => {
    $$(".seg", grupo).forEach(x => x.classList.remove("ativo"));
    botao.classList.add("ativo");
  };
  $("#nv-dur").onclick = e => {
    const b = e.target.closest(".seg");
    if (b) marcar($("#nv-dur"), b);
  };
  $("#nv-modo").onclick = e => {
    const b = e.target.closest(".seg");
    if (!b) return;
    marcar($("#nv-modo"), b);
    const colando = b.dataset.v === "colar";
    $("#nv-gerar").hidden = colando;
    $("#nv-colar").hidden = !colando;
  };
  $("#nv-roteiro").oninput = e => {
    const n = e.target.value.trim().length;
    const min = Math.max(1, Math.round(n / CPM()));
    $("#nv-conta").textContent = n
      ? `${n.toLocaleString("pt-BR")} caracteres · ${min} min de narração`
      : "A duração sai do tamanho do texto.";
    // acende a linha da tabela onde esse roteiro cai
    // acende a linha MAIS PRÓXIMA, não só a exata: com 11.000 caracteres nenhuma das
    // cinco batia e a tabela ficava toda apagada, sem te dizer de qual você chegou perto
    const perto = n ? DURACOES.reduce((a, b) =>
      Math.abs(b * CPM() - n) < Math.abs(a * CPM() - n) ? b : a) : null;
    $$("#nv-tabela div[data-min]").forEach(d =>
      d.classList.toggle("aceso", +d.dataset.min === perto));
  };
}

async function apagarCanal() {
  if (!await confirmar("Apagar canal?",
        `"${st.canal.nome}" e todos os vídeos dele serão apagados.`, "Apagar")) return;
  await api("/api/canais/" + st.canal.id, { method: "DELETE" });
  verCanais();
  toast("Canal apagado");
}

/* ================= VÍDEO ================= */
async function verVideo(vid) {
  st.video = await api("/api/videos/" + vid);
  videoEtapa = primeiraEtapaPendente(st.video);   // abre onde o trabalho parou
  // limpa ANTES de revelar: o irPara mostra a tela com o que sobrou da visita
  // anterior, e a animação de entrada dá tempo de você ver a etapa errada
  $("#video-corpo").innerHTML = "";
  $("#video-titulo").textContent = st.video.titulo;
  $("#video-sub").textContent = "";
  irPara("video");
  pintarVideo();
}

/* A tela do vídeo é um passo a passo: uma etapa por vez, com "Próximo" embaixo.
   Antes tudo empilhava junto e o roteiro acabava no fim, depois do que depende dele. */
const ETAPAS = ["Roteiro", "Narração", "Direção", "Montagem"];
let videoEtapa = 1;

function primeiraEtapaPendente(v) {
  if (v.estado !== "pronto") return 1;
  if (v.audio_estado !== "pronto") return 2;
  if (v.direcao_estado !== "pronto") return 3;
  return 4;
}

function irEtapa(n) {
  videoEtapa = Math.max(1, Math.min(ETAPAS.length, n));
  pintarVideo();
  $("#rolagem").scrollTop = 0;
}

function pintarVideo() {
  const v = st.video;
  $("#video-titulo").textContent = v.titulo;
  // enquanto escreve, o texto crescendo na tela já mostra o progresso — a linha aqui
  // só atrapalhava com número zerado e alvo
  $("#video-sub").textContent =
    v.estado === "pronto" ? `${v.dur} min · ${v.n_chars.toLocaleString("pt-BR")} caracteres`
    : v.estado === "erro" ? `${v.dur} min`
    : `${v.dur} min · escrevendo…`;

  $("#video-etapa-nome").textContent = ETAPAS[videoEtapa - 1];
  $("#video-passo").textContent = `${videoEtapa}/${ETAPAS.length}`;
  $("#video-back").textContent = videoEtapa > 1 ? ETAPAS[videoEtapa - 2] : (st.canal?.nome || "Canal");
  $("#video-back").onclick = () =>
    videoEtapa > 1 ? irEtapa(videoEtapa - 1) : verCanal(v.canal_id);

  const proximo = videoEtapa < ETAPAS.length
    ? `<div class="pad" style="padding-top:18px">
         <button class="btn grande" onclick="irEtapa(${videoEtapa + 1})">Próximo</button>
       </div>` : "";

  const c = $("#video-corpo");
  c.innerHTML = [blocoRoteiro, blocoAudio, blocoDirecao, blocoMontagem][videoEtapa - 1](v)
                + proximo;
  if (v.estado === "gerando" || v.estado === "fila" || v.audio_estado === "gerando"
      || v.direcao_estado === "gerando" || v.montagem_estado === "montando") {
    agendar(async () => {
      st.video = await api("/api/videos/" + v.id);
      pintarVideo();
    }, 1200);
  }
}

/* etapa 1: o roteiro */
function blocoRoteiro(v) {
  if (v.estado === "erro") return `
    <div class="caixa-erro">${esc(v.erro)}</div>
    <div class="acoes">
      <button class="btn secundario" onclick="refazerRoteiro()">Tentar de novo</button>
      <button class="btn destrutivo" onclick="apagarVideo()">Apagar</button>
    </div>`;
  if (!v.roteiro) return `
    <div class="vazio"><div class="spinner" style="margin:0 auto 14px"></div>
      Pensando na abertura…</div>`;
  return `
    ${v.aviso ? `<div class="caixa-aviso">⚠️ ${esc(v.aviso)}</div>` : ""}
    <div class="roteiro ${v.estado === "gerando" ? "parcial" : ""}">${esc(v.roteiro)}</div>
    ${v.estado === "pronto" ? `<div class="pad">
      <button class="btn secundario" onclick="refazerRoteiro()">Refazer roteiro</button>
    </div>` : ""}`;
}

/* etapa 2: narração. A API traz o audio.mp3 e o blocos.srt juntos. */
function blocoAudio(v) {
  if (v.estado !== "pronto") return `
    <div class="vazio">Termina o roteiro primeiro.</div>`;
  const e = v.audio_estado;
  if (e === "gerando") return `
    <div class="group"><div class="row">
      <div class="spinner"></div>
      <div class="row-corpo">
        <div class="row-titulo">Gerando a narração</div>
        <div class="row-sub">${esc(v.audio_msg || "…")}</div>
      </div>
    </div></div>`;
  if (e === "erro") return `
    <div class="caixa-erro">${esc(v.audio_erro)}</div>
    <div class="pad"><button class="btn secundario" onclick="gerarAudio()">Tentar de novo</button></div>`;
  if (e === "pronto") return `
    <div class="group">
      <div class="row"><audio controls class="player" src="/api/videos/${v.id}/audio.mp3"></audio></div>
      <button class="row" onclick="abrirPasta()">
        <div class="row-corpo">
          <div class="row-titulo">Abrir pasta</div>
          <div class="row-sub">audio.mp3 · blocos.srt · roteiro.txt</div>
        </div>
        <div class="chevron"></div>
      </button>
    </div>`;
  return `<div class="pad"><button class="btn" onclick="gerarAudio()">Gerar áudio</button></div>`;
}

/* etapa 3: direção — decide o que aparece na tela em cada bloco */
function blocoDirecao(v) {
  if (v.audio_estado !== "pronto") return `
    <div class="vazio">Gera a narração primeiro — a direção precisa do blocos.srt.</div>`;
  const e = v.direcao_estado;
  if (e === "gerando") return `
    <div class="group"><div class="row">
      <div class="spinner"></div>
      <div class="row-corpo">
        <div class="row-titulo">Decidindo o que aparece na tela</div>
        <div class="row-sub">${esc(v.direcao_msg || "…")}</div>
      </div>
    </div></div>`;
  if (e === "erro") return `
    <div class="caixa-erro">${esc(v.direcao_erro)}</div>
    <div class="pad"><button class="btn secundario" onclick="gerarDirecao()">Tentar de novo</button></div>`;
  if (e === "pronto") {
    const r = v.direcao_resumo || {};
    return `
    <div class="group">
      <div class="row"><div class="row-corpo">
        <div class="row-titulo">${r.blocos} blocos</div>
        <div class="row-sub">${r.avatar} avatar · ${r.imagem} imagem · ${r.video} vídeo${
          r.card ? " · 1 card" : ""}</div>
      </div></div>
      <div class="row"><div class="row-corpo">
        <div class="row-titulo">${r.flow} prompts</div>
        <div class="row-sub">cola no DarkPlanner — ${r.video} deles viram vídeo</div>
      </div></div>
      <button class="row" onclick="abrirPasta()">
        <div class="row-corpo"><div class="row-titulo">Abrir pasta</div>
          <div class="row-sub">prompts_flow.txt · plano.json · preview.txt</div></div>
        <div class="chevron"></div>
      </button>
    </div>
    <div class="pad">
      <button class="btn" onclick="copiarPrompts(this)">Copiar prompts</button>
    </div>
    <div class="group-nota">Cola no multiprompt do DarkPlanner. Ele baixa as imagens e
      os vídeos sozinho.</div>`;
  }
  return `<div class="pad"><button class="btn" onclick="gerarDirecao()">Gerar direção</button></div>`;
}

/* etapa final: os arquivos que vêm de fora + a montagem */
function blocoMontagem(v) {
  if (v.direcao_estado !== "pronto") return `
    <div class="vazio">Gera a direção primeiro.</div>`;
  const b = v.broll_resumo || {};
  const e = v.montagem_estado;
  const nome = c => (c || "").split("\\").pop();

  if (e === "montando") return `
    <div class="group"><div class="row">
      <div class="spinner"></div>
      <div class="row-corpo">
        <div class="row-titulo">Montando o vídeo</div>
        <div class="row-sub">${esc(v.montagem_msg || "…")}</div>
      </div>
    </div></div>`;

  const arquivos = `
    <div class="group">
      <button class="row" onclick="anexarAvatar()">
        <div class="row-corpo">
          <div class="row-titulo">Avatar</div>
          <div class="row-sub">${v.avatar_path
            ? esc(nome(v.avatar_path)) : "anexar o .mp4 do HeyGen"}</div>
        </div>
        <div class="row-valor">${v.avatar_path ? "trocar" : "anexar"}</div>
      </button>
      <button class="row" onclick="apontarBroll()">
        <div class="row-corpo">
          <div class="row-titulo">Imagens e vídeos</div>
          <div class="row-sub">${b.imagem !== undefined
            ? `${b.imagem} imagens · ${b.video} vídeos`
            : "apontar a pasta do DarkPlanner"}</div>
        </div>
        <div class="row-valor">${b.imagem !== undefined ? "trocar" : "apontar"}</div>
      </button>
    </div>`;

  if (e === "erro") return `
    ${arquivos}
    <div class="caixa-erro">${esc(v.montagem_erro)}</div>
    <div class="pad"><button class="btn" onclick="montar()">Tentar de novo</button></div>`;

  if (e === "pronto") return `
    ${arquivos}
    <div class="group"><button class="row" onclick="abrirPasta()">
      <div class="row-corpo">
        <div class="row-titulo">✅ Vídeo pronto</div>
        <div class="row-sub">${esc(nome(v.montagem_saida))}${v.montagem_faltaram
          ? ' · ' + v.montagem_faltaram + ' bloco' + (v.montagem_faltaram === 1 ? '' : 's')
            + ' sem imagem, o avatar cobriu' : ''}</div>
      </div><div class="chevron"></div>
    </button></div>
    <div class="pad"><button class="btn secundario" onclick="montar()">Montar de novo</button></div>`;

  return `
    ${arquivos}
    <div class="pad"><button class="btn" onclick="montar()">Montar vídeo</button></div>`;
}

const nativo = () => window.pywebview?.api;

async function anexarAvatar() {
  if (!nativo()) return toast("só funciona na janela do app");
  const caminho = await window.pywebview.api.escolher_arquivo();
  if (!caminho) return;
  try {
    st.video = await api(`/api/videos/${st.video.id}/avatar`,
                         { method: "POST", body: { caminho } });
    pintarVideo();
  } catch (e) { toast(e.message); }
}

async function apontarBroll() {
  if (!nativo()) return toast("só funciona na janela do app");
  const pasta = await window.pywebview.api.escolher_pasta();
  if (!pasta) return;
  toast("importando…");
  try {
    st.video = await api(`/api/videos/${st.video.id}/broll`,
                         { method: "POST", body: { pasta } });
    const b = st.video.broll_resumo || {};
    toast(`${b.imagem} imagens · ${b.video} vídeos`);
    pintarVideo();
  } catch (e) { toast(e.message); }
}

async function montar() {
  try {
    st.video = await api(`/api/videos/${st.video.id}/montar`, { method: "POST" });
    pintarVideo();
  } catch (e) { toast(e.message); }
}

async function copiarPrompts(botao) {
  const r = await fetch(`/api/videos/${st.video.id}/prompts`);
  if (!r.ok) { toast("gera a direção primeiro"); return; }
  const txt = await r.text();
  await navigator.clipboard.writeText(txt);
  const n = txt.split("\n").filter(l => l.trim()).length;
  botao.textContent = `✓ ${n} prompts copiados`;
  setTimeout(() => botao.textContent = "Copiar prompts", 2500);
}

async function gerarDirecao() {
  try {
    st.video = await api(`/api/videos/${st.video.id}/direcao`, { method: "POST" });
    pintarVideo();
  } catch (e) { toast(e.message); }
}

async function refazerRoteiro() {
  if (!await confirmar("Refazer o roteiro?",
        "O áudio e a direção desse vídeo serão descartados.", "Refazer")) return;
  try {
    st.video = await api(`/api/videos/${st.video.id}/refazer`, { method: "POST" });
    pintarVideo();
    toast("Reescrevendo…");
  } catch (e) { toast(e.message); }
}

async function gerarAudio() {
  try {
    st.video = await api(`/api/videos/${st.video.id}/audio`, { method: "POST" });
    pintarVideo();
  } catch (e) { toast(e.message); }
}

async function abrirPasta() {
  try { await api(`/api/videos/${st.video.id}/pasta`, { method: "POST" }); }
  catch (e) { toast(e.message); }
}

async function copiar() {
  await navigator.clipboard.writeText(st.video.roteiro || "");
  toast("Roteiro copiado");
}

/* serve pros dois: o botão da tela do vídeo e o menu do botão direito na lista */
async function apagarVideo(id, titulo) {
  const alvo = id || st.video?.id;
  if (!alvo) return;
  const nome = titulo || st.video?.titulo || "";
  if (!await confirmar("Apagar vídeo?", nome ? `"${nome}"` : "", "Apagar")) return;
  const cid = st.video?.canal_id || st.canal?.id;
  await api("/api/videos/" + alvo, { method: "DELETE" });
  if (st.video?.id === alvo) verCanal(cid); else carregarVideos();
  toast("Vídeo apagado");
}

/* ================= VOZES ================= */
/* Ao criar um canal ele ainda não existe no servidor, então a voz não tem onde ser
   salva. Por isso o picker devolve a escolha pro formulário, junto com tudo que já
   estava digitado, e só vai pro servidor quando você aperta Criar/Salvar. */
let rascunhoCanal = null;

function escolherVozNoForm() {
  const d = lerFormCanal();
  // sem idioma não dá pra filtrar nem tocar o preview certo — a lista seria inútil
  if (!d.idioma.trim()) return toast("Escolhe o idioma do canal primeiro.");
  rascunhoCanal = d;
  fecharSheet();
  verVozes();
}

async function verVozes() {
  irPara("vozes");
  const voltando = !!rascunhoCanal;
  $("#vozes-back").textContent = voltando ? "Voltar" : (st.canal?.nome || "Canal");
  $("#vozes-back").onclick = () => {
    if (rascunhoCanal) {
      const d = rascunhoCanal; rascunhoCanal = null;
      irPara(d._editando ? "canal" : "canais");
      sheetCanal(d._editando ? { ...d, id: d._editando } : d);
    } else verCanal(st.canal.id);
  };
  $("#voz-q").value = "";
  $$(".seg", $("#voz-genero")).forEach((s, i) => s.classList.toggle("ativo", i === 0));
  await carregarVozes();
  $("#voz-q").oninput = () => { clearTimeout(window._tv);
    window._tv = setTimeout(carregarVozes, 250); };
  $("#voz-genero").onclick = e => {
    const b = e.target.closest(".seg");
    if (!b) return;
    $$(".seg", $("#voz-genero")).forEach(x => x.classList.remove("ativo"));
    b.classList.add("ativo");
    carregarVozes();
  };
}

let vozPagina = 1;

async function carregarVozes(pagina) {
  vozPagina = pagina || 1;                     // busca ou filtro novo volta pra 1
  const q = $("#voz-q").value.trim();
  const g = $("#voz-genero .seg.ativo").dataset.v || "";
  const idioma = idiomaAtual();
  const el = $("#lista-vozes");
  el.innerHTML = `<div class="vazio"><div class="spinner" style="margin:0 auto"></div></div>`;
  let d;
  try {
    d = await api(`/api/vozes?q=${encodeURIComponent(q)}&genero=${g}` +
                  `&idioma=${encodeURIComponent(idioma)}&limite=60&pagina=${vozPagina}`);
  } catch (e) { el.innerHTML = `<div class="caixa-erro">${esc(e.message)}</div>`; return; }
  vozPagina = d.pagina;
  if (!d.vozes.length) { el.innerHTML = `<div class="vazio">Nenhuma voz com esse nome.</div>`; return; }
  // veio do formulário? então só o rascunho manda. Sem o "?" aqui, um rascunho com voz
  // vazia caía pro st.canal e marcava a voz de um canal antigo (ou já apagado).
  const atual = rascunhoCanal ? rascunhoCanal.voz_id : st.canal?.voz_id;

  // id e nome vão em data-*, não interpolados dentro do onclick: nome de voz tem aspas
  // e vírgula, e a aspa fecharia o atributo HTML no meio — o clique não fazia nada.
  const linha = v => `
      <div class="row ${v.id === atual ? "escolhida" : ""}"
           data-vid="${esc(v.id)}" data-vnome="${esc(v.nome)}">
        <button class="play" title="Ouvir">▶</button>
        <div class="row-corpo">
          <div class="row-titulo">${esc(v.nome)}</div>
          <div class="row-sub">${v.genero === "female" ? "feminina" : "masculina"}${
            v.id === atual ? " · em uso" : ""}</div>
        </div>
        <button class="btn-mini">${v.id === atual ? "✓" : "usar"}</button>
      </div>`;

  const noIdioma = d.vozes.filter(v => v.grupo === "idioma");
  const semInfo = d.vozes.filter(v => v.grupo === "sem_idioma");
  let html = "";
  if (noIdioma.length) {
    html += `<div class="group-label">${d.total} voz${d.total === 1 ? "" : "es"} em ${
      esc(idioma)}${d.paginas > 1 ? ` · ${d.de}–${d.ate}` : ""}</div>
      <div class="group">${noIdioma.map(linha).join("")}</div>`;
    if (d.paginas > 1) html += `
      <div class="paginacao">
        <button ${d.pagina <= 1 ? "disabled" : ""} onclick="carregarVozes(${d.pagina - 1})">‹</button>
        <span>${d.pagina} de ${d.paginas}</span>
        <button ${d.pagina >= d.paginas ? "disabled" : ""} onclick="carregarVozes(${d.pagina + 1})">›</button>
      </div>`;
  }
  if (semInfo.length) {
    html += `<div class="group-label">Sem idioma informado</div>
      <div class="group">${semInfo.map(linha).join("")}</div>
      <div class="group-nota">Essas não declaram em que idiomas foram testadas.
        Podem funcionar — ouça antes.</div>`;
  }
  el.innerHTML = html;
  el.onclick = e => {
    const linha = e.target.closest(".row[data-vid]");
    if (!linha) return;
    const play = e.target.closest(".play");
    if (play) ouvir(linha.dataset.vid, play);
    else usarVoz(linha.dataset.vid, linha.dataset.vnome);
  };
}

function idiomaAtual() {
  return (rascunhoCanal?.idioma || st.canal?.idioma || "").trim();
}

let tocando = null;
function ouvir(id, botao) {
  const p = $("#player");
  if (tocando && tocando !== botao) tocando.textContent = "▶";
  if (tocando === botao && !p.paused) { p.pause(); botao.textContent = "▶"; tocando = null; return; }
  botao.textContent = "…";
  // preview no idioma do canal: é ouvindo a voz falar alemão que se julga um canal alemão
  p.src = `/api/vozes/${id}/preview?idioma=${encodeURIComponent(idiomaAtual())}`;
  p.play().then(() => { botao.textContent = "❚❚"; tocando = botao; })
          .catch(() => { botao.textContent = "▶"; toast("não consegui tocar essa voz"); });
  p.onended = () => { botao.textContent = "▶"; tocando = null; };
}

async function usarVoz(id, nome) {
  if (rascunhoCanal) {                     // veio do formulário: devolve pra lá
    const d = { ...rascunhoCanal, voz_id: id, voz_nome: nome };
    rascunhoCanal = null;
    irPara(d._editando ? "canal" : "canais");
    sheetCanal(d._editando ? { ...d, id: d._editando } : d);
    return;
  }
  st.canal = await api(`/api/canais/${st.canal.id}/voz`,
                       { method: "POST", body: { voz_id: id, voz_nome: nome } });
  toast(`Voz do canal: ${nome}`);
  verCanal(st.canal.id);
}

/* ================= MODELOS ================= */
async function verModelos() {
  irPara("modelos");
  await carregarModelos();
}

async function carregarModelos() {
  st.modelos = await api("/api/presets");
  const el = $("#lista-modelos");
  if (!st.modelos.length) {
    el.innerHTML = `<div class="vazio">Nenhum modelo ainda.<br>
      Toque em <b>+</b> e anexe um <code>.txt</code> com roteiros.</div>`;
    return;
  }
  el.innerHTML = `<div class="group">` + st.modelos.map(p => `
    <div class="row">
      <div class="row-corpo">
        <div class="row-titulo">${esc(p.nome)}</div>
        <div class="row-sub">${p.n_roteiros} roteiro${p.n_roteiros === 1 ? "" : "s"} ·
          ${Math.round(p.n_chars / 1000).toLocaleString("pt-BR")} mil caracteres${
          p.origem ? " · " + esc(p.origem) : ""}</div>
      </div>
      <button class="icon-btn" style="color:var(--red);font-size:15px;width:auto;padding:0 4px"
        onclick="apagarModelo('${p.id}')">Apagar</button>
    </div>`).join("") + `</div>`;
}

function sheetNovoModelo() {
  abrirSheet("Novo modelo", `
    <div class="group-label">Modelo</div>
    <div class="group">
      <label class="row field"><span class="field-nome">Nome</span>
        <input id="nm-nome" placeholder="cozinheiro" autocomplete="off"></label>
    </div>
    <div class="group-label">Roteiros de treinamento</div>
    <div class="pad" style="padding-top:0">
      <input type="file" id="nm-file" accept=".json,.txt,application/json,text/plain" hidden>
      <button class="arquivo-btn" id="nm-btn" onclick="document.getElementById('nm-file').click()">
        Anexar arquivo</button>
    </div>`,
    async () => {
      const f = $("#nm-file").files[0];
      if (!f) throw new Error("anexa o arquivo primeiro.");
      const conteudo = await f.text();
      const p = await api("/api/presets", { method: "POST", body: {
        nome: $("#nm-nome").value, conteudo, origem: f.name,
      }});
      fecharSheet();
      carregarModelos();
      toast(`Modelo "${p.nome}" criado — ${p.n_roteiros} roteiros`);
    }, "Criar");

  $("#nm-file").onchange = e => {
    const f = e.target.files[0];
    if (!f) return;
    const b = $("#nm-btn");
    b.textContent = "✓ " + f.name;
    b.classList.add("ok");
    if (!$("#nm-nome").value) {
      $("#nm-nome").value = f.name.replace(/\.(json|txt)$/i, "");
    }
  };
}

async function apagarModelo(pid) {
  if (!await confirmar("Apagar modelo?", "", "Apagar")) return;
  try {
    await api("/api/presets/" + pid, { method: "DELETE" });
    carregarModelos();
    toast("Modelo apagado");
  } catch (e) { toast(e.message); }
}

/* ================= AJUSTES ================= */
async function verAjustes() {
  irPara("ajustes");
  st.cfg = await api("/api/config");
  $("#cfg-key").value = st.cfg.tem_key ? st.cfg.anthropic_key : "";
  $("#cfg-key").type = st.cfg.tem_key ? "text" : "password";
  $("#cfg-dpkey").value = st.cfg.tem_key_dp ? st.cfg.darkplanner_key : "";
  $("#cfg-dpkey").type = st.cfg.tem_key_dp ? "text" : "password";
  $("#cfg-modelo").value = st.cfg.modelo;
}

async function salvarCfg() {
  st.cfg = await api("/api/config", { method: "POST", body: {
    anthropic_key: $("#cfg-key").value,
    darkplanner_key: $("#cfg-dpkey").value,
    modelo: $("#cfg-modelo").value,
  }});
  toast("Salvo");
  verAjustes();
}


/* ---------------- atualizacao ---------------- */
/* Compara a VERSAO local com a tag da ultima release do GitHub. Baixa o zip e escreve
   por cima, menos data/ (suas chaves e canais) e bin/ (o ffmpeg, que nao vai pro repo). */
let updZip = null;

async function verificarAtualizacao() {
  const sub = $("#upd-sub"), val = $("#upd-valor"), notas = $("#upd-notas");
  val.textContent = "…"; notas.textContent = "";
  updZip = null;
  let d;
  try { d = await api("/api/versao"); }
  catch (e) { sub.textContent = "erro: " + e.message; val.textContent = "buscar"; return; }

  if (!d.configurado) {
    sub.textContent = `versão ${d.atual} · sem repositório configurado`;
    notas.textContent = "Preencha REPO no arquivo versao.py com usuário/repositório.";
    val.textContent = "—";
    return;
  }
  if (d.erro) {
    sub.textContent = `versão ${d.atual}`;
    notas.textContent = d.erro;
    val.textContent = "buscar";
    return;
  }
  if (!d.ha_atualizacao) {
    sub.textContent = `versão ${d.atual} · já é a mais nova`;
    val.textContent = "buscar";
    return;
  }
  updZip = d.zip;
  sub.textContent = `${d.atual} → ${d.ultima} disponível`;
  notas.textContent = d.notas || "";
  val.textContent = "atualizar";
  $("#btn-atualizar").onclick = aplicarAtualizacao;
}

async function aplicarAtualizacao() {
  if (!updZip) return verificarAtualizacao();
  if (!await confirmar("Atualizar o app?",
        "Seus canais, vídeos e chaves não são tocados. Depois é só fechar e abrir.",
        "Atualizar", false)) return;
  const val = $("#upd-valor");
  val.textContent = "baixando…";
  try {
    const r = await api("/api/atualizar", { method: "POST", body: { zip: updZip } });
    $("#upd-sub").textContent = r.msg;
    val.textContent = "pronto";
    $("#btn-atualizar").onclick = verificarAtualizacao;
    updZip = null;
  } catch (e) {
    $("#upd-sub").textContent = "falhou: " + e.message;
    val.textContent = "tentar";
  }
}

/* ---------------- moldura própria ---------------- */
const naJanela = () => !!window.pywebview?.api;
$("#tb-min").onclick = () => naJanela() ? window.pywebview.api.minimizar() : null;
$("#tb-close").onclick = () => naJanela() ? window.pywebview.api.fechar() : window.close();

/* ---------------- polling ---------------- */
function agendar(fn, ms) { pararPolling(); timer = setTimeout(fn, ms); }
function pararPolling() { if (timer) { clearTimeout(timer); timer = null; } }


/* ---------------- boot ---------------- */
(async function () {
  try {
    st.cfg = await api("/api/config");
    st.modelos = await api("/api/presets");
    await verCanais();
    if (!st.cfg.tem_key) toast("Coloque a chave da API em Ajustes");
  } catch (e) {
    toast("Erro ao abrir: " + e.message);
  }
})();
