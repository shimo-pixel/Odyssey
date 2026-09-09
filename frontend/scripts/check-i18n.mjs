#!/usr/bin/env node
// Verifies zh/en key parity and that every t('...') key used in the app exists.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const src = readFileSync(join(root, 'js/i18n.js'), 'utf8');

function keysOf(locale) {
  const start = src.indexOf(`  ${locale}: {`);
  if (start < 0) throw new Error(`locale ${locale} not found`);
  const end = src.indexOf('\n  },', start);
  const body = src.slice(start, end);
  return new Set([...body.matchAll(/^\s{4}'([^']+)':/gm)].map(m => m[1]));
}

const zh = keysOf('zh');
const en = keysOf('en');

const missingEn = [...zh].filter(k => !en.has(k));
const missingZh = [...en].filter(k => !zh.has(k));

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith('.js') && !p.endsWith('js/i18n.js')) out.push(p);
  }
  return out;
}

const used = new Map();
for (const file of walk(join(root, 'js'))) {
  const text = readFileSync(file, 'utf8');
  for (const m of text.matchAll(/\bt\(\s*'([^'${}]+)'/g)) {
    if (!used.has(m[1])) used.set(m[1], file.slice(root.length + 1));
  }
}

const unknown = [...used].filter(([k]) => !zh.has(k));
const report = (label, items) => {
  if (!items.length) return true;
  console.error(`\n${label} (${items.length}):`);
  for (const item of items) console.error('  ' + (Array.isArray(item) ? `${item[0]}  <- ${item[1]}` : item));
  return false;
};

const ok = [
  report('Keys missing from en', missingEn),
  report('Keys missing from zh', missingZh),
  report('t() keys with no translation', unknown),
].every(Boolean);

console.log(ok ? `i18n ok — ${zh.size} keys, ${used.size} referenced` : '\ni18n check failed');
process.exit(ok ? 0 : 1);
