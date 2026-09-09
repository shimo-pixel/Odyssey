/**
 * Chat content renderer: GFM markdown + MathType-compatible LaTeX
 * ($…$ / $$…$$ / \\(…\\) / \\[…\\]) via marked + KaTeX.
 */

const KATEX_VERSION = '0.16.22';
const MARKED_VERSION = '15.0.7';
const KATEX_CSS = `https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/katex.min.css`;
const KATEX_JS = `https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/katex.min.js`;
const MARKED_JS = `https://cdn.jsdelivr.net/npm/marked@${MARKED_VERSION}/marked.min.js`;

let katexPromise = null;
let markedPromise = null;

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function loadScript(id, src) {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id);
    if (existing) {
      if (existing.dataset.loaded === '1') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`Failed to load ${id}`)), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.id = id;
    script.src = src;
    script.defer = true;
    script.onload = () => {
      script.dataset.loaded = '1';
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${id}`));
    document.head.appendChild(script);
  });
}

function ensureCss() {
  if (document.getElementById('katex-css')) return;
  const link = document.createElement('link');
  link.id = 'katex-css';
  link.rel = 'stylesheet';
  link.href = KATEX_CSS;
  document.head.appendChild(link);
}

/** Load KaTeX once (CDN). */
export function ensureKatex() {
  if (typeof window !== 'undefined' && window.katex) {
    ensureCss();
    return Promise.resolve(window.katex);
  }
  if (katexPromise) return katexPromise;
  ensureCss();
  katexPromise = loadScript('katex-js', KATEX_JS)
    .then(() => window.katex)
    .catch((err) => {
      katexPromise = null;
      throw err;
    });
  return katexPromise;
}

/** Load marked once (CDN). */
export function ensureMarked() {
  if (typeof window !== 'undefined' && window.marked?.parse) {
    return Promise.resolve(window.marked);
  }
  if (markedPromise) return markedPromise;
  markedPromise = loadScript('marked-js', MARKED_JS)
    .then(() => window.marked)
    .catch((err) => {
      markedPromise = null;
      throw err;
    });
  return markedPromise;
}

/** Preload markdown + math renderers. */
export function ensureChatRenderers() {
  return Promise.all([
    ensureKatex().catch(() => null),
    ensureMarked().catch(() => null),
  ]);
}

function findNextDelimiter(text, from) {
  const markers = ['```', '$$', '\\[', '\\(', '$'];
  let best = -1;
  for (const m of markers) {
    const idx = text.indexOf(m, from);
    if (idx !== -1 && (best === -1 || idx < best)) best = idx;
  }
  return best;
}

/**
 * Split text into plain / math segments. Incomplete delimiters stay as plain text
 * (important while streaming).
 */
function splitSegments(text) {
  const segments = [];
  let i = 0;
  const n = text.length;

  while (i < n) {
    if (text.startsWith('```', i)) {
      const end = text.indexOf('```', i + 3);
      if (end === -1) {
        segments.push({ type: 'text', value: text.slice(i) });
        break;
      }
      segments.push({ type: 'text', value: text.slice(i, end + 3) });
      i = end + 3;
      continue;
    }

    if (text.startsWith('$$', i)) {
      const end = text.indexOf('$$', i + 2);
      if (end === -1) {
        segments.push({ type: 'text', value: text.slice(i) });
        break;
      }
      segments.push({ type: 'display', value: text.slice(i + 2, end) });
      i = end + 2;
      continue;
    }

    if (text.startsWith('\\[', i)) {
      const end = text.indexOf('\\]', i + 2);
      if (end === -1) {
        segments.push({ type: 'text', value: text.slice(i) });
        break;
      }
      segments.push({ type: 'display', value: text.slice(i + 2, end) });
      i = end + 2;
      continue;
    }

    if (text.startsWith('\\(', i)) {
      const end = text.indexOf('\\)', i + 2);
      if (end === -1) {
        segments.push({ type: 'text', value: text.slice(i) });
        break;
      }
      segments.push({ type: 'inline', value: text.slice(i + 2, end) });
      i = end + 2;
      continue;
    }

    if (text[i] === '$') {
      const next = text[i + 1];
      if (next && /[\d\s]/.test(next)) {
        const nxt = findNextDelimiter(text, i + 1);
        const end = nxt === -1 ? n : nxt;
        segments.push({ type: 'text', value: text.slice(i, end) });
        i = end;
        continue;
      }
      let j = i + 1;
      let closed = -1;
      while (j < n) {
        if (text[j] === '$' && text[j - 1] !== '\\') {
          closed = j;
          break;
        }
        if (text[j] === '\n') break;
        j += 1;
      }
      if (closed === -1) {
        segments.push({ type: 'text', value: text.slice(i) });
        break;
      }
      const body = text.slice(i + 1, closed);
      if (!body.trim()) {
        segments.push({ type: 'text', value: text.slice(i, closed + 1) });
      } else {
        segments.push({ type: 'inline', value: body });
      }
      i = closed + 1;
      continue;
    }

    const nxt = findNextDelimiter(text, i);
    if (nxt === -1) {
      segments.push({ type: 'text', value: text.slice(i) });
      break;
    }
    if (nxt === i) {
      segments.push({ type: 'text', value: text[i] });
      i += 1;
      continue;
    }
    segments.push({ type: 'text', value: text.slice(i, nxt) });
    i = nxt;
  }

  return segments;
}

function renderTex(tex, displayMode) {
  const katex = typeof window !== 'undefined' ? window.katex : null;
  if (!katex) return escapeHtml(displayMode ? `$$${tex}$$` : `$${tex}$`);
  try {
    return katex.renderToString(tex.trim(), {
      throwOnError: false,
      displayMode,
      strict: 'ignore',
      trust: false,
    });
  } catch {
    return `<span class="sim-chat-math-fallback">${escapeHtml(tex)}</span>`;
  }
}

function mathHtml(seg) {
  if (seg.type === 'display') {
    return `<div class="sim-chat-math-block">${renderTex(seg.value, true)}</div>`;
  }
  return `<span class="sim-chat-math-inline">${renderTex(seg.value, false)}</span>`;
}

/** Protect math from markdown (_ / * / etc.) with opaque placeholders. */
function extractMath(text) {
  const slots = [];
  const protectedText = splitSegments(text)
    .map((seg) => {
      if (seg.type === 'display' || seg.type === 'inline') {
        const idx = slots.length;
        slots.push(seg);
        // Private-use placeholders survive markdown unchanged.
        return seg.type === 'display'
          ? `\n\n\uE000MATH${idx}\uE001\n\n`
          : `\uE000MATH${idx}\uE001`;
      }
      return seg.value;
    })
    .join('');
  return { text: protectedText, slots };
}

function restoreMath(html, slots) {
  return html.replace(/\uE000MATH(\d+)\uE001/g, (_, n) => {
    const seg = slots[Number(n)];
    return seg ? mathHtml(seg) : '';
  });
}

const ALLOWED_TAGS = new Set([
  'A', 'ABBR', 'B', 'BLOCKQUOTE', 'BR', 'CODE', 'DEL', 'DIV', 'EM', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'HR', 'I', 'LI', 'OL', 'P', 'PRE', 'S', 'SPAN', 'STRONG', 'SUB', 'SUP', 'TABLE', 'TBODY', 'TD',
  'TH', 'THEAD', 'TR', 'UL', 'ANNOTATION', 'MATH', 'MGLYPH', 'MI', 'MN', 'MO', 'MROW', 'MSPACE',
  'MSQRT', 'MSTYLE', 'MSUB', 'MSUBSUP', 'MSUP', 'MTEXT', 'MUNDER', 'MUNDEROVER', 'SEMANTICS',
]);

const ALLOWED_ATTRS = new Set([
  'href', 'title', 'class', 'id', 'target', 'rel', 'aria-hidden', 'aria-label', 'role',
  'colspan', 'rowspan', 'align', 'start', 'style', 'xmlns', 'encoding',
]);

function sanitizeHtml(html) {
  if (typeof document === 'undefined') return html;
  const template = document.createElement('template');
  template.innerHTML = html;
  const walk = (node) => {
    const children = [...node.childNodes];
    for (const child of children) {
      if (child.nodeType === 1) {
        const tag = child.tagName;
        if (!ALLOWED_TAGS.has(tag) && !tag.startsWith('M')) {
          // Unwrap unknown elements (keep children)
          while (child.firstChild) node.insertBefore(child.firstChild, child);
          node.removeChild(child);
          continue;
        }
        for (const attr of [...child.attributes]) {
          const name = attr.name.toLowerCase();
          if (name.startsWith('on') || !ALLOWED_ATTRS.has(name)) {
            child.removeAttribute(attr.name);
            continue;
          }
          if (name === 'href') {
            const href = (attr.value || '').trim();
            if (/^javascript:/i.test(href) || /^data:/i.test(href) || /^vbscript:/i.test(href)) {
              child.removeAttribute(attr.name);
            } else {
              child.setAttribute('rel', 'noopener noreferrer');
              if (/^https?:\/\//i.test(href) || href.startsWith('mailto:')) {
                child.setAttribute('target', '_blank');
              }
            }
          }
          if (name === 'style') {
            // KaTeX injects layout styles; drop anything else risky
            const style = attr.value || '';
            if (/expression|url\s*\(|@import|javascript/i.test(style)) {
              child.removeAttribute('style');
            }
          }
        }
        walk(child);
      } else if (child.nodeType === 8) {
        node.removeChild(child);
      }
    }
  };
  walk(template.content);
  return template.innerHTML;
}

function parseMarkdown(src) {
  const marked = typeof window !== 'undefined' ? window.marked : null;
  if (!marked?.parse) {
    return escapeHtml(src).replace(/\n/g, '<br>');
  }
  try {
    return marked.parse(src, {
      async: false,
      breaks: true,
      gfm: true,
    });
  } catch {
    return escapeHtml(src).replace(/\n/g, '<br>');
  }
}

/**
 * Render chat message content as HTML (markdown + KaTeX).
 * Incomplete math while streaming stays as plain escaped text.
 */
export function formatChatHtml(text) {
  const raw = String(text ?? '');
  if (!raw) return '';
  const { text: protectedText, slots } = extractMath(raw);
  const mdHtml = parseMarkdown(protectedText);
  const withMath = restoreMath(mdHtml, slots);
  return sanitizeHtml(withMath);
}
