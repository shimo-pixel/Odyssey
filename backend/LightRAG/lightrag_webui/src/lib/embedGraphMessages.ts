/** postMessage protocol for graph iframe embedding (cpweb → LightRAG WebUI). */

export type GraphSearchHighlightPayload = {
  entityNames: string[]
  relationships: Array<{ source: string; target: string }>
  focusEntityNames?: string[]
  focusQueryLabel?: string
}

export const EMBED_GRAPH_MSG = {
  searchHighlight: 'lightrag:graph-search-highlight',
  clearSearchHighlight: 'lightrag:graph-clear-search-highlight',
  graphReady: 'lightrag:graph-ready',
  setTheme: 'lightrag:set-theme'
} as const

export type EmbedTheme = 'dark' | 'light'

export function isGraphSearchHighlightMessage(
  data: unknown
): data is { type: typeof EMBED_GRAPH_MSG.searchHighlight; payload: GraphSearchHighlightPayload } {
  if (!data || typeof data !== 'object') {
    return false
  }
  const msg = data as { type?: string; payload?: GraphSearchHighlightPayload }
  return msg.type === EMBED_GRAPH_MSG.searchHighlight && Boolean(msg.payload)
}

export function isGraphClearSearchHighlightMessage(data: unknown): boolean {
  return (
    Boolean(data) &&
    typeof data === 'object' &&
    (data as { type?: string }).type === EMBED_GRAPH_MSG.clearSearchHighlight
  )
}

export function isSetThemeMessage(
  data: unknown
): data is { type: typeof EMBED_GRAPH_MSG.setTheme; theme: EmbedTheme } {
  if (!data || typeof data !== 'object') {
    return false
  }
  const msg = data as { type?: string; theme?: string }
  return (
    msg.type === EMBED_GRAPH_MSG.setTheme &&
    (msg.theme === 'dark' || msg.theme === 'light')
  )
}
