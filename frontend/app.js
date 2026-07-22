'use strict';

/* ---------- tiny helpers ---------- */
function E(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null) continue;
      if (k === 'class') el.className = v;
      else if (k === 'html') el.innerHTML = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function shortId(id) { const p = String(id).split(':'); return p[p.length - 1]; }

/* A single access key (sent as X-API-Key) is used for both the token-spending
   tutor endpoints (per-company vendor accounts) and the /admin endpoints. Browse
   read-only with no key; log in via the header control to use 問答/審訂. */
const KEY_STORE = 'apiKey';
function getKey() { return localStorage.getItem(KEY_STORE) || localStorage.getItem('adminApiKey') || ''; }
function setKey(k) {
  if (k) localStorage.setItem(KEY_STORE, k); else localStorage.removeItem(KEY_STORE);
  localStorage.removeItem('adminApiKey'); // migrate/clear the legacy key
}
function authHeaders() {
  const key = getKey();
  return key ? { 'X-API-Key': key } : {};
}

/* Errors use the standardized body {error:{code,message}}; surface code + message. */
async function apiError(r) {
  const body = await r.json().catch(() => ({}));
  const formatDetail = (value) => {
    if (Array.isArray(value)) return value.map(formatDetail).filter(Boolean).join('\n');
    if (value && typeof value === 'object') {
      const item = value;
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : '';
      if (field === 'chunk_size' && item.type === 'greater_than_equal') {
        return '切塊大小至少需要 100 個字元。';
      }
      if (String(item.msg || '').includes('chunk_overlap must be smaller than chunk_size')) {
        return '重疊大小必須小於切塊大小。';
      }
      const location = field ? `${field}：` : '';
      if (item.msg) return location + item.msg;
      try { return JSON.stringify(item); } catch { return '輸入資料格式不正確'; }
    }
    return value == null ? '' : String(value);
  };
  const rawDetail = (body.error && body.error.message) || body.detail;
  const detail = formatDetail(rawDetail) || ('HTTP ' + r.status);
  const err = new Error(detail);
  err.code = (body.error && body.error.code) || null;
  err.status = r.status;
  return err;
}

const api = {
  async get(path) {
    const r = await fetch(path, { headers: authHeaders() });
    if (!r.ok) throw await apiError(r);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw await apiError(r);
    return r.json();
  },
};

/* Minimal login control mounted into the header (.hd-right). */
function renderLoginControl() {
  const host = document.querySelector('.hd-right');
  if (!host) return;
  const existing = document.getElementById('loginbox');
  if (existing) existing.remove();
  const box = E('div', { id: 'loginbox', class: 'loginbox' });
  const key = getKey();
  if (key) {
    box.append(
      E('span', { class: 'login-tag', title: '已登入' }, '已登入 · ' + key.slice(0, 4) + '…'),
      E('button', { class: 'login-btn', onclick: () => { setKey(''); renderLoginControl(); } }, '登出'),
    );
  } else {
    const input = E('input', { class: 'login-input', type: 'password', placeholder: '公司存取金鑰' });
    const submit = () => { const v = input.value.trim(); if (v) { setKey(v); renderLoginControl(); } };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    box.append(input, E('button', { class: 'login-btn', onclick: submit }, '登入'));
  }
  host.prepend(box);
}
window.addEventListener('DOMContentLoaded', renderLoginControl);

/* node type -> palette colour (square marker) */
const TYPE_COLOR = {
  Hormone: '#A65A35', Structure: '#6B5640', Receptor: '#8A7D67',
  RegulatoryEffect: '#7E8060', PhysiologicalVariable: '#B5894A',
  Interaction: '#9C6B4A', FeedbackLoop: '#5A5040', System: '#211C16',
  Concept: '#C9B79A', Molecule: '#7E8060', Enzyme: '#7E8060',
};
const typeColor = (t) => TYPE_COLOR[t] || '#8A7D67';

/* ---------- shell / router ---------- */
const VIEWS = [
  { id: 'chat', label: '問答', render: renderChat },
  { id: 'graph', label: '圖譜', render: renderGraph },
  { id: 'library', label: '典藏', render: renderLibrary },
  { id: 'ingest', label: '解析', render: renderIngest },
  { id: 'curation', label: '審訂', render: renderCuration },
  { id: 'eval', label: '評估', render: renderEval },
];

function currentViewId() {
  const id = location.hash.replace('#', '');
  return VIEWS.some((v) => v.id === id) ? id : 'chat';
}

function renderTabs() {
  const tabs = document.getElementById('tabs');
  clear(tabs);
  const active = currentViewId();
  for (const v of VIEWS) {
    tabs.append(E('button', {
      class: 'tab' + (v.id === active ? ' active' : ''),
      onclick: () => { location.hash = v.id; },
    }, v.label));
  }
}

async function route() {
  renderTabs();
  const view = document.getElementById('view');
  clear(view);
  const v = VIEWS.find((x) => x.id === currentViewId());
  view.append(E('div', { class: 'loading' }, '載入中…'));
  try {
    await v.render(view);
  } catch (err) {
    clear(view);
    view.append(E('div', { class: 'notice err' }, '錯誤：' + err.message));
  }
}
window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', route);

/* ============================================================
   CHAT
   ============================================================ */
const SESS_KEY = 'honzo_sessions';
function loadSessions() { try { return JSON.parse(localStorage.getItem(SESS_KEY)) || []; } catch { return []; } }
function saveSessions(s) { localStorage.setItem(SESS_KEY, JSON.stringify(s)); }

const SUGGESTIONS = [
  '胰島素如何降低血糖?',
  'ADH 如何調節血液滲透壓?',
  'PTH 與抑鈣素如何拮抗調節血鈣?',
  '分娩時的正回饋迴路如何運作?',
];

async function renderChat(host) {
  clear(host);
  let sessions = loadSessions();
  let currentId = sessions[0] ? sessions[0].id : null;

  const wrap = E('div', { class: 'chat' });
  const main = E('div', { class: 'chat-main' });
  const panel = E('div', { class: 'sessions' });
  wrap.append(main, panel);
  host.append(wrap);

  function current() { return sessions.find((s) => s.id === currentId); }

  function newSession() {
    const s = { id: 'sess-' + Date.now(), title: '新對話', messages: [] };
    sessions.unshift(s); currentId = s.id; saveSessions(sessions); paintAll();
  }

  async function ask(question) {
    if (!question.trim()) return;
    if (!current()) newSession();
    const sess = current();
    sess.messages.push({ role: 'user', text: question });
    if (sess.title === '新對話') sess.title = question.slice(0, 18);
    saveSessions(sessions); paintAll();
    const thinking = { role: 'ai', text: '…檢索中', pending: true };
    sess.messages.push(thinking); paintMain();
    try {
      const res = await api.post('/query', { question, top_k: 5, graph_depth: 1, include_debug: true });
      Object.assign(thinking, {
        text: res.answer, pending: false,
        citations: res.citations, nodes: res.supporting_nodes,
        rels: res.relationships_used, debug: res.retrieval_debug,
      });
    } catch (err) {
      // Standardized auth/quota errors carry a code; their message is already a
      // reader-facing prompt. login_required also nudges toward the header login.
      let text;
      if (err.code === 'login_required') text = err.message + '（請點右上角登入)';
      else if (err.code) text = err.message; // quota_exceeded / account_expired / account_disabled
      else text = '查詢失敗：' + err.message;
      Object.assign(thinking, { text, pending: false });
    }
    saveSessions(sessions); paintMain();
  }

  function bubbleAI(m) {
    const box = E('div', { class: 'bubble-ai' }, E('p', { text: m.text }));
    if (m.pending) return E('div', { class: 'bubble-ai-row' }, E('div', { class: 'ai-ico' }, '✦'), box);

    const nodesById = {};
    (m.nodes || []).forEach((n) => { nodesById[n.id] = n.label; });

    if (m.citations && m.citations.length) {
      box.append(E('div', { class: 'cite-head' }, `引用來源 · ${m.citations.length}`));
      const chips = E('div', { class: 'chips' });
      m.citations.forEach((c, i) => chips.append(E('span', { class: 'chip', title: c.snippet },
        E('span', { class: 'n' }, String(i + 1).padStart(2, '0')),
        E('span', { class: 'lbl' }, shortId(c.chunk_id)))));
      box.append(chips);
    }
    if (m.nodes && m.nodes.length) {
      box.append(E('div', { class: 'cite-head' }, `支持節點 · ${m.nodes.length}`));
      const chips = E('div', { class: 'chips' });
      m.nodes.slice(0, 12).forEach((n) => chips.append(E('span', { class: 'chip' },
        E('span', { class: 'tdot', style: `background:${typeColor(n.type)}` }),
        E('span', { class: 'lbl' }, n.label))));
      if (m.nodes.length > 12) chips.append(E('span', { class: 'chip muted' }, `+${m.nodes.length - 12}`));
      box.append(chips);
    }
    if (m.rels && m.rels.length) {
      box.append(E('div', { class: 'cite-head' }, `關係 · ${m.rels.length}`));
      const chips = E('div', { class: 'chips' });
      m.rels.slice(0, 8).forEach((r) => chips.append(E('span', { class: 'chip rel' },
        (nodesById[r.source] || shortId(r.source)), E('span', { class: 'arw' }, ` —${r.relation}→ `),
        (nodesById[r.target] || shortId(r.target)))));
      if (m.rels.length > 8) chips.append(E('span', { class: 'chip rel muted' }, `+${m.rels.length - 8}`));
      box.append(chips);
    }
    return E('div', { class: 'bubble-ai-row' }, E('div', { class: 'ai-ico' }, '✦'), box);
  }

  function paintMain() {
    clear(main);
    const sess = current();
    if (!sess || !sess.messages.length) {
      const sug = E('div', { class: 'suggest' });
      SUGGESTIONS.forEach((q) => sug.append(E('button', { onclick: () => ask(q) }, q)));
      main.append(E('div', { class: 'empty' },
        E('div', { class: 'ai-ico' }, '✦'),
        E('h2', {}, '今天想了解什麼?'),
        E('div', { class: 'muted', style: 'font-size:13px' }, '答案僅依典藏的激素調控知識生成，並標注引用來源'),
        sug));
    } else {
      main.append(E('div', { class: 'chat-thread-hd' },
        E('div', { class: 'ai-ico' }, '✦'),
        E('div', {}, E('div', { class: 'serif', style: 'font-size:18px;font-weight:700' }, sess.title),
          E('div', { class: 'muted', style: 'font-size:11.5px;margin-top:4px' }, '僅依典藏知識作答 · 內分泌調控域')),
        E('span', { class: 'badge', style: 'margin-left:auto' }, 'HYBRID · VECTOR + GRAPH')));
      const msgs = E('div', { class: 'chat-msgs' });
      sess.messages.forEach((m) => msgs.append(m.role === 'user'
        ? E('div', { class: 'bubble-user' }, m.text) : bubbleAI(m)));
      main.append(msgs);
      msgs.scrollTop = msgs.scrollHeight;
    }
    // composer
    const ta = E('textarea', { placeholder: '接著問⋯⋯', rows: '1' });
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); const q = ta.value; ta.value = ''; ask(q); }
    });
    main.append(E('div', { class: 'composer' },
      E('div', { class: 'composer-row' }, ta,
        E('button', { class: 'btn', onclick: () => { const q = ta.value; ta.value = ''; ask(q); } }, '發送')),
      E('div', { class: 'composer-hint' }, '答案僅依典藏知識生成，並標注引用來源 · Enter 送出 · Shift+Enter 換行')));
    if (current() && current().messages.length) requestAnimationFrame(() => { const m = main.querySelector('.chat-msgs'); if (m) m.scrollTop = m.scrollHeight; });
  }

  function paintPanel() {
    clear(panel);
    panel.append(E('div', { class: 'sessions-hd' },
      E('span', { class: 'eyebrow' }, 'SESSIONS · 對話')));
    panel.append(E('div', { style: 'padding:14px 16px 8px' },
      E('button', { class: 'btn-ghost', style: 'width:100%;padding:10px', onclick: newSession }, '＋ 新對話')));
    const list = E('div', { class: 'sess-list' });
    if (!sessions.length) list.append(E('div', { class: 'muted', style: 'font-size:12px;padding:8px' }, '尚無對話'));
    sessions.forEach((s) => list.append(E('div', {
      class: 'sess' + (s.id === currentId ? ' active' : ''),
      onclick: () => { currentId = s.id; paintAll(); },
    }, E('div', { class: 't' }, s.title),
       E('div', { class: 'm' }, `${s.messages.filter((m) => m.role === 'user').length} 則`))));
    panel.append(list);
    panel.append(E('div', { class: 'sessions-ft' },
      E('span', {}, `${sessions.length} 個對話`),
      E('span', { class: 'clear', onclick: () => { sessions = []; currentId = null; saveSessions(sessions); paintAll(); } }, '清除全部')));
  }

  function paintAll() { paintMain(); paintPanel(); }
  paintAll();

  // deep link: /app/?ask=... #chat auto-submits a question
  const urlAsk = new URLSearchParams(location.search).get('ask');
  if (urlAsk) ask(urlAsk);
}

/* ============================================================
   GRAPH
   ============================================================ */
function forceLayout(nodes, edges, w, h) {
  const N = nodes.length || 1;
  const pos = {};
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / N;
    pos[n.id] = { x: w / 2 + Math.cos(a) * Math.min(w, h) * 0.32, y: h / 2 + Math.sin(a) * Math.min(w, h) * 0.32, vx: 0, vy: 0 };
  });
  const links = edges.map((e) => [e.source, e.target]).filter(([s, t]) => pos[s] && pos[t]);
  for (let it = 0; it < 320; it++) {
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = pos[nodes[i].id], b = pos[nodes[j].id];
      let dx = a.x - b.x, dy = a.y - b.y; const d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2);
      const rep = 8600 / d2, fx = (dx / d) * rep, fy = (dy / d) * rep;
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
    }
    links.forEach(([s, t]) => {
      const a = pos[s], b = pos[t]; let dx = b.x - a.x, dy = b.y - a.y; const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const k = (d - 165) * 0.02, fx = (dx / d) * k, fy = (dy / d) * k;
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
    });
    nodes.forEach((n) => {
      const p = pos[n.id];
      p.vx += (w / 2 - p.x) * 0.0022; p.vy += (h / 2 - p.y) * 0.0022;
      p.x += p.vx * 0.82; p.y += p.vy * 0.82; p.vx *= 0.82; p.vy *= 0.82;
    });
  }
  const pad = 60;
  nodes.forEach((n) => { const p = pos[n.id]; p.x = Math.max(pad, Math.min(w - pad, p.x)); p.y = Math.max(pad, Math.min(h - pad, p.y)); });
  return pos;
}

let graphSeedId = null; // set by Library rows to auto-draw a node's subgraph

const SVGNS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs) { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; }

async function renderGraph(host) {
  clear(host);
  const topics = (await api.get('/library')).groups;

  const topicSel = E('select', {}, E('option', { value: '' }, '— 選擇主題 —'),
    ...topics.map((g) => E('option', { value: g.topic }, `${g.label} (${g.count})`)));
  const nodeInput = E('input', { placeholder: '或輸入節點 id，如 hormone:insulin', style: 'min-width:280px' });
  const depthSel = E('select', {}, E('option', { value: '1' }, '深度 1'), E('option', { value: '2' }, '深度 2'));
  const drawBtn = E('button', { class: 'btn', onclick: draw }, '描繪子圖');

  host.append(E('div', { class: 'controls' }, E('span', { class: 'eyebrow' }, '概念圖譜'), topicSel, nodeInput, depthSel, drawBtn));
  const wrap = E('div', { class: 'graph-wrap' });
  const canvas = E('div', { class: 'graph-canvas' });
  const side = E('div', { class: 'graph-side' });
  wrap.append(canvas, side); host.append(wrap);

  side.append(E('div', { class: 'eyebrow' }, '說明'),
    E('div', { class: 'muted', style: 'font-size:12px;margin-top:10px;line-height:1.7' },
      '選一個主題或輸入節點 id，以受控查詢（/concept-map、/neighbors）從 Neo4j 取回 approved 子圖。點節點看詳情。'));

  // seed from a Library click, or a deep link like /app/?node=hormone:insulin#graph
  const urlSeed = new URLSearchParams(location.search).get('node');
  const seed = graphSeedId || urlSeed;
  if (seed) { nodeInput.value = seed; graphSeedId = null; draw(); }

  function renderSideDetail(n) {
    clear(side);
    side.append(E('div', { class: 'eyebrow' }, 'NODE · 節點'));
    side.append(E('div', { class: 'serif', style: 'font-size:19px;font-weight:700;margin-top:10px' }, n.label));
    side.append(E('div', { class: 'mono', style: 'font-size:10px;color:var(--muted);margin-top:4px' }, n.id));
    const load = async () => {
      try {
        const d = await api.get('/nodes/' + encodeURIComponent(n.id));
        side.append(E('div', { style: 'display:flex;align-items:center;gap:7px;margin-top:12px;font-size:12px' },
          E('span', { class: 'tdot', style: `background:${typeColor(d.type)}` }), d.type));
        if (d.description) side.append(E('div', { style: 'font-size:13px;line-height:1.7;margin-top:10px' }, d.description));
        const keys = Object.keys(d.properties || {});
        if (keys.length) side.append(E('div', { class: 'mono', style: 'font-size:11px;color:var(--text-2);margin-top:10px' },
          keys.map((k) => `${k}: ${d.properties[k]}`).join('\n')));
      } catch (err) { side.append(E('div', { class: 'notice err' }, err.message)); }
    };
    load();
  }

  async function draw() {
    clear(canvas);
    canvas.append(E('div', { class: 'loading' }, '查詢子圖…'));
    let data;
    try {
      const nid = nodeInput.value.trim();
      const depth = Number(depthSel.value);
      if (nid) {
        const r = await api.get(`/neighbors/${encodeURIComponent(nid)}?depth=${depth}`);
        data = { nodes: [r.center_node, ...r.nodes], edges: r.edges };
      } else if (topicSel.value) {
        data = await api.post('/concept-map', { topic: topicSel.value, depth });
      } else { clear(canvas); canvas.append(E('div', { class: 'loading' }, '請先選主題或輸入節點 id。')); return; }
    } catch (err) { clear(canvas); canvas.append(E('div', { class: 'notice err' }, err.message)); return; }

    clear(canvas);
    const W = 960, H = 640;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet' });
    const pos = forceLayout(data.nodes, data.edges, W, H);
    const byId = {}; data.nodes.forEach((n) => { byId[n.id] = n; });
    data.edges.forEach((e) => {
      const a = pos[e.source], b = pos[e.target]; if (!a || !b) return;
      svg.append(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#DED5C2', 'stroke-width': '1' }));
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      const lbl = svgEl('text', { x: mx, y: my, class: 'gedge-label', 'text-anchor': 'middle' }); lbl.textContent = e.relation;
      svg.append(lbl);
    });
    data.nodes.forEach((n) => {
      const p = pos[n.id]; const c = typeColor(n.type);
      const g = svgEl('g', { style: 'cursor:pointer' });
      g.addEventListener('click', () => renderSideDetail(n));
      g.append(svgEl('rect', { x: p.x - 6, y: p.y - 6, width: 12, height: 12, fill: c }));
      const t = svgEl('text', { x: p.x + 10, y: p.y + 4, class: 'gnode-label' });
      t.textContent = n.label.length > 20 ? n.label.slice(0, 19) + '…' : n.label;
      const tt = svgEl('title', {}); tt.textContent = `${n.label} · ${n.type}`; t.append(tt);
      g.append(t); svg.append(g);
    });
    canvas.append(svg);

    // legend
    const types = [...new Set(data.nodes.map((n) => n.type))];
    const legend = E('div', { class: 'legend', style: 'position:absolute;left:16px;bottom:14px;background:rgba(244,239,228,.9);padding:8px 12px' });
    types.forEach((t) => legend.append(E('span', { class: 'li' },
      E('span', { class: 'tdot', style: `background:${typeColor(t)}` }), t)));
    canvas.append(legend);
    clear(side); side.append(E('div', { class: 'eyebrow' }, 'SUBGRAPH · 子圖'),
      E('div', { class: 'mono', style: 'font-size:12px;margin-top:10px;color:var(--text-2)' },
        `${data.nodes.length} 節點 · ${data.edges.length} 關係`),
      E('div', { class: 'muted', style: 'font-size:12px;margin-top:10px' }, '點任一節點查看詳情。'));
  }
}

/* ============================================================
   LIBRARY
   ============================================================ */
async function renderLibrary(host) {
  clear(host);
  const data = await api.get('/library');
  host.append(E('div', { class: 'page-head' },
    E('div', { class: 'eyebrow' }, 'LIBRARY · 典藏'),
    E('div', { class: 'page-title', style: 'margin-top:8px' }, '典藏'),
    E('div', { class: 'page-sub' }, `依主題分組的知識節點 · ${data.total_nodes} 節點 · ${data.total_edges} 關係 · ${data.total_topics} 主題`)));

  const groups = E('div', { class: 'lib-groups scroll' });
  data.groups.forEach((g) => {
    groups.append(E('div', { class: 'lib-group-hd' },
      E('span', { class: 'name' }, g.label),
      E('span', { class: 'en' }, g.topic.toUpperCase()),
      E('span', { class: 'cnt' }, `${g.count} 節點`)));
    g.nodes.forEach((n, i) => groups.append(E('div', {
      class: 'lib-row',
      onclick: () => { graphSeedId = n.id; location.hash = 'graph'; },
    }, E('span', { class: 'idx' }, String(i + 1).padStart(2, '0')),
       E('span', { class: 'name' }, n.label),
       E('span', { class: 'type' }, E('span', { class: 'tdot', style: `background:${typeColor(n.type)}` }), n.type),
       E('span', { class: 'id' }, n.id))));
  });
  host.append(groups);
}

/* ============================================================
   CURATION
   ============================================================ */
const NODE_TYPES = ['Hormone', 'Structure', 'Receptor', 'RegulatoryEffect', 'PhysiologicalVariable', 'Interaction', 'FeedbackLoop', 'Concept', 'System', 'Disease', 'Misconception'];
const REL_TYPES = ['SECRETES', 'TARGETS', 'BINDS_TO', 'HAS_EFFECT', 'ON_VARIABLE', 'INCREASES', 'DECREASES', 'REGULATES_SECRETION_OF', 'PARTICIPATES_IN', 'USES_EFFECT', 'PREREQUISITE_OF', 'CAUSES', 'COMMONLY_CONFUSED_WITH'];

async function renderCuration(host) {
  clear(host);
  host.append(E('div', { class: 'page-head', style: 'padding-bottom:0' },
    E('div', { class: 'eyebrow' }, 'CURATION · 人工審訂'),
    E('div', { class: 'page-title', style: 'margin-top:8px;font-size:30px' }, '審訂佇列'),
    E('div', { class: 'page-sub' }, 'LLM 或人工提出的候選節點/關係先進 proposed 狀態，經審核才寫入 approved graph。')));

  const wrap = E('div', { class: 'cur-wrap' });
  const left = E('div', { class: 'cur-col' });
  const right = E('div', { class: 'cur-col' });
  wrap.append(left, right); host.append(wrap);

  /* ---- propose form ---- */
  let itemType = 'node';
  const notice = E('div');
  const formHost = E('div');
  left.append(E('div', { class: 'eyebrow', style: 'margin-bottom:14px' }, '提出候選'));
  const seg = E('div', { class: 'seg' },
    E('button', { class: 'on', onclick: (e) => { itemType = 'node'; toggleSeg(e.target); paintForm(); } }, '節點 NODE'),
    E('button', { onclick: (e) => { itemType = 'edge'; toggleSeg(e.target); paintForm(); } }, '關係 EDGE'));
  function toggleSeg(btn) { seg.querySelectorAll('button').forEach((b) => b.classList.remove('on')); btn.classList.add('on'); }
  left.append(seg, notice, formHost);

  function field(label, code, input) {
    return E('div', { class: 'field' }, E('label', {}, label, E('span', { class: 'code' }, code)), input);
  }
  function paintForm() {
    clear(formHost);
    if (itemType === 'node') {
      const id = E('input', { placeholder: 'hormone:example' });
      const type = E('select', {}, ...NODE_TYPES.map((t) => E('option', {}, t)));
      const label = E('input', { placeholder: 'Example hormone' });
      const desc = E('textarea', { placeholder: '節點說明…' });
      const reason = E('input', { placeholder: '為何提出' });
      formHost.append(field('id', 'ID', id), field('類型', 'TYPE', type), field('名稱', 'LABEL', label),
        field('說明', 'DESC', desc), field('理由', 'REASON', reason),
        E('button', { class: 'btn', onclick: () => submit({ item_type: 'node', action: 'create', reason: reason.value, payload: { id: id.value.trim(), type: type.value, label: label.value.trim(), description: desc.value.trim() } }) }, '提出候選'));
    } else {
      const id = E('input', { placeholder: 'edge:example' });
      const type = E('select', {}, ...REL_TYPES.map((t) => E('option', {}, t)));
      const source = E('input', { placeholder: 'source node id' });
      const target = E('input', { placeholder: 'target node id' });
      const reason = E('input', { placeholder: '為何提出' });
      formHost.append(field('id', 'ID', id), field('關係', 'TYPE', type), field('起點', 'SOURCE', source),
        field('終點', 'TARGET', target), field('理由', 'REASON', reason),
        E('button', { class: 'btn', onclick: () => submit({ item_type: 'edge', action: 'create', reason: reason.value, payload: { id: id.value.trim(), type: type.value, source: source.value.trim(), target: target.value.trim() } }) }, '提出候選'));
    }
  }
  async function submit(body) {
    clear(notice);
    if (!body.payload.id) { notice.append(E('div', { class: 'notice err' }, 'id 為必填')); return; }
    try {
      await api.post('/admin/curation/items', body);
      notice.append(E('div', { class: 'notice ok' }, '已提出，狀態 proposed。')); paintForm(); loadQueue();
    } catch (err) { notice.append(E('div', { class: 'notice err' }, err.message)); }
  }
  paintForm();

  /* ---- review queue ---- */
  right.append(E('div', { class: 'eyebrow', style: 'margin-bottom:14px' }, '待審佇列 · PROPOSED'));
  const queue = E('div');
  right.append(queue);

  async function loadQueue() {
    clear(queue); queue.append(E('div', { class: 'loading', style: 'padding:8px' }, '載入…'));
    let items;
    try { items = await api.get('/admin/curation/items?status=proposed'); }
    catch (err) { clear(queue); queue.append(E('div', { class: 'notice err' }, err.message)); return; }
    clear(queue);
    if (!items.length) { queue.append(E('div', { class: 'muted', style: 'font-size:12px' }, '目前沒有待審項目。可用左側表單提出一個。')); return; }
    items.forEach((it) => {
      const p = it.payload;
      const summary = it.item_type === 'node'
        ? `${p.type}  ${p.label || ''}\n${p.id}`
        : `${p.source}  —${p.type}→  ${p.target}\n${p.id}`;

      const sc = it.schema_check;
      let schemaBadge = null;
      if (sc) {
        const allPassed = sc.passed;
        const failedChecks = (sc.checks || []).filter(c => !c.passed);
        const tip = allPassed
          ? 'Schema 自動檢查通過'
          : '⚠ Schema 問題：' + failedChecks.map(c => c.detail || c.name).join('、');
        schemaBadge = E('span', {
          class: allPassed ? 'schema-badge schema-ok' : 'schema-badge schema-warn',
          title: tip,
        }, allPassed ? '✓ Schema' : '⚠ Schema');
      }

      const card = E('div', { class: 'qitem' },
        E('div', { class: 'h' }, E('span', { class: 'tag tag-proposed' }, it.item_type.toUpperCase()),
          E('span', { class: 'mono', style: 'font-size:10px;color:var(--muted)' }, it.action),
          schemaBadge),
        E('div', { class: 'pay' }, summary),
        it.reason ? E('div', { class: 'muted', style: 'font-size:11px' }, '理由：' + it.reason) : null);
      const acts = E('div', { class: 'acts' },
        E('button', { class: 'btn', onclick: () => decide(it.item_id, 'approve') }, '批准'),
        E('button', { class: 'btn-ghost', onclick: () => decide(it.item_id, 'reject') }, '拒絕'));
      card.append(acts); queue.append(card);
    });
  }
  async function decide(itemId, action) {
    try { await api.post(`/admin/curation/items/${encodeURIComponent(itemId)}/${action}`, { reviewer: 'demo', reason: action === 'approve' ? '審核通過' : '不需要' }); loadQueue(); }
    catch (err) { clear(notice); notice.append(E('div', { class: 'notice err' }, err.message)); }
  }
  loadQueue();
}

/* ============================================================
   INGEST / 解析 — document extraction (interface public, run locked)
   ============================================================ */
const OWNER_STORE = 'ingestOwnerToken';
// sessionStorage, not localStorage: the owner token is a long-lived secret, so
// scope it to the tab session rather than persisting it at rest across visits.
const getOwner = () => sessionStorage.getItem(OWNER_STORE) || '';
const setOwner = (t) => { if (t) sessionStorage.setItem(OWNER_STORE, t); else sessionStorage.removeItem(OWNER_STORE); };

const STRAT_LABELS = {
  fixed: '固定長度', recursive: '遞迴切塊', markdown_header: '標題切塊',
};

/* run needs an extra owner-token header on top of the admin key */
async function ingestRun(body, ownerToken) {
  const r = await fetch('/admin/ingest/run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(ownerToken ? { 'X-Ingest-Owner-Token': ownerToken } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw await apiError(r);
  return r.json();
}

async function renderIngest(host) {
  clear(host);
  const opts = await api.get('/admin/ingest/options');

  const state = {
    source: opts.sources[0] ? opts.sources[0].key : '',
    strategy: opts.default_strategy || 'recursive',
    params: { chunk_size: 500, chunk_overlap: 80, max_section_size: 800 },
  };

  host.append(E('div', { class: 'page-head' },
    E('div', { class: 'eyebrow' }, 'EXTRACTION · 解析流程'),
    E('div', { class: 'page-title', style: 'margin-top:8px;font-size:30px' }, '文件解析與收錄'),
    E('div', { class: 'page-sub' },
      '將原始章節切塊、逐塊送 LLM 抽取候選節點/關係,寫入審訂佇列(proposed)。' +
      '預覽不消耗 token;實際注入僅限資料庫擁有者。')));

  const wrap = E('div', { class: 'ing-wrap' });
  host.append(wrap);

  const steps = E('div', { class: 'ing-steps' });
  const results = E('div', { class: 'ing-results' });

  // ---- step 1: source ----
  const sourceSel = E('select', { class: 'ing-select', onchange: (e) => { state.source = e.target.value; } },
    ...opts.sources.map((s) => E('option', { value: s.key }, `${s.filename}  ·  ${s.scope}`)));
  if (!opts.sources.length) sourceSel.append(E('option', { value: '' }, '（尚無可匯入的章節檔）'));

  // ---- step 2/3: strategy + params (repainted together) ----
  const stratRow = E('div', { class: 'pill-row' });
  const paramsHost = E('div');

  function paintStrategy() {
    clear(stratRow);
    opts.strategies.forEach((s) => stratRow.append(E('button', {
      class: 'pill' + (s.name === state.strategy ? ' on cha' : ''),
      title: s.description,
      onclick: () => { state.strategy = s.name; paintStrategy(); paintParams(); updateParamValidity(); },
    }, STRAT_LABELS[s.name] || s.name)));
  }
  function numParam(key, label) {
    const limits = key === 'chunk_size'
      ? { min: '100', max: '5000' }
      : key === 'chunk_overlap'
        ? { min: '0', max: '2000' }
        : { min: '100', max: '8000' };
    return E('div', { class: 'ing-param' },
      E('label', {}, label),
      E('input', {
        type: 'number', value: String(state.params[key]), ...limits,
        oninput: (e) => { state.params[key] = Number(e.target.value); updateParamValidity(); },
      }));
  }
  const paramError = E('div', { class: 'notice err', style: 'display:none;margin-top:10px' });

  function paramValidationMessage() {
    if (state.strategy === 'markdown_header') {
      return state.params.max_section_size < 100 ? '每個標題區塊大小至少需要 100 個字元。' : '';
    }
    if (!Number.isFinite(state.params.chunk_size) || state.params.chunk_size < 100) {
      return '切塊大小至少需要 100 個字元。';
    }
    if (!Number.isFinite(state.params.chunk_overlap) || state.params.chunk_overlap < 0) {
      return '重疊大小不可小於 0。';
    }
    if (state.params.chunk_overlap >= state.params.chunk_size) {
      return '重疊大小必須小於切塊大小。';
    }
    return '';
  }

  function updateParamValidity() {
    const message = paramValidationMessage();
    paramError.textContent = message;
    paramError.style.display = message ? '' : 'none';
    previewBtn.disabled = Boolean(message);
    runBtn.disabled = Boolean(message);
    return !message;
  }

  function paintParams() {
    clear(paramsHost);
    const box = E('div', { class: 'ing-params' });
    if (state.strategy === 'markdown_header') {
      box.append(numParam('max_section_size', 'MAX_SECTION_SIZE'));
    } else {
      box.append(numParam('chunk_size', 'CHUNK_SIZE'), numParam('chunk_overlap', 'CHUNK_OVERLAP'));
    }
    paramsHost.append(box, paramError);
  }
  paintStrategy();
  paintParams();

  // ---- step 4: profiles (informational) ----
  const profileRow = E('div', { class: 'pill-row' });
  if (opts.profiles.length) {
    opts.profiles.forEach((p) => profileRow.append(E('span', { class: 'pill' }, p)));
  } else {
    profileRow.append(E('span', { class: 'muted', style: 'font-size:12px' }, '（本機無私有 profile;將使用通用 base 模板）'));
  }

  function step(n, code, title, hint, body, accent) {
    return E('div', { class: 'ing-step' + (accent ? ' accent' : '') },
      E('div', { class: 'ing-rail' }, E('div', { class: 'ing-num' }, String(n)),
        n < 4 ? E('div', { class: 'ing-line' }) : null),
      E('div', { class: 'ing-body' },
        E('div', { class: 'ing-h' }, E('span', { class: 't' }, title), E('span', { class: 'c' }, code)),
        hint ? E('div', { class: 'ing-hint' }, hint) : null,
        body));
  }

  steps.append(
    step(1, 'SOURCE', '來源文件', '選擇要解析的章節檔(公開示範或本機私有 IP)。', sourceSel, true),
    step(2, 'CHUNK', '切塊策略', '不同切法影響每塊的語意完整度與抽取品質。', stratRow),
    step(3, 'PARAMS', '切塊參數', null, paramsHost),
    step(4, 'PROFILE', '領域補充 Profile',
      '由文件 front-matter 的 extraction_profile 指定,疊加在 base 抽取 prompt 之上。', profileRow, true),
  );
  wrap.append(steps);

  // ---- action bar ----
  const notice = E('div');
  const ownerInput = E('input', {
    class: 'owner-input', type: 'password', placeholder: '擁有者權杖', value: getOwner(),
  });
  const previewBtn = E('button', { class: 'btn-ghost', onclick: doPreview }, '預覽 · 不消耗 token');
  const runBtn = E('button', { class: 'lockbtn', onclick: doRun },
    E('span', { class: 'lk' }, '🔒'), '執行注入');

  wrap.append(E('div', { class: 'ing-actionbar' },
    E('div', { class: 'ing-note' },
      '預覽只做切塊與組 prompt,零 token、零寫入。執行注入會呼叫 LLM 並寫入 proposed 知識,' +
      '需正確的擁有者權杖(X-Ingest-Owner-Token)——預設對所有人上鎖。'),
    E('div', { class: 'ing-actions' }, previewBtn, ownerInput, runBtn)));
  wrap.append(notice, results);
  updateParamValidity();

  function buildBody() {
    const cp = state.strategy === 'markdown_header'
      ? { max_section_size: state.params.max_section_size }
      : { chunk_size: state.params.chunk_size, chunk_overlap: state.params.chunk_overlap };
    return { source: state.source, strategy: state.strategy, chunk_params: cp };
  }

  function setBusy(busy, which) {
    previewBtn.disabled = busy; runBtn.disabled = busy;
    if (busy) { clear(notice); results.replaceChildren(E('div', { class: 'loading' }, which === 'run' ? '注入中…' : '解析預覽中…')); }
  }

  async function doPreview() {
    if (!state.source || !updateParamValidity()) return;
    setBusy(true, 'preview');
    try { renderPreview(results, await api.post('/admin/ingest/preview', buildBody())); }
    catch (err) { clear(results); notice.replaceChildren(E('div', { class: 'notice err' }, err.message)); }
    finally { updateParamValidity(); }
  }

  async function doRun() {
    if (!state.source || !updateParamValidity()) return;
    const token = ownerInput.value.trim();
    setOwner(token);
    setBusy(true, 'run');
    try { renderRunResult(results, await ingestRun(buildBody(), token)); clear(notice); }
    catch (err) {
      clear(results);
      const msg = err.code === 'ingest_locked'
        ? '🔒 ' + err.message
        : err.code === 'llm_not_configured' ? err.message : ('注入失敗：' + err.message);
      notice.replaceChildren(E('div', { class: 'notice err' }, msg));
    }
    finally { updateParamValidity(); }
  }
}

function renderPreview(host, rep) {
  clear(host);
  host.append(E('div', { class: 'cite-head', style: 'margin:0 0 4px' },
    E('span', { class: 'badge' }, `PREVIEW · ${rep.chunks.length} CHUNKS · 0 TOKEN`)));

  // system prompt (collapsible)
  const sysBlock = E('pre', { class: 'prompt-block', style: 'display:none' }, rep.system_prompt || '');
  const sysToggle = E('button', { class: 'prompt-toggle', style: 'padding-left:0' }, '＋ 系統 PROMPT(含 profile 疊加)');
  sysToggle.addEventListener('click', () => {
    const open = sysBlock.style.display === 'none';
    sysBlock.style.display = open ? 'block' : 'none';
    sysToggle.textContent = (open ? '－' : '＋') + ' 系統 PROMPT(含 profile 疊加)';
  });
  host.append(sysToggle, sysBlock);

  rep.chunks.forEach((ch, i) => {
    const promptBlock = E('pre', { class: 'prompt-block', style: 'display:none' }, ch.user_prompt || '');
    const toggle = E('button', { class: 'prompt-toggle' }, '＋ 檢視送給 LLM 的 user prompt');
    toggle.addEventListener('click', () => {
      const open = promptBlock.style.display === 'none';
      promptBlock.style.display = open ? 'block' : 'none';
      toggle.textContent = (open ? '－' : '＋') + ' 檢視送給 LLM 的 user prompt';
    });
    host.append(E('div', { class: 'chunk-card' },
      E('div', { class: 'chunk-head' },
        E('span', { class: 'cid' }, String(i + 1).padStart(2, '0')),
        E('span', { class: 'mono', style: 'font-size:10px;color:var(--muted)' }, ch.chunk_id),
        E('span', { class: 'meta' }, `${(ch.content || '').length} 字`)),
      E('div', { class: 'chunk-text' }, ch.content),
      toggle, promptBlock));
  });
}

function renderRunResult(host, rep) {
  clear(host);
  const s = rep.stats || {};
  const tile = (k, v, cls) => E('div', { class: 'tile ' + (cls || '') },
    E('div', { class: 'k' }, k), E('div', { class: 'v' }, String(v)));
  host.append(E('div', { class: 'tiles' },
    tile('CHUNKS', s.chunks ?? 0),
    tile('候選節點', s.proposed_nodes ?? 0, 'pass'),
    tile('候選關係', s.proposed_edges ?? 0, 'pass'),
    tile('失敗塊', s.failed_chunks ?? 0, s.failed_chunks ? 'fail' : ''),
    tile('TOKENS', s.tokens ?? 0)));

  host.append(E('div', { class: 'notice ok' },
    `已將 ${s.proposed_nodes ?? 0} 個節點、${s.proposed_edges ?? 0} 個關係寫入審訂佇列(proposed)。` +
    '前往「審訂」分頁批准後才會進入 approved 知識圖譜。'));

  rep.chunks.forEach((ch, i) => {
    const ids = E('div', { class: 'pid-chips' });
    (ch.proposed_node_ids || []).forEach((id) => ids.append(E('span', { class: 'pid' }, shortId(id))));
    (ch.proposed_edge_ids || []).forEach((id) => ids.append(E('span', { class: 'pid edge' }, shortId(id))));
    host.append(E('div', { class: 'chunk-card' },
      E('div', { class: 'chunk-head' },
        E('span', { class: 'cid' }, String(i + 1).padStart(2, '0')),
        E('span', { class: 'mono', style: 'font-size:10px;color:var(--muted)' }, ch.chunk_id),
        E('span', { class: 'meta' }, ch.extraction_failed ? '抽取失敗' : `${ch.tokens} tok`)),
      E('div', { class: 'chunk-text' }, ch.content),
      ch.extraction_failed
        ? E('div', { class: 'chunk-fail' }, '⚠ 此塊抽取失敗(已跳過,不影響其他塊)')
        : ids));
  });
}

/* ============================================================
   EVALUATION
   ============================================================ */
async function renderEval(host) {
  clear(host);
  host.append(E('div', { class: 'page-head' },
    E('div', { class: 'eyebrow' }, 'EVALUATION · 評估'),
    E('div', { class: 'page-title', style: 'margin-top:8px;font-size:30px' }, '檢索品質評估'),
    E('div', { class: 'page-sub' }, '對 golden questions 重跑 /query 檢索管線，量測 recall@k、grounded 通過率與延遲。')));

  const rep = await api.get('/admin/evaluation/latest');
  const s = rep.summary;
  const tile = (k, v, sub, cls) => E('div', { class: 'tile ' + (cls || '') },
    E('div', { class: 'k' }, k), E('div', { class: 'v', html: v }), sub ? E('div', { class: 'th' }, sub) : null);

  host.append(E('div', { class: 'tiles' },
    tile('RECALL@' + s.top_k, s.recall_at_k, `門檻 ≥ ${s.thresholds.recall_at_k}`, s.recall_at_k >= s.thresholds.recall_at_k ? 'pass' : 'fail'),
    tile('GROUNDED', s.grounded_pass_rate, `門檻 ≥ ${s.thresholds.grounded_pass_rate}`, s.grounded_pass_rate >= s.thresholds.grounded_pass_rate ? 'pass' : 'fail'),
    tile('P95 LATENCY', s.latency_p95_ms + '<small> ms</small>', `門檻 ≤ ${s.thresholds.latency_p95_ms} ms`, s.latency_p95_ms <= s.thresholds.latency_p95_ms ? 'pass' : 'fail'),
    tile('QUESTIONS', s.num_questions, `模式 ${s.mode}`),
    tile('OVERALL', s.passed ? 'PASS' : 'FAIL', '', s.passed ? 'pass' : 'fail')));

  const maxLat = Math.max(...rep.items.map((i) => i.latency_ms), 1);
  const table = E('table', { class: 'etable' },
    E('thead', {}, E('tr', {}, ...['#', 'recall@k', 'grounded', 'latency', 'passed'].map((h) => E('th', {}, h)))));
  const tb = E('tbody');
  rep.items.forEach((it) => tb.append(E('tr', {},
    E('td', { class: 'n' }, it.question_id),
    E('td', { class: 'n' }, it.recall_at_k),
    E('td', {}, it.grounded_pass ? 'yes' : 'no'),
    E('td', {}, E('div', { style: 'display:flex;align-items:center;gap:8px' },
      E('span', { class: 'n', style: 'width:52px' }, it.latency_ms + 'ms'),
      E('span', { class: 'bar', style: 'flex:1' }, E('span', { style: `width:${(it.latency_ms / maxLat * 100).toFixed(0)}%` })))),
    E('td', {}, it.passed ? '✅' : '❌'))));
  table.append(tb);
  host.append(E('div', { class: 'scroll', style: 'padding:20px 48px 40px' }, table));
}
