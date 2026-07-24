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

/* human-readable zh labels — so curators read biology, not schema codes.
   value/API 一律仍用英文 code;這裡只影響「人要讀 / 要選」的地方。 */
const NODE_TYPE_LABEL = {
  Hormone: '激素', Structure: '構造', Receptor: '受體',
  RegulatoryEffect: '調控效果', PhysiologicalVariable: '生理變數',
  Interaction: '交互作用', FeedbackLoop: '回饋迴路', Concept: '概念',
  System: '系統', Disease: '疾病', Misconception: '常見迷思',
  Molecule: '分子', Enzyme: '酵素', Process: '生理過程', Variable: '生理變數',
};
const REL_TYPE_LABEL = {
  SECRETES: '分泌', TARGETS: '作用於', BINDS_TO: '結合',
  HAS_EFFECT: '產生調控效果', ON_VARIABLE: '作用在', INCREASES: '使其上升',
  DECREASES: '使其下降', REGULATES_SECRETION_OF: '調控分泌',
  PARTICIPATES_IN: '參與', USES_EFFECT: '運用效果', PREREQUISITE_OF: '是其先備',
  CAUSES: '促成', COMMONLY_CONFUSED_WITH: '常被混淆為',
};
const nodeTypeLabel = (t) => NODE_TYPE_LABEL[t] || t;
const phraseRelation = (r) => REL_TYPE_LABEL[r] || r;

/* ---------- shell / router ---------- */
const VIEWS = [
  { id: 'chat', label: '問答', render: renderChat },
  { id: 'graph', label: '圖譜', render: renderGraph },
  { id: 'library', label: '典藏', render: renderLibrary },
  { id: 'ingest', label: '解析', render: renderIngest },
  { id: 'curation', label: '審訂', render: renderCuration },
  { id: 'review', label: '群組審閱', render: renderReview },
  { id: 'expert', label: '審閱', render: renderExpertDemo },
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

/* edge endpoints only carry ids; resolve to human labels for the review cards.
   優先序:佇列同儕候選節點 → approved 圖(GET /nodes/{id}) → 退回短 id。
   查不到必須靜默 fallback,不可讓審核卡片報錯。 */
const nodeLabelCache = {};
async function resolveNodeLabels(ids, localMap) {
  const out = {};
  const missing = [];
  Array.from(new Set(ids.filter(Boolean))).forEach((id) => {
    if (localMap[id]) out[id] = localMap[id];
    else if (nodeLabelCache[id]) out[id] = nodeLabelCache[id];
    else missing.push(id);
  });
  await Promise.all(missing.map(async (id) => {
    try {
      const d = await api.get('/nodes/' + encodeURIComponent(id));
      const lbl = d.label || shortId(id);
      nodeLabelCache[id] = lbl; out[id] = lbl;
    } catch { out[id] = shortId(id); }
  }));
  return out;
}

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
    E('button', { class: 'on', onclick: (e) => { itemType = 'node'; toggleSeg(e.target); paintForm(); } }, '概念'),
    E('button', { onclick: (e) => { itemType = 'edge'; toggleSeg(e.target); paintForm(); } }, '關係'));
  function toggleSeg(btn) { seg.querySelectorAll('button').forEach((b) => b.classList.remove('on')); btn.classList.add('on'); }
  left.append(seg, notice, formHost);

  function field(label, input, hint) {
    return E('div', { class: 'field' },
      E('label', {}, label, hint ? E('span', { class: 'field-hint' }, hint) : null),
      input);
  }
  function paintForm() {
    clear(formHost);
    if (itemType === 'node') {
      const type = E('select', {}, ...NODE_TYPES.map((t) => E('option', { value: t }, nodeTypeLabel(t))));
      const label = E('input', { placeholder: '例如:胰島素' });
      const desc = E('textarea', { placeholder: '用一兩句話說明這個概念…' });
      const id = E('input', { placeholder: 'hormone:insulin' });
      const reason = E('input', { placeholder: '為什麼要新增這個概念?' });
      formHost.append(
        field('類型', type),
        field('名稱', label),
        field('說明', desc),
        field('系統識別碼', id, '小寫英數與冒號,例如 hormone:insulin'),
        field('提出理由', reason),
        E('button', { class: 'btn', onclick: () => submit({ item_type: 'node', action: 'create', reason: reason.value, payload: { id: id.value.trim(), type: type.value, label: label.value.trim(), description: desc.value.trim() } }) }, '提出候選'));
    } else {
      const type = E('select', {}, ...REL_TYPES.map((t) => E('option', { value: t }, phraseRelation(t))));
      const source = E('input', { placeholder: '起點概念的識別碼' });
      const target = E('input', { placeholder: '終點概念的識別碼' });
      const id = E('input', { placeholder: 'edge:insulin_decreases_glucose' });
      const reason = E('input', { placeholder: '為什麼這兩個概念之間有這個關係?' });
      formHost.append(
        field('關係', type),
        field('起點', source, '例如 hormone:insulin'),
        field('終點', target, '例如 physiological_variable:blood_glucose'),
        field('系統識別碼', id, '小寫英數與冒號'),
        field('提出理由', reason),
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
    if (!items.length) { clear(queue); queue.append(E('div', { class: 'muted', style: 'font-size:12px' }, '目前沒有待審項目。可用左側表單提出一個。')); return; }

    // resolve edge endpoint ids → human labels before painting
    const localMap = {};
    items.forEach((it) => { if (it.item_type === 'node' && it.payload && it.payload.id) localMap[it.payload.id] = it.payload.label || it.payload.id; });
    const endpointIds = [];
    items.forEach((it) => { if (it.item_type === 'edge') endpointIds.push(it.payload.source, it.payload.target); });
    const labels = await resolveNodeLabels(endpointIds, localMap);

    clear(queue);
    items.forEach((it) => {
      const p = it.payload;
      // headline reads as biology, not schema: 類型 + 名稱 / 關係句
      let head;
      if (it.item_type === 'node') {
        head = E('div', { class: 'q-head' },
          E('span', { class: 'q-kind', style: `--k:${typeColor(p.type)}` }, nodeTypeLabel(p.type)),
          E('span', { class: 'q-name' }, p.label || labels[p.id] || shortId(p.id)));
      } else {
        head = E('div', { class: 'q-head q-edge' },
          E('span', { class: 'q-name' }, labels[p.source] || shortId(p.source)),
          E('span', { class: 'q-rel' }, phraseRelation(p.type)),
          E('span', { class: 'q-name' }, labels[p.target] || shortId(p.target)));
      }
      const desc = (it.item_type === 'node' && p.description) ? E('div', { class: 'q-desc' }, p.description) : null;
      const reason = it.reason ? E('div', { class: 'q-reason' }, '提出理由：' + it.reason) : null;

      // technical details — collapsed by default so the engineer gate loses nothing
      const sc = it.schema_check;
      const schemaFailed = sc && !sc.passed;
      const techRows = [
        E('div', {}, `項目類型：${it.item_type} · 動作：${it.action}`),
        E('div', {}, `id：${p.id}`),
      ];
      if (it.item_type === 'edge') techRows.push(E('div', {}, `原始關係：${p.source} —${p.type}→ ${p.target}`));
      if (sc) {
        const failed = (sc.checks || []).filter((c) => !c.passed);
        techRows.push(E('div', { class: sc.passed ? 'ok' : 'warn' },
          sc.passed ? 'Schema 自動檢查：通過'
                    : 'Schema 自動檢查未過：' + failed.map((c) => c.detail || c.name).join('、')));
      }
      const tech = E('details', { class: 'q-tech' },
        E('summary', {}, '技術細節', schemaFailed ? E('span', { class: 'q-warn' }, '⚠ schema 需注意') : null),
        E('div', { class: 'q-tech-body' }, ...techRows));

      const acts = E('div', { class: 'acts' },
        E('button', { class: 'btn', onclick: () => decide(it.item_id, 'approve') }, '批准'),
        E('button', { class: 'btn-ghost', onclick: () => decide(it.item_id, 'reject') }, '拒絕'));

      queue.append(E('div', { class: `qitem${schemaFailed ? ' qitem-warn' : ''}` }, head, desc, reason, tech, acts));
    });
  }
  async function decide(itemId, action) {
    try { await api.post(`/admin/curation/items/${encodeURIComponent(itemId)}/${action}`, { reviewer: 'demo', reason: action === 'approve' ? '審核通過' : '不需要' }); loadQueue(); }
    catch (err) { clear(notice); notice.append(E('div', { class: 'notice err' }, err.message)); }
  }
  loadQueue();
}

/* ============================================================
   EXPERT REVIEW / 審閱 — governance demo (AI 提案 → 工程師 gate → 反向翻譯 → 專家 gate)
   資料源:GET /admin/expert-demo/cases(唯讀;system_understanding / engineer_gate 當場算)
   ============================================================ */
// 白話 schema-gap 選項 ⇄ 內部 code(專家只看白話,見 docs/schema-gap-policy.md)
const GAP_OPTIONS = [
  ['permissive_effect', 'A 不是直接影響 C,而是改變 B 對 C 的作用強度'],
  ['antagonistic_or_synergistic_interaction', 'A 和 B 之間不是因果,而是拮抗/協同'],
  ['pathway_or_cascade', '這是一個多步驟調控路徑,不是單一效果'],
  ['conditional_effect', '這是一個條件式效果,需要特定前提才成立'],
  ['threshold_effect', '這是一個閾值效果'],
  ['unknown', '其他'],
];
const EXPERT_STORE = (cid) => `expertReview:${cid}`;

async function renderExpertDemo(host) {
  clear(host);
  host.append(E('div', { class: 'page-head', style: 'padding-bottom:0' },
    E('div', { class: 'eyebrow' }, 'EXPERT REVIEW · 專家審閱'),
    E('div', { class: 'page-title', style: 'margin-top:8px;font-size:30px' }, '審閱'),
    E('div', { class: 'page-sub' },
      'AI 擬出提案 → 工程師 gate 檢查形式 → 系統反向翻譯成白話 → 專家只審生物語意,不看 JSON。')));

  let cases;
  try { cases = await api.get('/admin/expert-demo/cases'); }
  catch (err) { host.append(E('div', { class: 'notice err', style: 'margin:24px 48px' }, err.message)); return; }
  if (!cases.length) { host.append(E('div', { class: 'muted', style: 'margin:24px 48px' }, '沒有 demo 案例。')); return; }

  // 跨 case 的 id -> {label,type},供概念圖解析 references_existing 節點(不顯示 id)
  const globalNodes = {};
  cases.forEach((c) => (c.proposal.proposed_nodes || []).forEach((n) => {
    globalNodes[n.id] = { id: n.id, label: n.label, type: n.type };
  }));

  const wrap = E('div', { class: 'ex-wrap' });
  const list = E('div', { class: 'ex-list' });
  const panel = E('div', { class: 'ex-panel' });
  wrap.append(list, panel); host.append(wrap);

  let activeId = cases[0].id;
  let activeTab = 'expert';
  const current = () => cases.find((c) => c.id === activeId);

  function gateBadge(result) {
    const ok = result === 'pass';
    const gap = result === 'needs_schema_extension';
    const cls = ok ? 'ex-badge ok' : gap ? 'ex-badge gap' : 'ex-badge warn';
    const txt = ok ? '通過' : gap ? '需補 schema' : '未過';
    return E('span', { class: cls }, txt);
  }

  function paintList() {
    clear(list);
    list.append(E('div', { class: 'eyebrow', style: 'padding:18px 20px 10px' }, '案例 · CASES'));
    cases.forEach((c, i) => {
      list.append(E('div', {
        class: 'ex-case' + (c.id === activeId ? ' on' : ''),
        onclick: () => { activeId = c.id; paintList(); paintPanel(); },
      }, E('span', { class: 'ex-case-idx' }, String(i + 1).padStart(2, '0')),
         E('div', { class: 'ex-case-body' },
           E('div', { class: 'ex-case-src' }, c.source_text),
           E('div', { class: 'ex-case-meta' }, gateBadge(c.engineer_gate.result)))));
    });
  }

  const TABS = [['proposal', 'AI 提案'], ['gate', '工程師 gate'], ['expert', '專家審閱']];
  function paintPanel() {
    clear(panel);
    const tabs = E('div', { class: 'ex-tabs' });
    TABS.forEach(([id, label]) => tabs.append(E('button', {
      class: 'ex-tab' + (id === activeTab ? ' on' : ''),
      onclick: () => { activeTab = id; paintPanel(); },
    }, label)));
    const body = E('div', { class: 'ex-body scroll' });
    panel.append(tabs, body);
    const c = current();
    if (activeTab === 'proposal') paintProposal(body, c);
    else if (activeTab === 'gate') paintGate(body, c);
    else paintExpert(body, c);
  }

  // Tab1 — AI 提案(工程師/面試官;可顯示 id/JSON)
  function paintProposal(body, c) {
    const p = c.proposal;
    body.append(E('div', { class: 'ex-src' }, '原文:' + c.source_text));
    body.append(E('div', { class: 'ex-sub' },
      `信心 ${Math.round((p.confidence || 0) * 100)}% · 套用規則 ${(p.applied_rule_ids || []).join('、') || '—'}`));
    body.append(E('div', { class: 'ex-h' }, '候選節點'));
    (p.proposed_nodes || []).forEach((n) => body.append(E('div', { class: 'ex-row' },
      E('span', { class: 'q-kind', style: `--k:${typeColor(n.type)}` }, nodeTypeLabel(n.type)),
      E('span', { class: 'ex-row-label' }, n.label),
      E('span', { class: 'mono ex-id' }, n.id))));
    body.append(E('div', { class: 'ex-h' }, '候選關係'));
    (p.proposed_edges || []).forEach((e) => body.append(E('div', { class: 'ex-row mono ex-id' },
      `${e.source} —${e.type}→ ${e.target}`)));
    if ((p.references_existing || []).length) body.append(E('div', { class: 'ex-note' },
      '引用既有:' + p.references_existing.join('、')));
    if ((p.uncertain_points || []).length) body.append(E('div', { class: 'ex-note' },
      '不確定:' + p.uncertain_points.join(';')));
    if ((p.possible_over_inference || []).length) body.append(E('div', { class: 'ex-note' },
      '可能過度推論:' + p.possible_over_inference.join(';')));
  }

  // Tab2 — 工程師 gate(逐項燈號,當場計算)
  function paintGate(body, c) {
    body.append(E('div', { class: 'ex-gate-head' }, '整體結果:', gateBadge(c.engineer_gate.result)));
    c.engineer_gate.checks.forEach((ck) => body.append(E('div', { class: 'ex-check' },
      E('span', { class: 'ex-dot ' + (ck.passed ? 'ok' : 'bad') }, ck.passed ? '✓' : '✕'),
      E('div', {},
        E('div', { class: 'ex-check-name' }, ck.name),
        ck.detail ? E('div', { class: 'ex-check-detail' }, ck.detail) : null))));
  }

  // 領域專家權威判定(seeded);白話呈現,不露 schema/gap code,維持隔離
  const EXPERT_STATUS = {
    approved: ['領域專家已確認:系統理解符合原文', 'ok'],
    rejected: ['領域專家已退回:系統理解與原文的生物語意不符', 'err'],
    schema_gap: ['領域專家:此現象現行系統無法完整表達', ''],
  };
  function expertVerdict(review) {
    if (!review) return null;
    const meta = EXPERT_STATUS[review.status];
    if (!meta) return null; // not_reviewed / 未知 → 不顯示權威判定
    const el = E('div', { class: 'notice ' + meta[1], style: 'margin:12px 0' },
      E('div', {}, meta[0] + (review.reviewed_by ? '(' + review.reviewed_by + ')' : '')));
    if (review.notes) el.append(E('div', { style: 'margin-top:6px;opacity:.85' }, review.notes));
    return el;
  }

  // Tab3 — 專家審閱(強制隔離:不出現 id / JSON / schema code / gap code)
  function paintExpert(body, c) {
    body.append(E('div', { class: 'ex-src' }, '原文:' + c.source_text));

    const r = c.engineer_gate.result;
    if (r === 'fail_schema' || r === 'fail_pattern' || r === 'fail_testability') {
      // M1:形式被退回的提案不進入專家審查,也不顯示會誤導的「系統理解」(P5 gap 句)
      body.append(E('div', { class: 'notice err', style: 'margin:14px 0' },
        '此提案在工程師 gate 因形式問題被退回,依流程不進入專家審查——請先於「工程師 gate」分頁修正形式。'));
      return;
    }

    const verdict = expertVerdict(c.expert_review);
    if (verdict) body.append(verdict);

    body.append(E('div', { class: 'ex-understand' },
      E('div', { class: 'ex-h' }, '系統理解'),
      E('div', { class: 'ex-understand-txt' }, c.system_understanding.text)));
    body.append(E('div', { class: 'ex-h' }, '概念圖'));
    body.append(conceptMap(c.proposal));
    if ((c.did_not_understand_as || []).length) {
      body.append(E('div', { class: 'ex-h' }, '系統沒有理解成'));
      const ul = E('div', { class: 'ex-notlist' });
      c.did_not_understand_as.forEach((s) => ul.append(E('div', { class: 'ex-not' }, '✕ ' + s)));
      body.append(ul);
    }
    body.append(buildReviewForm(c));
  }

  function conceptMap(proposal) {
    const used = {};
    (proposal.proposed_nodes || []).forEach((n) => { used[n.id] = { id: n.id, label: n.label, type: n.type }; });
    (proposal.proposed_edges || []).forEach((e) => [e.source, e.target].forEach((id) => {
      if (!used[id]) used[id] = globalNodes[id] || { id, label: '（相關概念）', type: 'Concept' };
    }));
    const nodes = Object.values(used);
    const edges = (proposal.proposed_edges || []).map((e) => ({
      source: e.source, target: e.target, relation: phraseRelation(e.type),
    }));
    const W = 560, H = 360;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet', class: 'ex-svg' });
    if (!nodes.length) { const t = svgEl('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'gnode-label' }); t.textContent = '(此案例未提出可繪製的關係)'; svg.append(t); return svg; }
    const pos = forceLayout(nodes, edges, W, H);
    edges.forEach((e) => {
      const a = pos[e.source], b = pos[e.target]; if (!a || !b) return;
      svg.append(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#DED5C2', 'stroke-width': '1' }));
      const lbl = svgEl('text', { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, class: 'gedge-label', 'text-anchor': 'middle' });
      lbl.textContent = e.relation; svg.append(lbl);
    });
    nodes.forEach((n) => {
      const pt = pos[n.id]; const g = svgEl('g', {});
      g.append(svgEl('rect', { x: pt.x - 6, y: pt.y - 6, width: 12, height: 12, fill: typeColor(n.type) }));
      const t = svgEl('text', { x: pt.x + 10, y: pt.y + 4, class: 'gnode-label' });
      t.textContent = n.label.length > 16 ? n.label.slice(0, 15) + '…' : n.label;
      g.append(t); svg.append(g);   // 僅 label,不掛 id、不可點開詳情(維持隔離)
    });
    return svg;
  }

  function buildReviewForm(c) {
    const saved = JSON.parse(sessionStorage.getItem(EXPERT_STORE(c.id)) || '{}');
    const form = E('div', { class: 'ex-review' });
    form.append(E('div', { class: 'ex-h' }, '你的審查'));

    const gapWrap = E('div', { class: 'ex-gapwrap' });
    const decisions = [['agree', '同意:系統理解符合原文'], ['doubt', '有疑慮:理解有偏差或過度推論'], ['cannot', '無法表達:現行系統畫不出這個現象']];
    let decision = saved.decision || '';
    let gap = saved.gap || '';
    let notes = saved.notes || '';
    const notesInput = E('textarea', { class: 'ex-notes', placeholder: '備註(選填):給後續改進的說明…' });
    notesInput.value = notes;

    function persist() {
      sessionStorage.setItem(EXPERT_STORE(c.id), JSON.stringify({ decision, gap, notes: notesInput.value }));
    }
    function paintGap() {
      clear(gapWrap);
      if (decision !== 'cannot') return;
      gapWrap.append(E('div', { class: 'ex-sub' }, '這個現象比較像:'));
      GAP_OPTIONS.forEach(([code, label]) => {
        const on = gap === code;
        gapWrap.append(E('label', { class: 'ex-radio sub' + (on ? ' on' : '') },
          E('input', { type: 'radio', name: 'gap-' + c.id, checked: on ? '' : null,
            onchange: () => { gap = code; persist(); paintGap(); } }),
          label));
      });
    }

    decisions.forEach(([val, label]) => {
      const on = decision === val;
      form.append(E('label', { class: 'ex-radio' + (on ? ' on' : '') },
        E('input', { type: 'radio', name: 'dec-' + c.id, checked: on ? '' : null,
          onchange: () => { decision = val; if (val !== 'cannot') gap = ''; persist(); refreshRadios(); paintGap(); } }),
        label));
    });
    form.append(gapWrap);
    form.append(E('div', { class: 'ex-h', style: 'margin-top:14px' }, '備註'));
    notesInput.addEventListener('input', persist);
    form.append(notesInput);
    const submitMsg = E('div', { class: 'muted', style: 'font-size:11px;margin-top:8px' },
      '選擇即存本次瀏覽;按「送出審查」記錄為一筆 append-only 稽核(可追蹤)。');
    const submitBtn = E('button', { class: 'btn', style: 'margin-top:10px' }, '送出審查');
    submitBtn.addEventListener('click', async () => {
      if (!decision) { submitMsg.textContent = '請先選擇一個審查結果。'; return; }
      submitBtn.disabled = true; submitMsg.textContent = '記錄中…';
      try {
        const res = await api.post('/admin/expert-demo/reviews', {
          case_id: c.id,
          decision,
          schema_gap_type: decision === 'cannot' ? (gap || null) : null,
          notes: notesInput.value || null,
        });
        submitMsg.textContent = '已記錄稽核 ' + res.change_id;
      } catch (err) {
        submitMsg.textContent = '記錄失敗:' + err.message;
      } finally {
        submitBtn.disabled = false;
      }
    });
    form.append(submitBtn);
    form.append(submitMsg);

    function refreshRadios() {
      form.querySelectorAll('.ex-radio').forEach((el) => {
        const input = el.querySelector('input');
        el.classList.toggle('on', input.checked);
      });
    }
    paintGap();
    return form;
  }

  paintList();
  paintPanel();
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

// ── 群組審閱 REVIEW — unified two-gate governance on real proposal groups ──────────
// Data source: GET /admin/review/groups. Each group is one biological statement
// (nodes+edges sharing a group_id) with its Schema gate (engineer_gate) + expert lens
// (back_translation) computed live. Approve writes the whole group into the graph.
async function renderReview(host) {
  clear(host);
  host.append(E('div', { class: 'page-head', style: 'padding-bottom:0' },
    E('div', { class: 'eyebrow' }, 'REVIEW · 群組審閱'),
    E('div', { class: 'page-title', style: 'margin-top:8px;font-size:30px' }, '群組審閱'),
    E('div', { class: 'page-sub' },
      '一個提案(陳述的 nodes+edges)過兩道 gate:Schema gate 檢查形式 → 專家審生物語意 → 核准寫入知識圖譜。')));

  let groups;
  try { groups = await api.get('/admin/review/groups'); }
  catch (err) { host.append(E('div', { class: 'notice err', style: 'margin:24px 48px' }, err.message)); return; }
  if (!groups.length) { host.append(E('div', { class: 'muted', style: 'margin:24px 48px' }, '目前沒有待審的提案群組。')); return; }

  const globalNodes = {};
  groups.forEach((g) => (g.proposal.proposed_nodes || []).forEach((n) => {
    globalNodes[n.id] = { id: n.id, label: n.label, type: n.type };
  }));

  // Result banner lives OUTSIDE the repainted list/panel, so a decision's outcome
  // survives the repaint that follows it.
  const flash = E('div', { style: 'margin:0 48px' });
  host.append(flash);
  function setFlash(text, kind) {
    clear(flash);
    if (text) flash.append(E('div', { class: 'notice ' + (kind || ''), style: 'margin:12px 0' }, text));
  }

  const wrap = E('div', { class: 'ex-wrap' });
  const list = E('div', { class: 'ex-list' });
  const panel = E('div', { class: 'ex-panel' });
  wrap.append(list, panel); host.append(wrap);

  let activeId = groups[0].group_id;
  let activeTab = 'expert';
  const current = () => groups.find((g) => g.group_id === activeId);

  function gateBadge(result) {
    const ok = result === 'pass';
    const gap = result === 'needs_schema_extension';
    const cls = ok ? 'ex-badge ok' : gap ? 'ex-badge gap' : 'ex-badge warn';
    return E('span', { class: cls }, ok ? '通過' : gap ? '需補 schema' : '未過');
  }

  function paintList() {
    clear(list);
    list.append(E('div', { class: 'eyebrow', style: 'padding:18px 20px 10px' }, '提案群組 · GROUPS'));
    groups.forEach((g, i) => list.append(E('div', {
      class: 'ex-case' + (g.group_id === activeId ? ' on' : ''),
      onclick: () => { activeId = g.group_id; paintList(); paintPanel(); },
    }, E('span', { class: 'ex-case-idx' }, String(i + 1).padStart(2, '0')),
       E('div', { class: 'ex-case-body' },
         E('div', { class: 'ex-case-src' }, g.understanding.text),
         E('div', { class: 'ex-case-meta' }, gateBadge(g.schema_gate.result))))));
  }

  const TABS = [['proposal', '提案內容'], ['gate', 'Schema gate'], ['expert', '專家審閱']];
  function paintPanel() {
    clear(panel);
    const tabs = E('div', { class: 'ex-tabs' });
    TABS.forEach(([id, label]) => tabs.append(E('button', {
      class: 'ex-tab' + (id === activeTab ? ' on' : ''),
      onclick: () => { activeTab = id; paintPanel(); },
    }, label)));
    const body = E('div', { class: 'ex-body scroll' });
    panel.append(tabs, body);
    const g = current();
    if (activeTab === 'proposal') paintProposal(body, g);
    else if (activeTab === 'gate') paintGate(body, g);
    else paintExpert(body, g);
  }

  // 提案 tab (engineer/interviewer — may show id/JSON)
  function paintProposal(body, g) {
    const p = g.proposal;
    body.append(E('div', { class: 'ex-sub' }, '提案者:' + g.proposed_by));
    body.append(E('div', { class: 'ex-h' }, '候選節點'));
    (p.proposed_nodes || []).forEach((n) => body.append(E('div', { class: 'ex-row' },
      E('span', { class: 'q-kind', style: `--k:${typeColor(n.type)}` }, nodeTypeLabel(n.type)),
      E('span', { class: 'ex-row-label' }, n.label),
      E('span', { class: 'mono ex-id' }, n.id))));
    body.append(E('div', { class: 'ex-h' }, '候選關係'));
    (p.proposed_edges || []).forEach((e) => body.append(E('div', { class: 'ex-row mono ex-id' },
      `${e.source} —${e.type}→ ${e.target}`)));
  }

  // Schema gate tab (form checks)
  function paintGate(body, g) {
    body.append(E('div', { class: 'ex-gate-head' }, '整體結果:', gateBadge(g.schema_gate.result)));
    g.schema_gate.checks.forEach((ck) => body.append(E('div', { class: 'ex-check' },
      E('span', { class: 'ex-dot ' + (ck.passed ? 'ok' : 'bad') }, ck.passed ? '✓' : '✕'),
      E('div', {}, E('div', { class: 'ex-check-name' }, ck.name),
        ck.detail ? E('div', { class: 'ex-check-detail' }, ck.detail) : null))));
  }

  // 專家審閱 tab (meaning; no id / JSON / schema code — isolation)
  // Deliberate divergence from the (P4-retired) expert-demo screen: instead of hiding the
  // understanding for a gate-failed proposal, we show the honest (non-gap, post-D5) summary
  // with a banner + disabled 核准, so the reviewer sees what was proposed and why it's blocked.
  function paintExpert(body, g) {
    const res = g.schema_gate.result;
    if (res !== 'pass') {
      body.append(E('div', { class: 'notice', style: 'margin:0 0 12px' },
        res === 'needs_schema_extension'
          ? '此提案為 schema gap(現行知識結構無法完整表達);以下為系統摘要,只能退回或記為 gap。'
          : '此提案未通過 Schema gate(形式問題);以下為系統摘要,只能退回修正,無法核准。'));
    }
    body.append(E('div', { class: 'ex-understand' },
      E('div', { class: 'ex-h' }, '系統理解'),
      E('div', { class: 'ex-understand-txt' }, g.understanding.text)));
    body.append(E('div', { class: 'ex-h' }, '概念圖'));
    body.append(conceptMap(g.proposal));
    body.append(reviewActions(g));
  }

  function conceptMap(proposal) {
    const used = {};
    (proposal.proposed_nodes || []).forEach((n) => { used[n.id] = { id: n.id, label: n.label, type: n.type }; });
    (proposal.proposed_edges || []).forEach((e) => [e.source, e.target].forEach((id) => {
      if (!used[id]) used[id] = globalNodes[id] || { id, label: '（相關概念）', type: 'Concept' };
    }));
    const nodes = Object.values(used);
    const edges = (proposal.proposed_edges || []).map((e) => ({ source: e.source, target: e.target, relation: phraseRelation(e.type) }));
    const W = 560, H = 360;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet', class: 'ex-svg' });
    if (!nodes.length) { const t = svgEl('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'gnode-label' }); t.textContent = '(無可繪製關係)'; svg.append(t); return svg; }
    const pos = forceLayout(nodes, edges, W, H);
    edges.forEach((e) => {
      const a = pos[e.source], b = pos[e.target]; if (!a || !b) return;
      svg.append(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#DED5C2', 'stroke-width': '1' }));
      const lbl = svgEl('text', { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, class: 'gedge-label', 'text-anchor': 'middle' });
      lbl.textContent = e.relation; svg.append(lbl);
    });
    nodes.forEach((n) => {
      const pt = pos[n.id]; const grp = svgEl('g', {});
      grp.append(svgEl('rect', { x: pt.x - 6, y: pt.y - 6, width: 12, height: 12, fill: typeColor(n.type) }));
      const t = svgEl('text', { x: pt.x + 10, y: pt.y + 4, class: 'gnode-label' });
      t.textContent = n.label.length > 16 ? n.label.slice(0, 15) + '…' : n.label;
      grp.append(t); svg.append(grp);
    });
    return svg;
  }

  function reviewActions(g) {
    const gateOk = g.schema_gate.result === 'pass';
    const box = E('div', { class: 'ex-review' });
    box.append(E('div', { class: 'ex-h' }, '你的裁決'));
    const notes = E('textarea', { class: 'ex-notes', placeholder: '理由(選填)…' });
    const msg = E('div', { class: 'muted', style: 'font-size:11px;margin-top:8px' },
      gateOk ? '核准 → 寫入知識圖譜並記錄稽核;退回 → 記錄稽核,不寫入。'
             : 'Schema gate 未通過:形式有問題的提案不能進入知識圖譜,只能退回修正。');
    const approve = E('button', { class: 'btn' }, '核准並寫入');
    const reject = E('button', { class: 'btn-ghost' }, '退回');
    // Schema gate is enforcing — the backend refuses (409) too; the UI must not imply otherwise.
    if (!gateOk) { approve.disabled = true; approve.title = 'Schema gate 未通過,無法核准'; }
    async function act(kind) {
      approve.disabled = reject.disabled = true; setFlash('處理中…');
      try {
        const res = await api.post(
          `/admin/review/groups/${encodeURIComponent(g.group_id)}/${kind}`,
          { reviewer: 'demo', reason: notes.value || null });
        setFlash(kind === 'approve'
          ? `已核准並寫入知識圖譜(nodes ${res.nodes} / edges ${res.edges})`
          : '已退回,未寫入知識圖譜。', 'ok');
        groups = groups.filter((x) => x.group_id !== g.group_id);
        if (!groups.length) {
          clear(list); clear(panel);
          panel.append(E('div', { class: 'muted', style: 'padding:24px' }, '目前沒有待審的提案群組。'));
          return;
        }
        activeId = groups[0].group_id; paintList(); paintPanel();
      } catch (err) {
        setFlash('失敗:' + err.message, 'err');
        approve.disabled = !gateOk; reject.disabled = false;
      }
    }
    approve.addEventListener('click', () => act('approve'));
    reject.addEventListener('click', () => act('reject'));
    box.append(notes, E('div', { style: 'display:flex;gap:10px;margin-top:10px' }, approve, reject), msg);
    return box;
  }

  paintList(); paintPanel();
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
