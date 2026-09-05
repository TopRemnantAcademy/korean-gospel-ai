/* ═══════════════════════════════════════════════════════════════════════════
   DOM helpers — lightweight jQuery-style shortcuts
   ═══════════════════════════════════════════════════════════════════════════ */

const $ = (sel, parent = document) => parent.querySelector(sel);
const $$ = (sel, parent = document) => [...parent.querySelectorAll(sel)];

/* Create element with attributes and children in a single call */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'className') el.className = v;
    else if (k === 'textContent') el.textContent = v;
    else if (k === 'innerHTML') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    el.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return el;
}

/* Show/hide helpers */
function show(el) { el.classList.remove('hidden'); }
function hide(el) { el.classList.add('hidden'); }
function toggle(el) { el.classList.toggle('hidden'); }

/* Clear all children */
function empty(el) { el.textContent = ''; }

/* Debounce */
function debounce(fn, ms = 150) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
