import type { LightragGraphType } from '@/api/lightrag'

/** Academic / infographic palette — cycles by entity type */
export const D3_ENTITY_PALETTE = [
  '#FF6B35',
  '#004E89',
  '#7B2D8E',
  '#1A936F',
  '#C5283D',
  '#E9724C',
  '#3498db',
  '#9b59b6',
  '#27ae60',
  '#f39c12'
] as const

export const D3_THEME = {
  canvasBg: '#FAFAFA',
  dotColor: '#D0D0D0',
  dotSpacing: 24,
  nodeRadius: 10,
  nodeStroke: '#ffffff',
  nodeStrokeWidth: 2.5,
  nodeHoverStroke: '#333333',
  nodeSelectedStroke: '#E91E63',
  nodeSelectedStrokeWidth: 4,
  nodeSearchFocusStroke: '#FF1744',
  nodeSearchFocusStrokeWidth: 6,
  edgeDefault: '#C0C0C0',
  edgeDefaultWidth: 1.5,
  /** MiroFish Process.vue-style baseline fade for dense graphs */
  edgeDefaultOpacity: 0.45,
  /** Non-focused edges when a node/edge is selected or hovered */
  edgeDimOpacity: 0.12,
  edgeConnected: '#E91E63',
  edgeConnectedWidth: 2.5,
  edgeSelected: '#3498db',
  edgeSelectedWidth: 3,
  edgeLabelColor: '#666666',
  edgeLabelFontSize: 9,
  edgeLabelBg: 'rgba(255,255,255,0.85)',
  nodeLabelFontSize: 11,
  nodeLabelMaxChars: 8,
  accentPurple: '#7B2D8E',
  graphFont: 'system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
  detailFont: "'Noto Sans SC', system-ui, sans-serif",
  monoFont: "'JetBrains Mono', ui-monospace, monospace",
  statusCapsuleBg: 'rgba(0,0,0,0.65)'
} as const

export function getNodeLabel(node: LightragGraphType['nodes'][number]): string {
  const label =
    node.properties?.entity_id ||
    node.properties?.name ||
    node.labels?.find((l) => l !== '*') ||
    node.id
  return label == null ? '' : String(label)
}

export function getNodeType(node: LightragGraphType['nodes'][number]): string {
  return node.properties?.entity_type || node.labels?.[0] || 'entity'
}

export function truncateLabel(text: string, max = D3_THEME.nodeLabelMaxChars): string {
  if (text.length <= max) {
    return text
  }
  return `${text.slice(0, max)}…`
}

export function getD3EntityColor(
  entityType: string,
  typeColorMap: Map<string, string> | Record<string, string> | undefined
): { color: string; map: Map<string, string>; updated: boolean } {
  const map =
    typeColorMap instanceof Map
      ? typeColorMap
      : new Map(Object.entries(typeColorMap ?? {}))
  const key = (entityType || 'entity').toLowerCase().trim() || 'entity'

  if (map.has(key)) {
    return { color: map.get(key)!, map, updated: false }
  }

  const color = D3_ENTITY_PALETTE[map.size % D3_ENTITY_PALETTE.length]
  const newMap = new Map(map)
  newMap.set(key, color)
  return { color, map: newMap, updated: true }
}

export function isMonoPropertyKey(key: string): boolean {
  return /^(id|uuid|episode|chunk|doc|source|target)$/i.test(key)
}
