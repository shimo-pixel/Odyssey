const PREFS_KEY = 'prds_prefs';

export function defaultPrefs() {
  return {
    locale: 'zh',
    theme: 'light',
    defaultAgentCount: 10,
    defaultMaxEvents: 6,
    autoOpenResults: true,
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
