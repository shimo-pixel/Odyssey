import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, FolderKanban, Trash2 } from 'lucide-react'
import Button from '@/components/ui/Button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/Select'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/Dialog'
import Input from '@/components/ui/Input'
import { useTaskStore } from '@/stores/task'
import { toast } from 'sonner'
import {
  selectValueToWorkspace,
  workspaceDisplayName,
  workspaceToSelectValue
} from '@/lib/workspace'

export default function TaskSelector() {
  const { t } = useTranslation()
  const currentWorkspace = useTaskStore.use.currentWorkspace()
  const workspaces = useTaskStore.use.workspaces()
  const defaultWorkspace = useTaskStore.use.defaultWorkspace()
  const loading = useTaskStore.use.loading()
  const setCurrentWorkspace = useTaskStore.use.setCurrentWorkspace()
  const refreshWorkspaces = useTaskStore.use.refreshWorkspaces()
  const addWorkspace = useTaskStore.use.addWorkspace()
  const removeWorkspace = useTaskStore.use.removeWorkspace()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [taskId, setTaskId] = useState('')
  const [taskName, setTaskName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    refreshWorkspaces().catch((error) => {
      console.error('Failed to load workspaces:', error)
    })
  }, [refreshWorkspaces])

  const handleCreate = useCallback(async () => {
    const id = taskId.trim()
    if (!id) {
      toast.error(t('taskSelector.idRequired', 'Task ID is required'))
      return
    }
    if (!/^[a-zA-Z0-9_]+$/.test(id)) {
      toast.error(
        t('taskSelector.idInvalid', 'Task ID may only contain letters, digits, and underscores')
      )
      return
    }
    setCreating(true)
    try {
      await addWorkspace(id, taskName.trim() || id)
      setDialogOpen(false)
      setTaskId('')
      setTaskName('')
      toast.success(t('taskSelector.created', 'Task created'))
    } catch (error) {
      toast.error(String(error))
    } finally {
      setCreating(false)
    }
  }, [addWorkspace, taskId, taskName, t])

  const handleDelete = useCallback(async () => {
    if (!currentWorkspace || currentWorkspace === defaultWorkspace) {
      return
    }
    if (!window.confirm(t('taskSelector.deleteConfirm', 'Delete this task and its knowledge base?'))) {
      return
    }
    try {
      await removeWorkspace(currentWorkspace)
      toast.success(t('taskSelector.deleted', 'Task deleted'))
    } catch (error) {
      toast.error(String(error))
    }
  }, [currentWorkspace, defaultWorkspace, removeWorkspace, t])

  const selectValue = workspaceToSelectValue(currentWorkspace)
  const defaultSelectValue = workspaceToSelectValue(defaultWorkspace)

  return (
    <div className="flex items-center gap-2">
      <FolderKanban className="size-4 text-muted-foreground" />
      <Select
        value={workspaces.length === 0 ? undefined : selectValue}
        onValueChange={(value) => setCurrentWorkspace(selectValueToWorkspace(value))}
        disabled={loading || workspaces.length === 0}
      >
        <SelectTrigger className="h-8 w-[180px]">
          <SelectValue placeholder={t('taskSelector.placeholder', 'Select task')} />
        </SelectTrigger>
        <SelectContent>
          {workspaces.map((workspace) => (
            <SelectItem
              key={workspaceToSelectValue(workspace.id)}
              value={workspaceToSelectValue(workspace.id)}
            >
              {workspaceDisplayName(
                workspace.id,
                workspace.name,
                t('taskSelector.default', 'Default')
              )}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 px-2">
            <Plus className="size-4" />
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('taskSelector.createTitle', 'Create Task')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Input
              placeholder={t('taskSelector.idPlaceholder', 'task_id')}
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
            />
            <Input
              placeholder={t('taskSelector.namePlaceholder', 'Display name (optional)')}
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button onClick={handleCreate} disabled={creating}>
              {t('taskSelector.create', 'Create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {currentWorkspace &&
        workspaceToSelectValue(currentWorkspace) !== defaultSelectValue && (
        <Button
          variant="outline"
          size="sm"
          className="h-8 px-2 text-destructive"
          onClick={handleDelete}
        >
          <Trash2 className="size-4" />
        </Button>
      )}
    </div>
  )
}
