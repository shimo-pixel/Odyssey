import { API, apiOrigin } from '../api.js';
import { pageShell } from '../layout.js';
import { icon } from '../icons.js';
import { t } from '../i18n.js';
import { getPrefs } from '../prefs.js';

let pollTimer = null;
let activeCategoryId = null;
let activeTab = 'files';
let graphLoadedFor = null;
let previewObjectUrl = null;
let themeSyncHandler = null;

const TEXT_EXTS = new Set([
  'txt', 'md', 'markdown', 'json', 'csv', 'tsv', 'log', 'xml', 'html', 'htm', 'yml', 'yaml', 'py', 'js', 'ts', 'css',
]);

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatSize(n) {
  if (!n || n < 1024) return `${n || 0} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusChipClass(status) {
  const s = (status || '').toLowerCase();
  if (s === 'completed' || s === 'processed' || s === 'finished') return 'g-chip g-chip-green';
  if (s === 'error' || s === 'failed') return 'g-chip g-chip-blue';
  return 'g-chip g-chip-blue';
}

function fileExt(name) {
  const m = String(name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return m ? m[1] : '';
}

function revokePreviewUrl() {
  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = null;
  }
}

export function renderKb(categoryId = null) {
  if (categoryId) {
    return pageShell(`
      <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20" id="kb-detail-root">
        <div class="mb-6">
          <a href="#kb" class="page-back-link">${t('kb.backCategories')}</a>
        </div>
        <header class="mb-6">
          <h1 id="kb-cat-title" class="text-2xl font-semibold text-on-surface tracking-tight">${escapeHtml(categoryId)}</h1>
          <p id="kb-cat-desc" class="text-sm text-on-surface-variant mt-2">${t('kb.categoryDetailSubtitle')}</p>
        </header>

        <div class="kb-tabs settings-tabs" role="tablist" style="padding-left:0;padding-right:0">
          <button type="button" class="settings-tab is-active" role="tab" data-kb-tab="files" aria-selected="true">${t('kb.filesTab')}</button>
          <button type="button" class="settings-tab" role="tab" data-kb-tab="graph" aria-selected="false">${t('kb.graphTab')}</button>
        </div>

        <div id="kb-panel-files" class="kb-tab-panel" data-kb-panel="files" role="tabpanel">
          <div class="kb-files-toolbar">
            <div class="flex items-center gap-3 min-w-0">
              <h2 class="font-medium text-sm text-on-surface truncate">${t('kb.files')}</h2>
              <span id="kb-upload-msg" class="text-xs text-on-surface-variant truncate"></span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button type="button" id="kb-refresh" class="text-sm text-primary hover:underline px-2 py-1">${t('kb.refresh')}</button>
              <label class="btn-start px-4 py-2 rounded-lg text-sm font-medium text-on-primary cursor-pointer inline-flex items-center gap-1.5">
                <span>${t('kb.upload')}</span>
                <input id="kb-file-input" type="file" class="hidden" multiple />
              </label>
            </div>
          </div>
          <div id="kb-file-grid" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div class="glass-panel rounded-lg p-6 text-center text-on-surface-variant text-sm col-span-full">${t('common.loading')}</div>
          </div>
        </div>

        <div id="kb-panel-graph" class="kb-tab-panel hidden" data-kb-panel="graph" role="tabpanel" hidden>
          <p class="text-xs text-on-surface-variant mb-3">${t('kb.graphHint')}</p>
          <div class="glass-panel rounded-lg overflow-hidden">
            <div class="kb-graph-frame-wrap relative">
              <iframe id="kb-graph-frame" title="Knowledge Graph" class="absolute inset-0 w-full h-full border-0 bg-background" src="about:blank"></iframe>
            </div>
            <p id="kb-graph-error" class="hidden px-6 py-3 text-sm text-error"></p>
          </div>
        </div>
      </div>
    `, { sidebarActive: 'kb' });
  }

  return pageShell(`
    <div class="p-8 lg:p-12 max-w-6xl mx-auto pb-20" id="kb-list-root">
      <div class="mb-6">
        <a href="#simulate" class="page-back-link">${t('kb.back')}</a>
      </div>
      <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold text-on-surface tracking-tight">${t('kb.title')}</h1>
          <p class="text-sm text-on-surface-variant mt-2">${t('kb.categoriesSubtitle')}</p>
        </div>
        <div class="flex items-center gap-3">
          <button type="button" id="kb-new-category" class="btn-start px-4 py-2 rounded-lg text-sm font-medium text-on-primary">
            ${t('kb.newCategory')}
          </button>
        </div>
      </header>
      <div id="kb-category-grid" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div class="glass-panel rounded-lg p-6 text-center text-on-surface-variant text-sm col-span-full">${t('common.loading')}</div>
      </div>
    </div>
  `, { sidebarActive: 'kb' });
}

async function refreshCategories() {
  const grid = document.getElementById('kb-category-grid');
  if (!grid) return;
  try {
    const cats = await API.listKbCategories();
    if (!cats.length) {
      grid.innerHTML = `<div class="glass-panel rounded-lg p-8 text-center text-on-surface-variant text-sm col-span-full">${t('kb.noCategories')}</div>`;
      return;
    }
    grid.innerHTML = cats.map((c) => `
      <div class="kb-card glass-panel rounded-lg p-5 hover:border-primary/40 transition-colors">
        <a href="#kb/${encodeURIComponent(c.id)}" class="kb-card-body no-underline text-inherit">
          <h3 class="font-medium text-on-surface mb-1">${escapeHtml(c.name || c.id)}</h3>
          ${c.description ? `<p class="text-xs text-on-surface-variant line-clamp-2 mb-3">${escapeHtml(c.description)}</p>` : ''}
          <p class="text-xs text-on-surface-variant mb-2">${t('kb.docCount', { n: c.document_count || 0 })}</p>
          <p class="text-[11px] font-mono text-outline truncate">${escapeHtml(c.id)}</p>
        </a>
        <button type="button" data-del-cat="${escapeHtml(c.id)}" class="kb-card-delete" aria-label="${t('kb.deleteCategory')}">${t('kb.deleteCategory')}</button>
      </div>
    `).join('');
  } catch (e) {
    grid.innerHTML = `<div class="glass-panel rounded-lg p-6 text-center text-error text-sm col-span-full">${escapeHtml(e.message || String(e))}</div>`;
  }
}

async function refreshFiles(categoryId) {
  const grid = document.getElementById('kb-file-grid');
  if (!grid) return;
  try {
    const docs = await API.listKbDocuments(categoryId);
    if (!docs.length) {
      grid.innerHTML = `<div class="glass-panel rounded-lg p-8 text-center text-on-surface-variant text-sm col-span-full">${t('kb.empty')}</div>`;
      return;
    }
    grid.innerHTML = docs.map((d) => `
      <div class="kb-card glass-panel rounded-lg p-5">
        <button type="button" class="kb-card-body" data-open-doc="${escapeHtml(d.id)}" data-filename="${escapeHtml(d.filename)}" data-has-content="${d.has_content ? '1' : '0'}">
          <div class="flex items-start justify-between gap-2 mb-2">
            <h3 class="font-medium text-sm text-on-surface break-all text-left" title="${escapeHtml(d.filename)}">${escapeHtml(d.filename)}</h3>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded-md ${statusChipClass(d.status)} shrink-0">${escapeHtml(d.status || '—')}</span>
          </div>
          <div class="text-xs text-on-surface-variant flex justify-between gap-2">
            <span>${formatSize(d.size)}</span>
            <span>${formatTime(d.created_at)}</span>
          </div>
        </button>
        <button type="button" data-del="${escapeHtml(d.id)}" class="kb-card-delete" aria-label="${t('kb.delete')}">${t('kb.delete')}</button>
      </div>
    `).join('');
  } catch (e) {
    grid.innerHTML = `<div class="glass-panel rounded-lg p-6 text-center text-error text-sm col-span-full">${escapeHtml(e.message || String(e))}</div>`;
  }
}

async function loadGraph(categoryId) {
  const frame = document.getElementById('kb-graph-frame');
  const err = document.getElementById('kb-graph-error');
  if (!frame) return;
  const prefs = getPrefs();
  const lang = prefs.locale === 'en' ? 'en' : 'zh';
  const theme = prefs.theme === 'dark' ? 'dark' : 'light';
  // LightRAG WebUI HashRouter embed (see DTS-LightRAG-HTTP-API §3.1)
  let embedPath = '/lightrag/webui/index.html#/embed/graph';
  try {
    const cfg = await API.getConfig();
    if (cfg.lightrag_embed_path) embedPath = cfg.lightrag_embed_path;
  } catch (_) { /* default */ }
  const qs = new URLSearchParams({
    workspace: categoryId,
    lang,
    theme,
    hg: '5',
  });
  frame.src = `${apiOrigin()}${embedPath}?${qs.toString()}`;
  graphLoadedFor = categoryId;
  try {
    const st = await API.kbStatus();
    if (!st.lightrag_ok && err) {
      err.classList.remove('hidden');
      err.textContent = t('kg.offlineHint');
    } else if (err) {
      err.classList.add('hidden');
    }
  } catch {
    if (err) {
      err.classList.remove('hidden');
      err.textContent = t('kg.offlineHint');
    }
  }
}

function syncGraphTheme(theme) {
  const frame = document.getElementById('kb-graph-frame');
  if (!frame?.contentWindow || !frame.src || frame.src === 'about:blank') return;
  const mode = theme === 'dark' ? 'dark' : 'light';
  try {
    frame.contentWindow.postMessage(
      { type: 'lightrag:set-theme', theme: mode },
      apiOrigin(),
    );
  } catch (_) { /* cross-origin / not ready */ }
}

function switchTab(tab, categoryId) {
  activeTab = tab;
  document.querySelectorAll('[data-kb-tab]').forEach((btn) => {
    const on = btn.getAttribute('data-kb-tab') === tab;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('[data-kb-panel]').forEach((panel) => {
    const on = panel.getAttribute('data-kb-panel') === tab;
    panel.classList.toggle('hidden', !on);
    if (on) panel.removeAttribute('hidden');
    else panel.setAttribute('hidden', '');
  });
  if (tab === 'graph' && graphLoadedFor !== categoryId) {
    loadGraph(categoryId);
  }
}

function closeFilePreview() {
  revokePreviewUrl();
  document.getElementById('kb-preview-overlay')?.remove();
}

async function openFilePreview(docId, filename, categoryId, hasContent) {
  closeFilePreview();
  if (!hasContent) {
    alert(t('kb.previewUnavailable'));
    return;
  }

  const overlay = document.createElement('div');
  overlay.id = 'kb-preview-overlay';
  overlay.className = 'refine-overlay';
  overlay.innerHTML = `
    <div class="refine-modal kb-preview-modal custom-scrollbar" role="dialog" aria-modal="true">
      <div class="refine-modal-head">
        <div class="min-w-0">
          <h2 class="text-lg font-semibold text-on-surface truncate">${escapeHtml(filename)}</h2>
          <p class="text-xs text-on-surface-variant mt-1">${t('kb.previewTitle')}</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <a id="kb-preview-download" class="refine-btn refine-btn--ghost text-sm no-underline" href="#">${t('kb.download')}</a>
          <button type="button" id="kb-preview-close" class="refine-icon-btn" aria-label="${t('common.close')}">
            ${icon('close', 'icon icon--md')}
          </button>
        </div>
      </div>
      <div id="kb-preview-body" class="kb-preview-body">
        <p class="text-sm text-on-surface-variant">${t('common.loading')}</p>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const close = () => closeFilePreview();
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.getElementById('kb-preview-close')?.addEventListener('click', close);

  const body = document.getElementById('kb-preview-body');
  const dl = document.getElementById('kb-preview-download');

  try {
    const res = await API.getKbDocumentContent(docId, categoryId);
    const blob = await res.blob();
    const type = (res.headers.get('content-type') || blob.type || '').split(';')[0].trim().toLowerCase();
    previewObjectUrl = URL.createObjectURL(blob);
    if (dl) {
      dl.href = previewObjectUrl;
      dl.download = filename || 'download';
    }

    const ext = fileExt(filename);
    const isText = type.startsWith('text/')
      || type === 'application/json'
      || type === 'application/xml'
      || TEXT_EXTS.has(ext);
    const isPdf = type === 'application/pdf' || ext === 'pdf';

    if (isText) {
      const text = await blob.text();
      body.innerHTML = `<pre class="kb-preview-pre">${escapeHtml(text)}</pre>`;
    } else if (isPdf) {
      body.innerHTML = `<iframe class="kb-preview-pdf" title="${escapeHtml(filename)}" src="${previewObjectUrl}"></iframe>`;
    } else {
      body.innerHTML = `
        <div class="kb-preview-binary">
          <p class="text-sm text-on-surface-variant mb-4">${t('kb.previewBinary')}</p>
          <a class="btn-start px-4 py-2 rounded-lg text-sm font-medium text-on-primary no-underline inline-flex" href="${previewObjectUrl}" download="${escapeHtml(filename)}">${t('kb.download')}</a>
        </div>`;
    }
  } catch (e) {
    body.innerHTML = `<p class="text-sm text-error">${escapeHtml(e.message || String(e))}</p>`;
  }
}

async function handleUpload(categoryId, input) {
  const files = [...(input?.files || [])];
  const msg = document.getElementById('kb-upload-msg');
  if (!files.length) return;
  if (msg) msg.textContent = t('kb.uploading');
  try {
    for (const f of files) {
      await API.uploadKbDocument(f, categoryId);
    }
    if (msg) msg.textContent = t('kb.uploadOk');
    await refreshFiles(categoryId);
  } catch (err) {
    if (msg) msg.textContent = err.message || String(err);
  } finally {
    if (input) input.value = '';
  }
}

export function unmountKb() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (themeSyncHandler) {
    window.removeEventListener('prds:prefs-changed', themeSyncHandler);
    themeSyncHandler = null;
  }
  activeCategoryId = null;
  activeTab = 'files';
  graphLoadedFor = null;
  closeFilePreview();
}

function openCreateCategoryModal() {
  document.getElementById('kb-create-overlay')?.remove();
  const overlay = document.createElement('div');
  overlay.id = 'kb-create-overlay';
  overlay.className = 'refine-overlay';
  overlay.innerHTML = `
    <div class="refine-modal custom-scrollbar" role="dialog" aria-modal="true" style="max-width:28rem">
      <div class="refine-modal-head">
        <div>
          <h2 class="text-lg font-semibold text-on-surface">${t('kb.newCategory')}</h2>
          <p class="text-xs text-on-surface-variant mt-1">${t('kb.newCategoryHint')}</p>
        </div>
        <button type="button" id="kb-create-close" class="refine-icon-btn" aria-label="${t('common.close')}">
          ${icon('close', 'icon icon--md')}
        </button>
      </div>
      <div class="refine-grid">
        <label class="refine-field">
          <span class="refine-label">${t('kb.categoryName')}</span>
          <input id="kb-create-name" type="text" class="refine-input" maxlength="128" placeholder="${t('kb.newCategoryPrompt')}" />
        </label>
        <label class="refine-field">
          <span class="refine-label">${t('kb.categoryDesc')}</span>
          <textarea id="kb-create-desc" rows="3" class="refine-input" maxlength="2000" placeholder="${t('kb.categoryDescPlaceholder')}"></textarea>
        </label>
      </div>
      <div class="refine-actions">
        <button type="button" id="kb-create-cancel" class="refine-btn refine-btn--ghost">${t('common.close')}</button>
        <button type="button" id="kb-create-confirm" class="refine-btn refine-btn--primary">
          ${icon('add', 'icon icon--sm')}<span>${t('kb.createConfirm')}</span>
        </button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.getElementById('kb-create-close')?.addEventListener('click', close);
  document.getElementById('kb-create-cancel')?.addEventListener('click', close);
  document.getElementById('kb-create-name')?.focus();

  document.getElementById('kb-create-confirm')?.addEventListener('click', async () => {
    const name = (document.getElementById('kb-create-name')?.value || '').trim();
    const description = (document.getElementById('kb-create-desc')?.value || '').trim();
    if (!name) {
      alert(t('kb.nameRequired'));
      return;
    }
    const btn = document.getElementById('kb-create-confirm');
    if (btn) btn.disabled = true;
    try {
      const cat = await API.createKbCategory({ name, description });
      close();
      location.hash = `#kb/${encodeURIComponent(cat.id)}`;
    } catch (e) {
      alert(e.message || String(e));
      if (btn) btn.disabled = false;
    }
  });
}

async function mountCategoryList() {
  await refreshCategories();

  document.getElementById('kb-new-category')?.addEventListener('click', () => {
    openCreateCategoryModal();
  });

  document.getElementById('kb-category-grid')?.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-del-cat]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const id = btn.getAttribute('data-del-cat');
    if (!id || !confirm(t('kb.deleteCategoryConfirm'))) return;
    try {
      await API.deleteKbCategory(id);
      await refreshCategories();
    } catch (err) {
      alert(err.message || String(err));
    }
  });

  pollTimer = setInterval(() => {
    refreshCategories();
  }, 8000);
}

async function mountCategoryDetail(categoryId) {
  activeCategoryId = categoryId;
  activeTab = 'files';
  graphLoadedFor = null;

  try {
    const cats = await API.listKbCategories();
    const cat = cats.find((c) => c.id === categoryId);
    const title = document.getElementById('kb-cat-title');
    const desc = document.getElementById('kb-cat-desc');
    if (title && cat) title.textContent = cat.name || categoryId;
    if (desc && cat?.description) desc.textContent = cat.description;
  } catch (_) { /* keep id */ }

  await refreshFiles(categoryId);

  document.querySelectorAll('[data-kb-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      switchTab(btn.getAttribute('data-kb-tab'), categoryId);
    });
  });

  document.getElementById('kb-refresh')?.addEventListener('click', () => {
    refreshFiles(categoryId);
  });

  document.getElementById('kb-file-input')?.addEventListener('change', (e) => {
    handleUpload(categoryId, e.target);
  });

  document.getElementById('kb-file-grid')?.addEventListener('click', async (e) => {
    const del = e.target.closest('[data-del]');
    if (del) {
      e.preventDefault();
      e.stopPropagation();
      const id = del.getAttribute('data-del');
      if (!id || !confirm(t('kb.deleteConfirm'))) return;
      try {
        await API.deleteKbDocument(id, categoryId);
        await refreshFiles(categoryId);
      } catch (err) {
        alert(err.message || String(err));
      }
      return;
    }
    const row = e.target.closest('[data-open-doc]');
    if (!row) return;
    const id = row.getAttribute('data-open-doc');
    const filename = row.getAttribute('data-filename') || '';
    const hasContent = row.getAttribute('data-has-content') === '1';
    if (id) openFilePreview(id, filename, categoryId, hasContent);
  });

  themeSyncHandler = (e) => {
    if (!e.detail?.themeOnly) return;
    syncGraphTheme(getPrefs().theme);
  };
  window.addEventListener('prds:prefs-changed', themeSyncHandler);

  pollTimer = setInterval(() => {
    if (activeCategoryId === categoryId && activeTab === 'files') {
      refreshFiles(categoryId);
    }
  }, 5000);
}

export async function mountKb(categoryId = null) {
  unmountKb();
  if (categoryId) {
    await mountCategoryDetail(categoryId);
  } else {
    await mountCategoryList();
  }
}
