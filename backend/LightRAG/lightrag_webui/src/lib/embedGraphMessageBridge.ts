import { useGraphStore } from '@/stores/graph'
import { useSettingsStore } from '@/stores/settings'
import type { GraphSearchHighlightPayload } from '@/lib/embedGraphMessages'
import {
  isGraphClearSearchHighlightMessage,
  isGraphSearchHighlightMessage,
  isSetThemeMessage
} from '@/lib/embedGraphMessages'

export const SEARCH_HIGHLIGHT_CHANGED = 'lightrag:internal-search-highlight-changed'

type SearchHighlightListener = (payload: GraphSearchHighlightPayload | null) => void

const listeners = new Set<SearchHighlightListener>()

export function onEmbedSearchHighlightChange(listener: SearchHighlightListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function notifySearchHighlight(payload: GraphSearchHighlightPayload | null): void {
  for (const listener of listeners) {
    listener(payload)
  }
  window.dispatchEvent(
    new CustomEvent(SEARCH_HIGHLIGHT_CHANGED, { detail: payload })
  )
}

let bridgeInstalled = false

/** Register postMessage listener as early as possible (before React paint). */
export function installEmbedGraphMessageBridge(): void {
  if (bridgeInstalled || typeof window === 'undefined') {
    return
  }
  bridgeInstalled = true

  window.addEventListener('message', (event: MessageEvent) => {
    const data = event.data
    if (isSetThemeMessage(data)) {
      useSettingsStore.getState().setTheme(data.theme)
      return
    }
    if (isGraphSearchHighlightMessage(data)) {
      const payload = data.payload
      useGraphStore.getState().setSearchHighlight(payload)
      notifySearchHighlight(payload)
      return
    }
    if (isGraphClearSearchHighlightMessage(data)) {
      useGraphStore.getState().clearSearchHighlight()
      notifySearchHighlight(null)
    }
  })
}

installEmbedGraphMessageBridge()
