const PREFS_KEY = 'prds_prefs';

export function defaultPrefs() {
  return {
    locale: 'zh',
    theme: 'light',
    useMock: true,
    defaultAgentCount: 10,
    defaultPeriods: 6,
    periodTimeUnit: 'month',
    periodTimeLength: 1,
    simulationStartDate: '',
    autoOpenResults: true,
  };
}

export function getPrefs() {
  try {
    return { ...defaultPrefs(), ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') };
  } catch {
    return defaultPrefs();
  }
}

export function savePrefs(prefs) {
  localStorage.setItem(PREFS_KEY, JSON.stringify({ ...getPrefs(), ...prefs }));
}
