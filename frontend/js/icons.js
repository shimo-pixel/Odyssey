/** Minimal stroke icons (20×20) — single family, no external deps */

const PATHS = {
  logo: '<path d="M4 14V6l8-4 8 4v8l-8 4-8-4z" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 2v16M4 6l8 4 8-4" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  simulate: '<path d="M6 3v14M10 7v10M14 5v12M18 9v8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  monitor: '<path d="M3 17V7l9-4 9 4v10" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M7 13l3 3 6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  results: '<rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M3 8h14M8 3v14" stroke="currentColor" stroke-width="1.5"/>',
  knowledge: '<circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="4" cy="6" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="16" cy="6" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="4" cy="14" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="16" cy="14" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M6 7l2.5 2M13.5 7L11 9M6 13l2.5-2M13.5 13L11 11" stroke="currentColor" stroke-width="1.5"/>',
  model: '<rect x="4" y="3" width="12" height="14" rx="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M8 7h4M8 10h4M8 13h2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  settings: '<circle cx="10" cy="10" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M10 1.8l.55 1.85 1.7-.55.95 1.7-1.4 1.2.7 1.75-1.9.35-.35 1.9-1.75-.7-1.2 1.4-1.7-.95.55-1.7-1.85-.55V8.2l1.85-.55-.55-1.7 1.7-.95 1.2 1.4 1.75-.7.35-1.9 1.9.35-.7-1.75 1.4-1.2.95-1.7-1.7.55L10 1.8z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round" fill="none"/>',
  translate: '<path d="M3 5h8M7 5c0 5-2 8-5 10M4 9h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/><path d="M12 8h6M15 8v7M13 13h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  sun: '<circle cx="10" cy="10" r="3.5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M10 2v1.5M10 16.5V18M2 10h1.5M16.5 10H18M4.2 4.2l1 1M14.8 14.8l1 1M4.2 15.8l1-1M14.8 5.2l1-1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  moon: '<path d="M15.5 11.5A6.5 6.5 0 0110 3.5 7 7 0 1015.5 11.5z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  gear: '<circle cx="10" cy="10" r="2.25" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M10 2.75v1.5M10 15.75v1.5M2.75 10h1.5M15.75 10h1.5M4.4 4.4l1.06 1.06M14.54 14.54l1.06 1.06M4.4 15.6l1.06-1.06M14.54 5.46l1.06-1.06M7.05 3.2l.55 1.4M12.4 15.4l.55 1.4M3.2 7.05l1.4.55M15.4 12.4l1.4.55M3.2 12.95l1.4-.55M15.4 7.6l1.4-.55M7.6 16.8l.55-1.4M12.95 3.2l.55-1.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  tune: '<path d="M3 6h14M6 10h8M8 14h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="6" cy="6" r="1.5" fill="currentColor"/><circle cx="12" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="14" r="1.5" fill="currentColor"/>',
  globe: '<circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M3 10h14M10 3c2.2 2.4 2.2 11.6 0 14M10 3c-2.2 2.4-2.2 11.6 0 14" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  link: '<path d="M8 12l4-4M11 8l2-2a2.8 2.8 0 014 4l-2 2M9 12l-2 2a2.8 2.8 0 01-4-4l2-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>',
  storage: '<ellipse cx="10" cy="5" rx="7" ry="2.5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M3 5v10c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M3 10c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  refresh: '<path d="M16 10a6 6 0 11-1.5-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/><path d="M16 4v4h-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  bolt: '<path d="M11 2L5 11h5l-1 7 7-10h-5l1-6z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/>',
  map: '<path d="M3 6l7-3 7 3v11l-7-3-7 3V6z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/><path d="M10 3v11M17 6v11" stroke="currentColor" stroke-width="1.5"/>',
  route: '<circle cx="6" cy="6" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="14" cy="14" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M8 6h4a2 2 0 012 2v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>',
  search: '<circle cx="9" cy="9" r="5.5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M13.5 13.5L17 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  insights: '<path d="M3 14l4-4 3 3 6-7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M14 6h3v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  users: '<circle cx="7" cy="7" r="2.5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M2 17c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="14" cy="8" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 17c0-2 1.5-3.5 3.5-3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>',
  info: '<circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M10 9v5M10 6.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  help: '<circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M7.5 7.5a2.5 2.5 0 014.5 1.5c0 2-3 2-3 4M10 15v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>',
  metrics: '<path d="M3 16V8M7 16V5M11 16v-6M15 16V3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  arrowRight: '<path d="M4 10h10M11 6l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  send: '<path d="M10 16V5M6.5 8.5L10 5l3.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  more: '<circle cx="10" cy="5" r="1" fill="currentColor"/><circle cx="10" cy="10" r="1" fill="currentColor"/><circle cx="10" cy="15" r="1" fill="currentColor"/>',
  layers: '<path d="M10 3L3 7l7 4 7-4-7-4zM3 12l7 4 7-4M3 17l7 4 7-4" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/>',
  brain: '<path d="M10 3c-2 0-3.5 1.5-3.5 3.5 0 1 .5 2 1.5 2.5-.5 1-1.5 2-1.5 3.5 0 2 1.5 3.5 3.5 3.5s3.5-1.5 3.5-3.5c0-1.5-1-2.5-1.5-3.5 1-.5 1.5-1.5 1.5-2.5C13.5 4.5 12 3 10 3z" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  schema: '<rect x="3" y="3" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><rect x="12" y="3" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><rect x="7" y="12" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M8 8v2h4V8M10 10v2" stroke="currentColor" stroke-width="1.5"/>',
  merge: '<path d="M7 4v12M13 4v12M7 10h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  touch: '<path d="M7 11V7a3 3 0 016 0v4M8 11v3a2 2 0 002 2h0a2 2 0 002-2v-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>',
  functions: '<path d="M5 7c2-2 4-2 6 0s4 2 6 0M5 13c2 2 4 2 6 0s4-2 6 0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>',
  note: '<path d="M5 3h10a1 1 0 011 1v13l-4-3H5a1 1 0 01-1-1V4a1 1 0 011-1z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/>',
  close: '<path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  add: '<path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  compose: '<path d="M11.5 3.8l4.7 4.7L7.2 17H3v-4.2L11.5 3.8z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" fill="none"/><path d="M10.2 5.2l4.6 4.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
  schedule: '<circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M10 6v4.5l3 1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  history: '<circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M10 6v4.5l3 1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
};

function svgInner(name) {
  return PATHS[name] || PATHS.info;
}

export function icon(name, className = 'icon') {
  return `<span class="${className}" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">${svgInner(name)}</svg></span>`;
}

export function spinner(className = 'icon icon-spin') {
  return `<span class="${className}" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.2"/><path d="M10 3a7 7 0 017 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></span>`;
}
