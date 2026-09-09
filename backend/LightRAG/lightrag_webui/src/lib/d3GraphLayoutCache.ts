/** Persist D3 node positions per workspace + query label (survives page refresh). */

export type GraphLayoutCache = {
  version: 2
  /** Node-id fingerprint; layout invalidates when nodes are added/removed. */
  nodeFingerprint: string
  positions: Record<string, { x: number; y: number }>
}

const CACHE_VERSION = 2 as const
const KEY_PREFIX = 'lightrag-graph-layout:v1'

function storageKey(workspace: string, queryLabel: string): string {
  const ws = workspace.trim() || '__default__'
  const label = queryLabel.trim() || '*'
  return `${KEY_PREFIX}:${ws}:${label}`
}

export function loadGraphLayoutCache(
  workspace: string,
  queryLabel: string
): GraphLayoutCache | null {
  try {
    const raw = localStorage.getItem(storageKey(workspace, queryLabel))
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as GraphLayoutCache
    if (parsed?.version !== CACHE_VERSION || !parsed.positions) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function saveGraphLayoutCache(
  workspace: string,
  queryLabel: string,
  cache: Omit<GraphLayoutCache, 'version'>
): void {
  try {
    const payload: GraphLayoutCache = { version: CACHE_VERSION, ...cache }
    localStorage.setItem(storageKey(workspace, queryLabel), JSON.stringify(payload))
  } catch {
    // Quota or private mode — ignore
  }
}

export function positionsFromCache(
  cache: GraphLayoutCache | null,
  nodeFingerprint: string
): Map<string, { x: number; y: number }> | null {
  if (!cache || cache.nodeFingerprint !== nodeFingerprint) {
    return null
  }
  return new Map(Object.entries(cache.positions))
}

export function positionsMapToRecord(
  positions: Map<string, { x: number; y: number }>
): Record<string, { x: number; y: number }> {
  const out: Record<string, { x: number; y: number }> = {}
  positions.forEach((value, key) => {
    out[key] = value
  })
  return out
}
