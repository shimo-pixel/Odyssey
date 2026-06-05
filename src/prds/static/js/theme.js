import { getPrefs, savePrefs } from './prefs.js';

export function applyTheme(theme) {
  const root = document.documentElement;
  const isDark = theme === 'dark';
  root.classList.toggle('dark', isDark);
  root.classList.toggle('light', !isDark);
}

export function applyLocale(locale) {
  document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN';
}

export function initAppearance() {
  const prefs = getPrefs();
  applyTheme(prefs.theme || 'light');
  applyLocale(prefs.locale || 'zh');
}

export function setTheme(theme) {
  savePrefs({ theme });
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent('prds:prefs-changed', { detail: { themeOnly: true } }));
}

export function setLocale(locale) {
  savePrefs({ locale });
  applyLocale(locale);
  window.dispatchEvent(new CustomEvent('prds:prefs-changed', { detail: { locale } }));
}

export function toggleTheme() {
  setTheme(getPrefs().theme === 'dark' ? 'light' : 'dark');
}

export function toggleLocale() {
  setLocale(getPrefs().locale === 'en' ? 'zh' : 'en');
}
