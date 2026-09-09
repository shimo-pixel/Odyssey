/** Radix Select does not allow empty string as item value. */
export const DEFAULT_WORKSPACE_SELECT_VALUE = '__default__'

/** HTTP headers are Latin-1; non-ASCII workspace ids must use B64 on the wire. */
export function utf8ToBase64(value: string): string {
  const bytes = new TextEncoder().encode(value)
  let binary = ''
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary)
}

export function workspaceNeedsB64Header(workspace: string): boolean {
  for (let i = 0; i < workspace.length; i += 1) {
    if (workspace.charCodeAt(i) > 0xff) {
      return true
    }
  }
  return false
}

export function applyWorkspaceHeaders(
  headers: Record<string, string>,
  workspace: string
): void {
  const ws = workspace.trim()
  if (!ws) {
    return
  }
  if (workspaceNeedsB64Header(ws)) {
    headers['LIGHTRAG-WORKSPACE-B64'] = utf8ToBase64(ws)
    return
  }
  headers['LIGHTRAG-WORKSPACE'] = ws
}

export function workspaceToSelectValue(workspaceId: string): string {
  return workspaceId === '' ? DEFAULT_WORKSPACE_SELECT_VALUE : workspaceId
}

export function selectValueToWorkspace(selectValue: string): string {
  return selectValue === DEFAULT_WORKSPACE_SELECT_VALUE ? '' : selectValue
}

export function workspaceDisplayName(
  workspaceId: string,
  workspaceName?: string | null,
  fallback = 'Default'
): string {
  if (workspaceName?.trim()) {
    return workspaceName.trim()
  }
  if (workspaceId) {
    return workspaceId
  }
  return fallback
}
