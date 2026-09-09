/**
 * Parallel-edge and self-loop layout aligned with MiroFish GraphPanel.vue.
 * @see /home/shimo/MiroFish-local/frontend/src/components/GraphPanel.vue
 */

export type LinkCurveLayout = {
  curvature: number
  pairIndex: number
  pairTotal: number
  isSelfLoop: boolean
}

export type LinkEndpoints = {
  sx: number
  sy: number
  tx: number
  ty: number
}

export type SelfLoopGroupMeta<T> = {
  isSelfLoopGroup: true
  selfLoopCount: number
  selfLoopEdges: T[]
}

export type PreparedMirofishLink<T> = LinkCurveLayout & {
  id: string
  source: string
  target: string
  label: string
  rawData: T | SelfLoopGroupMeta<T>
}

function pairKey(source: string, target: string): string {
  return [source, target].sort().join('_')
}

/** MiroFish curvature: fan out multi-edges; flip sign when source > target. */
export function computeMirofishCurvature(
  source: string,
  target: string,
  currentIndex: number,
  totalCount: number
): number {
  if (totalCount > 1) {
    const isReversed = source > target
    const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
    let curvature =
      (currentIndex / (totalCount - 1) - 0.5) * curvatureRange * 2

    if (isReversed) {
      curvature = -curvature
    }

    return curvature
  }

  return 0
}

/** Perpendicular offset magnitude for quadratic Bézier control point. */
export function mirofishEdgeBaseOffset(distance: number, pairTotal: number): number {
  const offsetRatio = 0.25 + pairTotal * 0.05
  return Math.max(35, distance * offsetRatio)
}

/** Trim link endpoints to node circle perimeters (MiroFish-style). */
export function trimLinkEndpoints(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  nodeRadius: number
): LinkEndpoints {
  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy) || 1
  const trim = Math.min(nodeRadius, dist / 2 - 0.5)
  if (trim <= 0) {
    return { sx, sy, tx, ty }
  }
  const ux = dx / dist
  const uy = dy / dist
  return {
    sx: sx + ux * trim,
    sy: sy + uy * trim,
    tx: tx - ux * trim,
    ty: ty - uy * trim
  }
}

export function mirofishLinkPath(
  endpoints: LinkEndpoints,
  layout: LinkCurveLayout
): string {
  const { sx, sy, tx, ty } = endpoints

  if (layout.isSelfLoop) {
    const loopRadius = 30
    const x1 = sx + 8
    const y1 = sy - 4
    const x2 = sx + 8
    const y2 = sy + 4
    return `M${x1},${y1} A${loopRadius},${loopRadius} 0 1,1 ${x2},${y2}`
  }

  if (layout.curvature === 0) {
    return `M${sx},${sy} L${tx},${ty}`
  }

  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy) || 1
  const pairTotal = layout.pairTotal || 1
  const baseOffset = mirofishEdgeBaseOffset(dist, pairTotal)
  const offsetX = (-dy / dist) * layout.curvature * baseOffset
  const offsetY = (dx / dist) * layout.curvature * baseOffset
  const cx = (sx + tx) / 2 + offsetX
  const cy = (sy + ty) / 2 + offsetY

  return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
}

export function mirofishLinkMidpoint(
  endpoints: LinkEndpoints,
  layout: LinkCurveLayout
): { x: number; y: number } {
  const { sx, sy, tx, ty } = endpoints

  if (layout.isSelfLoop) {
    return { x: sx + 70, y: sy }
  }

  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy) || 1
  const pairTotal = layout.pairTotal || 1
  const baseOffset = mirofishEdgeBaseOffset(dist, pairTotal)
  const offsetX = (-dy / dist) * layout.curvature * baseOffset
  const offsetY = (dx / dist) * layout.curvature * baseOffset
  const cx = (sx + tx) / 2 + offsetX
  const cy = (sy + ty) / 2 + offsetY

  return {
    x: 0.25 * sx + 0.5 * cx + 0.25 * tx,
    y: 0.25 * sy + 0.5 * cy + 0.25 * ty
  }
}

export function mirofishLinkDistance(pairTotal: number): number {
  return 150 + (pairTotal - 1) * 50
}

/**
 * Prepare D3 link rows: merge self-loops per node; assign symmetric curvature
 * for multiple edges between the same undirected pair.
 */
export function prepareMirofishStyleLinks<T extends { source: string; target: string; id: string }>(
  edges: readonly T[],
  getLabel: (edge: T) => string
): PreparedMirofishLink<T>[] {
  const edgePairCount: Record<string, number> = {}
  const selfLoopEdges: Record<string, T[]> = {}
  const edgePairIndex: Record<string, number> = {}
  const processedSelfLoopNodes = new Set<string>()
  const result: PreparedMirofishLink<T>[] = []

  edges.forEach((edge) => {
    if (edge.source === edge.target) {
      if (!selfLoopEdges[edge.source]) {
        selfLoopEdges[edge.source] = []
      }
      selfLoopEdges[edge.source].push(edge)
      return
    }

    const key = pairKey(edge.source, edge.target)
    edgePairCount[key] = (edgePairCount[key] || 0) + 1
  })

  edges.forEach((edge) => {
    if (edge.source === edge.target) {
      if (processedSelfLoopNodes.has(edge.source)) {
        return
      }
      processedSelfLoopNodes.add(edge.source)

      const allSelfLoops = selfLoopEdges[edge.source] ?? [edge]
      result.push({
        id: `self-loop:${edge.source}`,
        source: edge.source,
        target: edge.target,
        label: `Self Relations (${allSelfLoops.length})`,
        curvature: 0,
        pairIndex: 0,
        pairTotal: 1,
        isSelfLoop: true,
        rawData: {
          isSelfLoopGroup: true,
          selfLoopCount: allSelfLoops.length,
          selfLoopEdges: allSelfLoops
        }
      })
      return
    }

    const key = pairKey(edge.source, edge.target)
    const totalCount = edgePairCount[key] || 1
    const currentIndex = edgePairIndex[key] || 0
    edgePairIndex[key] = currentIndex + 1

    result.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: getLabel(edge),
      curvature: computeMirofishCurvature(
        edge.source,
        edge.target,
        currentIndex,
        totalCount
      ),
      pairIndex: currentIndex,
      pairTotal: totalCount,
      isSelfLoop: false,
      rawData: edge
    })
  })

  return result
}
