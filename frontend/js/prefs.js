const PREFS_KEY = 'prds_prefs';

export function defaultPrefs() {
  return {
    locale: 'zh',
    theme: 'light',
    // Number of coping strategies explored in parallel (one KB branch each).
    defaultAgentCount: 4,
    defaultMaxEvents: 6,
    autoOpenResults: true,
    maxConcurrentLlm: 20,
    selectedModelId: '',
  };
}

export function getPrefs() {
  try {
    const stored = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    const prefs = { ...defaultPrefs(), ...stored };
    if (stored.defaultPeriods != null && stored.defaultMaxEvents == null) {
      prefs.defaultMaxEvents = stored.defaultPeriods;
    }
    return prefs;
  } catch {
    return defaultPrefs();
  }
}

export function savePrefs(prefs) {
  localStorage.setItem(PREFS_KEY, JSON.stringify({ ...getPrefs(), ...prefs }));
}
