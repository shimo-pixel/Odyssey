import * as d3 from 'd3'
import { D3_THEME } from '@/lib/d3GraphTheme'

export type GraphHighlightState = {
  selectedNodeId: string | null
  selectedEdgeId: string | null
  hoveredNodeId: string | null
  hideUnselectedEdges: boolean
  /** Nodes matched by NL search (embed postMessage). */
  searchNodeIds: string[]
  /** Edges between matched search nodes. */
  searchEdgeIds: string[]
  /** Primary entities from the query (e.g. 崔晨). */
  focusNodeIds: string[]
}

type StyledNode = { id: string }
type StyledLink = { id: string; source: unknown; target: unknown }

function linkTouchesNode<L extends StyledLink>(
  link: L,
  nodeId: string | null
): boolean {
  if (!nodeId) {
    return false
  }
  const source = link.source as StyledNode
  const target = link.target as StyledNode
  return source.id === nodeId || target.id === nodeId
}

export function isLinkVisibleForHighlight<L extends StyledLink>(
  link: L,
  state: GraphHighlightState
): boolean {
  const focusNodeId = state.selectedNodeId || state.hoveredNodeId

  if (state.selectedEdgeId === link.id) {
    return true
  }
  if (focusNodeId && linkTouchesNode(link, focusNodeId)) {
    return true
  }
  if (!focusNodeId && !state.selectedEdgeId) {
    return true
  }
  if (state.hideUnselectedEdges) {
    return false
  }
  return true
}

export function refreshGraphHighlight<
  N extends StyledNode,
  L extends StyledLink
>(
  node: d3.Selection<SVGCircleElement, N, SVGGElement, unknown>,
  link: d3.Selection<SVGPathElement, L, SVGGElement, unknown>,
  linkLabels: d3.Selection<SVGTextElement, L, SVGGElement, unknown>,
  linkLabelBg: d3.Selection<SVGRectElement, L, SVGGElement, unknown>,
  state: GraphHighlightState,
  showEdgeLabels: boolean
) {
  applyGraphHighlightStyles(node, link, state)
  const labelDisplay = (d: L) => {
    if (!showEdgeLabels) {
      return 'none'
    }
    return isLinkVisibleForHighlight(d, state) ? null : 'none'
  }
  linkLabels.style('display', labelDisplay)
  linkLabelBg.style('display', labelDisplay)
}

/** MiroFish GraphPanel-style focus: pink neighbor edges, hide or dim the rest. */
export function applyGraphHighlightStyles<
  N extends StyledNode,
  L extends StyledLink
>(
  node: d3.Selection<SVGCircleElement, N, SVGGElement, unknown>,
  link: d3.Selection<SVGPathElement, L, SVGGElement, unknown>,
  state: GraphHighlightState
) {
  const { selectedNodeId, selectedEdgeId, hoveredNodeId, hideUnselectedEdges, searchNodeIds, focusNodeIds } =
    state
  const focusNodeId = selectedNodeId || hoveredNodeId
  const hasSearchFocus = searchNodeIds.length > 0
  const hasLinkFocus = Boolean(focusNodeId || selectedEdgeId)

  node
    .attr('stroke', D3_THEME.nodeStroke)
    .attr('stroke-width', D3_THEME.nodeStrokeWidth)
    .attr('filter', null)
    .attr('opacity', (d) => {
      if (!hasSearchFocus) {
        return 1
      }
      return searchNodeIds.includes(d.id) ? 1 : 0.28
    })

  if (hasSearchFocus) {
    node
      .filter((d) => searchNodeIds.includes(d.id) && !focusNodeIds.includes(d.id))
      .attr('stroke', D3_THEME.edgeConnected)
      .attr('stroke-width', D3_THEME.nodeStrokeWidth + 1.5)
    node
      .filter((d) => focusNodeIds.includes(d.id))
      .attr('stroke', D3_THEME.nodeSearchFocusStroke)
      .attr('stroke-width', D3_THEME.nodeSearchFocusStrokeWidth)
      .attr('filter', 'url(#search-focus-glow)')
  }

  if (selectedNodeId) {
    node
      .filter((d) => d.id === selectedNodeId)
      .attr('stroke', D3_THEME.nodeSelectedStroke)
      .attr('stroke-width', D3_THEME.nodeSelectedStrokeWidth)
  } else if (hoveredNodeId) {
    node
      .filter((d) => d.id === hoveredNodeId)
      .attr('stroke', D3_THEME.nodeHoverStroke)
      .attr('stroke-width', D3_THEME.nodeStrokeWidth + 0.5)
  }

  link.each(function (d) {
    const el = d3.select(this)
    const isConnected = linkTouchesNode(d, focusNodeId)
    const isSelectedEdge = selectedEdgeId === d.id

    el.style('display', null)

    if (isSelectedEdge) {
      el
        .attr('stroke', D3_THEME.edgeSelected)
        .attr('stroke-width', D3_THEME.edgeSelectedWidth)
        .attr('stroke-opacity', 1)
      return
    }

    if (selectedNodeId && isConnected) {
      el
        .attr('stroke', D3_THEME.edgeConnected)
        .attr('stroke-width', D3_THEME.edgeConnectedWidth)
        .attr('stroke-opacity', 1)
      return
    }

    if (hasLinkFocus) {
      if (hideUnselectedEdges && !isConnected) {
        el.style('display', 'none')
        return
      }
      if (!isConnected) {
        el
          .attr('stroke', D3_THEME.edgeDefault)
          .attr('stroke-width', D3_THEME.edgeDefaultWidth)
          .attr('stroke-opacity', D3_THEME.edgeDimOpacity)
        return
      }
    }

    el
      .attr('stroke', D3_THEME.edgeDefault)
      .attr('stroke-width', D3_THEME.edgeDefaultWidth)
      .attr('stroke-opacity', D3_THEME.edgeDefaultOpacity)
  })
}
