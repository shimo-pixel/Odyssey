import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ThemeProvider from '@/components/ThemeProvider'
import ErrorBoundary from '@/components/ErrorBoundary'
import GraphViewer from '@/features/GraphViewer'
import { getAuthStatus } from '@/api/lightrag'
import { useAuthStore } from '@/stores/state'
import { useSettingsStore } from '@/stores/settings'
import { useTaskStore } from '@/stores/task'
import '@/lib/embedGraphMessageBridge'
import i18n from '@/i18n'

/**
 * Chromeless knowledge-graph view for iframe embedding in external apps.
 * Query params:
 * - workspace: LightRAG workspace id (e.g. task_id_2)
 * - lang: UI language (defaults to zh)
 * - theme: light | dark (follows host app appearance)
 */
export default function GraphEmbedApp() {
  const [searchParams] = useSearchParams()
  const workspace = (searchParams.get('workspace') || '').trim()
  const embedLang = (searchParams.get('lang') || 'zh').trim() as
    | 'zh'
    | 'en'
    | 'zh_TW'
  const embedTheme = (searchParams.get('theme') || '').trim()
  const [initializing, setInitializing] = useState(true)
  const initRef = useRef(false)

  useLayoutEffect(() => {
    if (embedTheme === 'dark' || embedTheme === 'light') {
      useSettingsStore.getState().setTheme(embedTheme)
    }
  }, [embedTheme])

  const bootstrap = useCallback(async () => {
    if (initRef.current) return
    initRef.current = true

    try {
      if (embedTheme === 'dark' || embedTheme === 'light') {
        useSettingsStore.getState().setTheme(embedTheme)
      }
      useSettingsStore.getState().setLanguage(embedLang)
      void i18n.changeLanguage(embedLang)
      useSettingsStore.getState().setCurrentTab('knowledge-graph')
      useSettingsStore.getState().setEnableHealthCheck(false)

      const status = await getAuthStatus()
      const token = localStorage.getItem('LIGHTRAG-API-TOKEN')

      if (!status.auth_configured && status.access_token) {
        useAuthStore.getState().login(
          status.access_token,
          true,
          status.core_version,
          status.api_version,
          status.webui_title || null,
          status.webui_description || null
        )
      } else if (token) {
        const isGuestMode =
          status.auth_mode === 'disabled' || useAuthStore.getState().isGuestMode
        useAuthStore.getState().login(
          token,
          isGuestMode,
          status.core_version,
          status.api_version,
          status.webui_title || null,
          status.webui_description || null
        )
      }

      await useTaskStore.getState().refreshWorkspaces()
      if (workspace) {
        useTaskStore.getState().setCurrentWorkspace(workspace)
      }
    } catch (error) {
      console.error('Graph embed initialization failed:', error)
    } finally {
      setInitializing(false)
    }
  }, [workspace, embedLang, embedTheme])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  return (
    <ThemeProvider>
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-background">
        {initializing ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <div className="border-primary mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" />
              <p className="text-muted-foreground text-sm">正在加载图谱…</p>
            </div>
          </div>
        ) : (
          <div className="min-h-0 flex-1">
            <ErrorBoundary>
              <GraphViewer />
            </ErrorBoundary>
          </div>
        )}
      </div>
    </ThemeProvider>
  )
}
