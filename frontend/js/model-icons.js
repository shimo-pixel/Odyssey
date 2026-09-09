/** Brand icons for known LLM providers / model families (inline SVG). */

const ICONS = {
  deepseek: `<img src="./assets/deepseek.png" width="20" height="20" alt="" decoding="async" />`,
  openai: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="#10A37F" d="M22.3 10.2a5.4 5.4 0 00-3.1-7.4 5.5 5.5 0 00-5.9 1.2A5.4 5.4 0 007.5 2a5.5 5.5 0 00-5.2 3.7A5.4 5.4 0 00.7 12a5.4 5.4 0 003.1 7.4 5.5 5.5 0 005.9-1.2A5.4 5.4 0 0016.5 22a5.5 5.5 0 005.2-3.7 5.4 5.4 0 00.6-8.1z"/><path fill="#fff" d="M12 7.2l3.2 1.8v3.7L12 16.5 8.8 14.7V11l3.2-1.8z"/></svg>`,
  gemini: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><defs><linearGradient id="gm" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#1BA1E3"/><stop offset="50%" stop-color="#5489D6"/><stop offset="100%" stop-color="#9B72CB"/></linearGradient></defs><path fill="url(#gm)" d="M12 2c.4 4.8 2.4 8.2 7.5 10C14.4 13.8 12.4 17.2 12 22c-.4-4.8-2.4-8.2-7.5-10C9.6 10.2 11.6 6.8 12 2z"/></svg>`,
  claude: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="#D97757" d="M12 2l2.2 6.8H21l-5.6 4.1 2.1 6.6L12 15.8 6.5 19.5l2.1-6.6L3 8.8h6.8L12 2z"/></svg>`,
  qwen: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect width="24" height="24" rx="6" fill="#615CED"/><path d="M7 12h10M12 7v10" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>`,
  generic: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="currentColor" opacity="0.15"/><path d="M8 14c1.2 1.5 2.8 2.2 4 2.2s2.8-.7 4-2.2M9 10h.01M15 10h.01" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>`,
};

export function detectModelBrand(provider = '', model = '') {
  const s = `${provider} ${model}`.toLowerCase();
  if (s.includes('deepseek')) return 'deepseek';
  if (s.includes('gemini') || s.includes('google')) return 'gemini';
  if (s.includes('claude') || s.includes('anthropic')) return 'claude';
  if (s.includes('qwen') || s.includes('dashscope')) return 'qwen';
  if (s.includes('gpt') || s.includes('openai') || s.includes('o1') || s.includes('o3')) return 'openai';
  return 'generic';
}

export function modelBrandIcon(provider, model, className = 'model-brand-icon') {
  const brand = detectModelBrand(provider, model);
  return `<span class="${className}" data-brand="${brand}" aria-hidden="true">${ICONS[brand] || ICONS.generic}</span>`;
}
