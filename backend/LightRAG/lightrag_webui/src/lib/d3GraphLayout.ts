import type { SimulationNodeDatum } from 'd3'

/** Place nodes on a ring when no saved coordinates exist (MiroFish-style clean start). */
export function applyCircularInitialLayout<T extends SimulationNodeDatum>(
  nodes: T[],
  width: number,
  height: number
): void {
  const missing = nodes.filter((n) => n.x == null || n.y == null)
  if (!missing.length) return

  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) * 0.34

  missing.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / missing.length - Math.PI / 2
    node.x = cx + radius * Math.cos(angle)
    node.y = cy + radius * Math.sin(angle)
  })
}

export function graphStructureFingerprint(input: {
  nodes: readonly { id: string }[]
  edges: readonly unknown[]
}): string {
  const ids = input.nodes.map((n) => n.id).sort()
  return `${ids.length}:${ids.join('|')}#${input.edges.length}`
}

/** Layout cache key — only node set matters (edge-only changes keep positions). */
export function graphNodeLayoutFingerprint(
  nodes: readonly { id: string }[]
): string {
  const ids = nodes.map((n) => n.id).sort()
  return `${ids.length}:${ids.join('|')}`
}
