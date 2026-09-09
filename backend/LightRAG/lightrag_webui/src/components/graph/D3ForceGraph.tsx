import { useCallback, useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { SimulationNodeDatum, SimulationLinkDatum } from 'd3'
import { LightragGraphType } from '@/api/lightrag'
import {
  D3_THEME,
  getD3EntityColor,
  getNodeLabel,
  getNodeType,
  truncateLabel
} from '@/lib/d3GraphTheme'
import {
  mirofishLinkDistance,
  mirofishLinkMidpoint,
  mirofishLinkPath,
  prepareMirofishStyleLinks,
  trimLinkEndpoints,
  type SelfLoopGroupMeta
} from '@/lib/d3ParallelEdges'
import {
  refreshGraphHighlight as refreshD3GraphHighlight,
  type GraphHighlightState
} from '@/lib/d3GraphHighlight'
import {
  applyCircularInitialLayout,
  graphNodeLayoutFingerprint
} from '@/lib/d3GraphLayout'
import { resolveGraphSearchHighlight } from '@/lib/d3GraphSearchHighlight'
import { SEARCH_HIGHLIGHT_CHANGED, onEmbedSearchHighlightChange } from '@/lib/embedGraphMessageBridge'
import {
  loadGraphLayoutCache,
  positionsFromCache,
  positionsMapToRecord,
  saveGraphLayoutCache
} from '@/lib/d3GraphLayoutCache'
import { useGraphStore } from '@/stores/graph'
import { useSettingsStore } from '@/stores/settings'
import { useTaskStore } from '@/stores/task'
import D3GraphLegend from '@/components/graph/D3GraphLegend'
import D3NodeDetailPanel from '@/components/graph/D3NodeDetailPanel'
import { Brain, Tags } from 'lucide-react'
import { useTranslation } from 'react-i18next'

type D3Node = SimulationNodeDatum & {
  id: string
  name: string
  entityType: string
  color: string
  rawData: LightragGraphType['nodes'][number]
}

type GraphEdge = LightragGraphType['edges'][number]

type D3Link = SimulationLinkDatum<D3Node> & {
  id: string
  label: string
  curvature: number
  pairTotal: number
  pairIndex: number
  isSelfLoop: boolean
  rawData: GraphEdge | SelfLoopGroupMeta<GraphEdge>
}

interface D3ForceGraphProps {
  graphData: LightragGraphType | null
  loading?: boolean
  isLiveUpdating?: boolean
}

function linkEndpoints(d: D3Link): { sx: number; sy: number; tx: number; ty: number } {
  const source = d.source as D3Node
  const target = d.target as D3Node
  const sx0 = source.x ?? 0
  const sy0 = source.y ?? 0
  const tx0 = target.x ?? 0
  const ty0 = target.y ?? 0
  if (d.isSelfLoop) {
    return { sx: sx0, sy: sy0, tx: tx0, ty: ty0 }
  }
  return trimLinkEndpoints(sx0, sy0, tx0, ty0, D3_THEME.nodeRadius)
}

function getLinkMidpoint(d: D3Link): { x: number; y: number } {
  return mirofishLinkMidpoint(linkEndpoints(d), d)
}

function getLinkPath(d: D3Link): string {
  return mirofishLinkPath(linkEndpoints(d), d)
}

function findNodeByQueryLabel(
  nodes: LightragGraphType['nodes'],
  label: string
): LightragGraphType['nodes'][number] | null {
  if (!label || label === '*') {
    return null
  }
  const byId = nodes.find((n) => n.id === label)
  if (byId) {
    return byId
  }
  return nodes.find((n) => getNodeLabel(n) === label) ?? null
}

function getEdgeDisplayLabel(edge: GraphEdge): string {
  const props = edge.properties ?? {}
  const edgeType =
    typeof props.edge_type === 'string' ? props.edge_type.trim() : ''
  if (edgeType) {
    return edgeType
  }

  const keywords =
    typeof props.keywords === 'string' ? props.keywords.split(',')[0]?.trim() : ''
  if (keywords) {
    return keywords
  }

  if (edge.type && edge.type !== 'DIRECTED') {
    return edge.type
  }

  if (typeof props.description === 'string' && props.description.trim()) {
    return props.description.slice(0, 24)
  }

  return 'RELATED_TO'
}

const LAYOUT_TICKS_PER_NODE = 15
const LAYOUT_MIN_TICKS = 500
const LAYOUT_MAX_TICKS = 2500

function bindLinksToNodes(edges: D3Link[], nodes: D3Node[]): void {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  for (const edge of edges) {
    const sourceId =
      typeof edge.source === 'object'
        ? (edge.source as D3Node).id
        : (edge.source as string)
    const targetId =
      typeof edge.target === 'object'
        ? (edge.target as D3Node).id
        : (edge.target as string)
    const sourceNode = byId.get(sourceId)
    const targetNode = byId.get(targetId)
    if (sourceNode) {
      edge.source = sourceNode
    }
    if (targetNode) {
      edge.target = targetNode
    }
  }
}

function layoutTickBudget(nodeCount: number): number {
  return Math.min(
    LAYOUT_MAX_TICKS,
    Math.max(LAYOUT_MIN_TICKS, 400 + nodeCount * LAYOUT_TICKS_PER_NODE)
  )
}

function layoutForces(nodeCount: number, width: number, height: number) {
  const chargeStrength = -320 - Math.min(480, nodeCount * 3)
  const collideRadius = 44 + Math.min(24, nodeCount * 0.08)
  return {
    chargeStrength,
    collideRadius,
    centerX: width / 2,
    centerY: height / 2
  }
}

function pinNodePositions(nodes: D3Node[]): void {
  for (const node of nodes) {
    if (node.x != null && node.y != null) {
      node.fx = node.x
      node.fy = node.y
    }
  }
}

export default function D3ForceGraph({
  graphData,
  loading = false,
  isLiveUpdating = false
}: D3ForceGraphProps) {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const simulationRef = useRef<d3.Simulation<D3Node, D3Link> | null>(null)
  const positionsRef = useRef<Map<string, { x: number; y: number }>>(new Map())
  const nodeLayoutFingerprintRef = useRef('')
  const layoutFrozenRef = useRef(false)
  const updateVisualsRef = useRef<(() => void) | null>(null)
  const selectedNodeIdRef = useRef<string | null>(null)
  const selectedEdgeIdRef = useRef<string | null>(null)
  const hoveredNodeIdRef = useRef<string | null>(null)
  const nodeSelectionRef = useRef<d3.Selection<
    SVGCircleElement,
    D3Node,
    SVGGElement,
    unknown
  > | null>(null)
  const linkSelectionRef = useRef<d3.Selection<
    SVGPathElement,
    D3Link,
    SVGGElement,
    unknown
  > | null>(null)
  const linkLabelSelectionRef = useRef<d3.Selection<
    SVGTextElement,
    D3Link,
    SVGGElement,
    unknown
  > | null>(null)
  const linkLabelBgSelectionRef = useRef<d3.Selection<
    SVGRectElement,
    D3Link,
    SVGGElement,
    unknown
  > | null>(null)
  const queryLabel = useSettingsStore.use.queryLabel()
  const showEdgeLabels = useSettingsStore.use.showEdgeLabel()
  const hideUnselectedEdges = useSettingsStore.use.enableHideUnselectedEdges()
  const currentWorkspace = useTaskStore.use.currentWorkspace()
  const searchHighlight = useGraphStore.use.searchHighlight()
  const searchHighlightRef = useRef<{
    nodeIds: string[]
    edgeIds: string[]
    focusNodeIds: string[]
  }>({
    nodeIds: [],
    edgeIds: [],
    focusNodeIds: []
  })
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const graphGroupRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null)
  const graphNodesRef = useRef<D3Node[]>([])
  const prevQueryLabelRef = useRef<string | null>(queryLabel)
  const [selectedNode, setSelectedNode] = useState<LightragGraphType['nodes'][number] | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<LightragGraphType['nodes'][number] | null>(null)
  const [hoveredColor, setHoveredColor] = useState('#3498db')
  const [selectedColor, setSelectedColor] = useState('#3498db')
  const hoverClearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cancelHoverClear = useCallback(() => {
    if (hoverClearTimerRef.current) {
      clearTimeout(hoverClearTimerRef.current)
      hoverClearTimerRef.current = null
    }
  }, [])

  const clearHover = useCallback(() => {
    cancelHoverClear()
    setHoveredNode(null)
    setHoveredNodeId(null)
  }, [cancelHoverClear])

  const scheduleHoverClear = useCallback(() => {
    cancelHoverClear()
    hoverClearTimerRef.current = setTimeout(() => {
      setHoveredNode(null)
      setHoveredNodeId(null)
      hoverClearTimerRef.current = null
    }, 220)
  }, [cancelHoverClear])

  const panelNode = hoveredNode ?? selectedNode
  const panelColor = hoveredNode ? hoveredColor : selectedColor

  const getHighlightState = useCallback((): GraphHighlightState => ({
    selectedNodeId: selectedNodeIdRef.current,
    selectedEdgeId: selectedEdgeIdRef.current,
    hoveredNodeId: hoveredNodeIdRef.current,
    hideUnselectedEdges,
    searchNodeIds: searchHighlightRef.current.nodeIds,
    searchEdgeIds: searchHighlightRef.current.edgeIds,
    focusNodeIds: searchHighlightRef.current.focusNodeIds
  }), [hideUnselectedEdges])

  const zoomToSearchFocus = useCallback((targetIds: string[]) => {
    if (!targetIds.length || !svgRef.current || !containerRef.current || !zoomBehaviorRef.current) {
      return
    }
    const width = containerRef.current.clientWidth || 800
    const height = containerRef.current.clientHeight || 600
    const targets = graphNodesRef.current.filter(
      (node) => targetIds.includes(node.id) && node.x != null && node.y != null
    )
    if (!targets.length) {
      return
    }

    const cx =
      targets.reduce((sum, node) => sum + (node.x as number), 0) / targets.length
    const cy =
      targets.reduce((sum, node) => sum + (node.y as number), 0) / targets.length
    const scale = d3.zoomTransform(svgRef.current).k
    const transform = d3.zoomIdentity
      .translate(width / 2 - cx * scale, height / 2 - cy * scale)
      .scale(scale)

    d3.select(svgRef.current)
      .transition()
      .duration(650)
      .call(zoomBehaviorRef.current.transform, transform)
  }, [])

  const applyHighlight = useCallback(() => {
    if (
      !nodeSelectionRef.current ||
      !linkSelectionRef.current ||
      !linkLabelSelectionRef.current ||
      !linkLabelBgSelectionRef.current
    ) {
      return
    }
    refreshD3GraphHighlight(
      nodeSelectionRef.current,
      linkSelectionRef.current,
      linkLabelSelectionRef.current,
      linkLabelBgSelectionRef.current,
      getHighlightState(),
      showEdgeLabels
    )
  }, [getHighlightState, showEdgeLabels])

  const applySearchHighlightFromStore = useCallback(() => {
    if (!graphData) {
      searchHighlightRef.current = { nodeIds: [], edgeIds: [], focusNodeIds: [] }
      applyHighlight()
      return
    }

    searchHighlightRef.current = resolveGraphSearchHighlight(
      graphData,
      useGraphStore.getState().searchHighlight
    )
    applyHighlight()

    const { nodeIds } = searchHighlightRef.current
    const activeHighlight = useGraphStore.getState().searchHighlight
    if (nodeIds.length > 0 && activeHighlight) {
      window.setTimeout(() => zoomToSearchFocus(nodeIds), 150)
    }
  }, [graphData, applyHighlight, zoomToSearchFocus])

  useEffect(() => {
    applySearchHighlightFromStore()
  }, [graphData, searchHighlight, applySearchHighlightFromStore])

  useEffect(() => {
    const offBridge = onEmbedSearchHighlightChange(() => {
      applySearchHighlightFromStore()
    })
    const onDomEvent = () => applySearchHighlightFromStore()
    window.addEventListener(SEARCH_HIGHLIGHT_CHANGED, onDomEvent)
    return () => {
      offBridge()
      window.removeEventListener(SEARCH_HIGHLIGHT_CHANGED, onDomEvent)
    }
  }, [applySearchHighlightFromStore])

  useEffect(() => {
    if (!graphData?.nodes?.length || window.parent === window) {
      return
    }
    window.parent.postMessage({ type: 'lightrag:graph-ready' }, '*')
  }, [graphData])

  const clearSelection = useCallback(() => {
    setSelectedNode(null)
    setSelectedEdgeId(null)
    clearHover()
    useGraphStore.getState().clearSelection()
    const store = useGraphStore.getState()
    if (store.searchHighlight) {
      store.clearSearchHighlight()
    }
  }, [clearHover])

  useEffect(() => {
    selectedNodeIdRef.current = selectedNode?.id ?? null
    selectedEdgeIdRef.current = selectedEdgeId
    hoveredNodeIdRef.current = hoveredNodeId
    applyHighlight()
  }, [selectedNode, selectedEdgeId, hoveredNodeId, hideUnselectedEdges, showEdgeLabels, applyHighlight])

  useEffect(() => {
    if (!graphData) {
      clearSelection()
      return
    }

    if (selectedNode && !graphData.nodes.some((n) => n.id === selectedNode.id)) {
      clearSelection()
    }
  }, [graphData, selectedNode, clearSelection])

  useEffect(() => {
    if (!graphData) {
      clearSelection()
      return
    }

    const labelChanged = prevQueryLabelRef.current !== queryLabel
    prevQueryLabelRef.current = queryLabel

    if (!queryLabel || queryLabel === '*') {
      if (labelChanged) {
        clearSelection()
      }
      return
    }

    const match = findNodeByQueryLabel(graphData.nodes, queryLabel)
    if (!match) {
      return
    }
    const entityType = getNodeType(match)
    const { color } = getD3EntityColor(
      entityType,
      useGraphStore.getState().typeColorMap
    )
    setSelectedNode(match)
    setSelectedColor(color)
    useGraphStore.getState().setSelectedNode(match.id)
  }, [graphData, queryLabel, clearSelection])

  const persistLayout = useCallback(
    (nodes: D3Node[], nodeFingerprint: string) => {
      const map = new Map<string, { x: number; y: number }>()
      for (const node of nodes) {
        if (node.x != null && node.y != null) {
          map.set(node.id, { x: node.x, y: node.y })
        }
      }
      positionsRef.current = map
      saveGraphLayoutCache(currentWorkspace, queryLabel || '*', {
        nodeFingerprint,
        positions: positionsMapToRecord(map)
      })
    },
    [currentWorkspace, queryLabel]
  )

  const renderGraph = useCallback(() => {
    if (!graphData || !svgRef.current || !containerRef.current) {
      return
    }

    const width = containerRef.current.clientWidth || 800
    const height = containerRef.current.clientHeight || 600
    const nodeFingerprint = graphNodeLayoutFingerprint(graphData.nodes)
    const labelKey = queryLabel || '*'

    if (simulationRef.current) {
      simulationRef.current.stop()
      simulationRef.current = null
    }

    const cachedPositions =
      positionsFromCache(loadGraphLayoutCache(currentWorkspace, labelKey), nodeFingerprint) ??
      null

    const mergedPositions = new Map<string, { x: number; y: number }>()
    cachedPositions?.forEach((value, key) => mergedPositions.set(key, value))
    positionsRef.current.forEach((value, key) => {
      if (!mergedPositions.has(key)) {
        mergedPositions.set(key, value)
      }
    })

    nodeLayoutFingerprintRef.current = nodeFingerprint

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('width', width).attr('height', height)

    const defs = svg.append('defs')
    const glow = defs
      .append('filter')
      .attr('id', 'search-focus-glow')
      .attr('x', '-80%')
      .attr('y', '-80%')
      .attr('width', '260%')
      .attr('height', '260%')
    glow.append('feGaussianBlur').attr('stdDeviation', '3.5').attr('result', 'blur')
    glow
      .append('feMerge')
      .selectAll('feMergeNode')
      .data(['blur', 'SourceGraphic'])
      .enter()
      .append('feMergeNode')
      .attr('in', (d) => d)

    const getColor = (entityType: string) => {
      const { color, map, updated } = getD3EntityColor(
        entityType,
        useGraphStore.getState().typeColorMap
      )
      if (updated) {
        useGraphStore.getState().setTypeColorMap(map)
      }
      return color
    }

    const nodeMap: Record<string, LightragGraphType['nodes'][number]> = {}
    graphData.nodes.forEach((n) => {
      nodeMap[n.id] = n
    })

    const nodes: D3Node[] = graphData.nodes.map((n) => {
      const saved = mergedPositions.get(n.id)
      return {
        id: n.id,
        name: getNodeLabel(n),
        entityType: getNodeType(n),
        color: getColor(getNodeType(n)),
        rawData: n,
        x: saved?.x,
        y: saved?.y
      }
    })

    const validGraphEdges = graphData.edges.filter(
      (e) => nodeMap[e.source] && nodeMap[e.target]
    )

    const preparedLinks = prepareMirofishStyleLinks(validGraphEdges, getEdgeDisplayLabel)

    const edges: D3Link[] = preparedLinks.map((link) => ({
      id: link.id,
      source: link.source,
      target: link.target,
      label: link.label,
      curvature: link.curvature,
      pairTotal: link.pairTotal,
      pairIndex: link.pairIndex,
      isSelfLoop: link.isSelfLoop,
      rawData: link.rawData
    }))

    if (nodes.length === 0) {
      return
    }

    graphNodesRef.current = nodes
    searchHighlightRef.current = resolveGraphSearchHighlight(
      graphData,
      useGraphStore.getState().searchHighlight
    )

    bindLinksToNodes(edges, nodes)

    const allPositionsKnown = nodes.every((n) => n.x != null && n.y != null)
    layoutFrozenRef.current = allPositionsKnown

    if (!allPositionsKnown) {
      applyCircularInitialLayout(nodes, width, height)
      for (const node of nodes) {
        if (node.x != null && node.y != null && mergedPositions.has(node.id)) {
          node.fx = node.x
          node.fy = node.y
        }
      }
    } else {
      pinNodePositions(nodes)
    }

    const g = svg.append('g')
    graphGroupRef.current = g

    // Transparent background rect to reliably capture blank-area clicks (clears search highlight).
    g.append('rect')
      .attr('class', 'graph-background')
      .attr('x', -width * 4)
      .attr('y', -height * 4)
      .attr('width', width * 9)
      .attr('height', height * 9)
      .attr('fill', 'transparent')
      .style('pointer-events', 'all')
      .on('click', (event) => {
        event.stopPropagation()
        clearSelection()
      })

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .extent([
        [0, 0],
        [width, height]
      ])
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })
    zoomBehaviorRef.current = zoom

    svg
      .call(zoom)
      .on('click', () => {
        clearSelection()
      })

    g.on('click', () => {
      clearSelection()
    })

    const linkGroup = g.append('g').attr('class', 'links')
    const link = linkGroup
      .selectAll('path')
      .data(edges)
      .enter()
      .append('path')
      .attr('stroke', D3_THEME.edgeDefault)
      .attr('stroke-width', D3_THEME.edgeDefaultWidth)
      .attr('stroke-opacity', D3_THEME.edgeDefaultOpacity)
      .attr('fill', 'none')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        setSelectedEdgeId(d.id)
        setSelectedNode(null)
        useGraphStore.getState().clearSelection()
      })

    const edgeLabelGroup = g.append('g').attr('class', 'edge-labels')
    const linkLabelBg = edgeLabelGroup
      .selectAll('rect')
      .data(edges, (d: D3Link) => d.id)
      .enter()
      .append('rect')
      .attr('rx', 4)
      .attr('ry', 4)
      .attr('fill', D3_THEME.edgeLabelBg)
      .style('pointer-events', 'none')

    const linkLabels = edgeLabelGroup
      .selectAll('text')
      .data(edges, (d: D3Link) => d.id)
      .enter()
      .append('text')
      .text((d) => truncateLabel(d.label, 12))
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', `${D3_THEME.edgeLabelFontSize}px`)
      .attr('fill', D3_THEME.edgeLabelColor)
      .attr('font-family', D3_THEME.graphFont)
      .style('pointer-events', 'none')

    const nodeGroup = g.append('g').attr('class', 'nodes')
    const node = nodeGroup
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('r', D3_THEME.nodeRadius)
      .attr('fill', (d) => d.color)
      .attr('stroke', D3_THEME.nodeStroke)
      .attr('stroke-width', D3_THEME.nodeStrokeWidth)
      .style('cursor', 'pointer')

    const nodeLabels = nodeGroup
      .selectAll('text.node-label')
      .data(nodes)
      .enter()
      .append('text')
      .attr('class', 'node-label')
      .text((d) => truncateLabel(d.name))
      .attr('font-size', `${D3_THEME.nodeLabelFontSize}px`)
      .attr('fill', '#333333')
      .attr('font-family', D3_THEME.graphFont)
      .attr('dx', 14)
      .attr('dy', 4)
      .style('pointer-events', 'none')

    nodeSelectionRef.current = node
    linkSelectionRef.current = link
    linkLabelSelectionRef.current = linkLabels
    linkLabelBgSelectionRef.current = linkLabelBg

    const updateVisuals = () => {
      link.attr('d', (d) => getLinkPath(d))
      node.attr('cx', (d) => d.x ?? 0).attr('cy', (d) => d.y ?? 0)
      nodeLabels.attr('x', (d) => d.x ?? 0).attr('y', (d) => d.y ?? 0)

      linkLabels.each(function (d) {
        const mid = getLinkMidpoint(d)
        d3.select(this).attr('x', mid.x).attr('y', mid.y).attr('transform', '')
      })

      linkLabelBg.each(function (d, i) {
        const mid = getLinkMidpoint(d)
        const textEl = linkLabels.nodes()[i] as SVGTextElement | undefined
        const bbox = textEl?.getBBox()
        if (!bbox) return
        d3.select(this)
          .attr('x', mid.x - bbox.width / 2 - 4)
          .attr('y', mid.y - bbox.height / 2 - 2)
          .attr('width', bbox.width + 8)
          .attr('height', bbox.height + 4)
          .attr('transform', '')
      })
    }
    updateVisualsRef.current = updateVisuals

    let layoutFinalized = false
    const finalizeLayout = () => {
      if (layoutFinalized) {
        return
      }
      layoutFinalized = true
      simulationRef.current?.stop()
      simulationRef.current = null
      pinNodePositions(nodes)
      layoutFrozenRef.current = true
      persistLayout(nodes, nodeFingerprint)
      updateVisuals()
    }

    node.call(
      d3
        .drag<SVGCircleElement, D3Node>()
        .on('start', (event, d) => {
          if (!layoutFrozenRef.current && !event.active) {
            simulationRef.current?.alphaTarget(0.15).restart()
          }
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
          d.x = event.x
          d.y = event.y
          if (layoutFrozenRef.current) {
            updateVisuals()
            positionsRef.current.set(d.id, { x: d.x, y: d.y })
            saveGraphLayoutCache(currentWorkspace, labelKey, {
              nodeFingerprint,
              positions: positionsMapToRecord(positionsRef.current)
            })
          }
        })
        .on('end', (event, d) => {
          if (layoutFrozenRef.current) {
            d.fx = d.x
            d.fy = d.y
            persistLayout(nodes, nodeFingerprint)
            return
          }
          if (!event.active) {
            simulationRef.current?.alphaTarget(0)
          }
          d.fx = null
          d.fy = null
        })
    )
      .on('click', (event, d) => {
        event.stopPropagation()
        setSelectedEdgeId(null)
        setSelectedNode(d.rawData)
        setSelectedColor(d.color)
        useGraphStore.getState().setSelectedNode(d.id)
      })
      .on('mouseenter', (_event, d) => {
        cancelHoverClear()
        setHoveredNodeId(d.id)
        setHoveredNode(d.rawData)
        setHoveredColor(d.color)
      })
      .on('mouseleave', (_event, d) => {
        setHoveredNodeId((current) => (current === d.id ? null : current))
        scheduleHoverClear()
      })

    refreshD3GraphHighlight(node, link, linkLabels, linkLabelBg, getHighlightState(), showEdgeLabels)

    if (layoutFrozenRef.current) {
      updateVisuals()
      return
    }

    const { chargeStrength, collideRadius, centerX, centerY } = layoutForces(
      nodes.length,
      width,
      height
    )
    const maxTicks = layoutTickBudget(nodes.length)

    const simulation = d3
      .forceSimulation(nodes)
      .velocityDecay(0.3)
      .alphaMin(0.001)
      .alpha(1)
      .force(
        'link',
        d3
          .forceLink<D3Node, D3Link>(edges)
          .id((d) => d.id)
          .distance((d) => mirofishLinkDistance(d.pairTotal || 1))
          .strength(0.55)
      )
      .force('charge', d3.forceManyBody().strength(chargeStrength))
      .force('center', d3.forceCenter(centerX, centerY))
      .force('collide', d3.forceCollide(collideRadius))
      .force('x', d3.forceX(centerX).strength(0.02))
      .force('y', d3.forceY(centerY).strength(0.02))

    simulationRef.current = simulation

    let tickCount = 0
    simulation.on('tick', () => {
      tickCount += 1
      updateVisuals()
      if (tickCount >= maxTicks) {
        finalizeLayout()
      }
    })
    simulation.on('end', () => {
      finalizeLayout()
    })
  }, [
    graphData,
    clearSelection,
    getHighlightState,
    currentWorkspace,
    queryLabel,
    persistLayout,
    cancelHoverClear,
    scheduleHoverClear
  ])

  useEffect(() => () => cancelHoverClear(), [cancelHoverClear])

  useEffect(() => {
    renderGraph()
    return () => {
      simulationRef.current?.stop()
    }
  }, [renderGraph])

  useEffect(() => {
    const onResize = () => {
      if (!svgRef.current || !containerRef.current) {
        return
      }
      const width = containerRef.current.clientWidth || 800
      const height = containerRef.current.clientHeight || 600
      d3.select(svgRef.current).attr('width', width).attr('height', height)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const showStatusCapsule = (isLiveUpdating || loading) && graphData

  return (
    <div
      ref={containerRef}
      className="kg-dot-canvas relative h-full w-full overflow-hidden"
    >
      <button
        type="button"
        onClick={() =>
          useSettingsStore.setState((pre) => ({
            showEdgeLabel: !pre.showEdgeLabel
          }))
        }
        className={`absolute top-3 z-30 flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium shadow-sm transition-all ${
          panelNode ? 'right-[336px]' : 'right-3'
        } ${
          showEdgeLabels
            ? 'border-[#7B2D8E]/30 bg-white text-[#7B2D8E]'
            : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
        }`}
        style={{ fontFamily: D3_THEME.graphFont }}
        title={t('graphPanel.d3.edgeLabelsToggle', 'Toggle edge labels')}
      >
        <Tags className="size-3.5" />
        {t('graphPanel.d3.edgeLabels', 'Edge labels')}
      </button>

      {!graphData && !loading && (
        <div
          className="flex h-full items-center justify-center text-sm text-gray-500"
          style={{ fontFamily: D3_THEME.graphFont }}
        >
          {t('graphPanel.d3.empty', 'Select a label to load the knowledge graph')}
        </div>
      )}

      <svg ref={svgRef} className="relative z-10 h-full w-full" />

      {graphData && <D3GraphLegend />}

      {panelNode && (
        <D3NodeDetailPanel
          node={panelNode}
          entityColor={panelColor}
          onClose={clearSelection}
          onMouseEnter={cancelHoverClear}
          onMouseLeave={scheduleHoverClear}
        />
      )}

      {showStatusCapsule && (
        <div className="pointer-events-none absolute inset-x-0 bottom-6 z-30 flex justify-center">
          <div
            className="flex items-center gap-2 rounded-full px-5 py-2 text-sm text-white shadow-lg backdrop-blur-md"
            style={{ backgroundColor: D3_THEME.statusCapsuleBg }}
          >
            <Brain className="kg-breathe-icon size-4 text-white/90" />
            <span style={{ fontFamily: D3_THEME.graphFont }}>
              {isLiveUpdating
                ? t('graphPanel.d3.simulating', 'Simulating knowledge graph…')
                : t('graphPanel.d3.loading', 'Loading graph…')}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
