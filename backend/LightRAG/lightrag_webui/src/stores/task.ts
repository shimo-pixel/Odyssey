import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { createSelectors } from '@/lib/utils'
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  type WorkspaceInfo
} from '@/api/lightrag'

interface TaskState {
  currentWorkspace: string
  workspaces: WorkspaceInfo[]
  defaultWorkspace: string
  loading: boolean

  setCurrentWorkspace: (workspace: string) => void
  refreshWorkspaces: () => Promise<void>
  addWorkspace: (id: string, name?: string) => Promise<void>
  removeWorkspace: (id: string) => Promise<void>
}

const useTaskStoreBase = create<TaskState>()(
  persist(
    (set, get) => ({
      currentWorkspace: '',
      workspaces: [],
      defaultWorkspace: '',
      loading: false,

      setCurrentWorkspace: (workspace: string) => {
        if (workspace === get().currentWorkspace) {
          return
        }
        set({ currentWorkspace: workspace })
      },

      refreshWorkspaces: async () => {
        set({ loading: true })
        try {
          const response = await listWorkspaces()
          const workspaces = response.workspaces
          const defaultWorkspace = response.default_workspace || ''
          const state = get()
          let currentWorkspace = state.currentWorkspace

          if (!currentWorkspace) {
            currentWorkspace = defaultWorkspace || workspaces[0]?.id || ''
          } else if (
            workspaces.length > 0 &&
            !workspaces.some((w) => w.id === currentWorkspace)
          ) {
            currentWorkspace = defaultWorkspace || workspaces[0].id
          }

          set({
            workspaces,
            defaultWorkspace,
            currentWorkspace
          })
        } finally {
          set({ loading: false })
        }
      },

      addWorkspace: async (id: string, name?: string) => {
        const created = await createWorkspace(id, name)
        await get().refreshWorkspaces()
        set({ currentWorkspace: created.id })
      },

      removeWorkspace: async (id: string) => {
        const state = get()
        const nextWorkspace =
          state.currentWorkspace === id
            ? state.defaultWorkspace ||
              state.workspaces.find((w) => w.id !== id)?.id ||
              ''
            : state.currentWorkspace
        if (state.currentWorkspace === id) {
          set({ currentWorkspace: nextWorkspace })
        }
        await deleteWorkspace(id)
        await get().refreshWorkspaces()
      }
    }),
    {
      name: 'task-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        currentWorkspace: state.currentWorkspace
      })
    }
  )
)

export const useTaskStore = createSelectors(useTaskStoreBase)
