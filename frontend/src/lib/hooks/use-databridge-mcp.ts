import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Connection, Endpoint, Evidence, mcpApi, Version } from '@/lib/api/databridge-mcp'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useTranslation } from './use-translation'

export function useMCPStatus() {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeMCP, 'status'], queryFn: () => mcpApi.read<{ enabled: boolean }>('/mcp/status'), retry: false })
}
export function useMCPConnections(notebook: string) {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeMCP, 'connections', notebook], queryFn: () => mcpApi.read<Connection[]>('/mcp/servers', { notebook_id: notebook }), enabled: !!notebook, retry: false })
}
export function useMCPEndpoints(admin: string) {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeMCP, 'endpoints'], queryFn: () => mcpApi.read<Endpoint[]>('/mcp/endpoints', undefined, admin), enabled: !!admin, retry: false, staleTime: 0 })
}
export function useMCPVersions(admin: string) {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeMCP, 'versions'], queryFn: () => mcpApi.read<Version[]>('/dataset-versions', undefined, admin), enabled: !!admin, retry: false })
}
export function useMCPRuns(connection: string, notebook: string) {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeMCP, 'runs', connection, notebook], queryFn: () => mcpApi.read<Evidence[]>('/query/runs', { connection_id: connection, notebook_id: notebook }), enabled: !!connection && !!notebook, retry: false })
}
export function useMCPAction() {
  const client = useQueryClient()
  const { t } = useTranslation()
  return useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    retry: false,
    onSuccess: () => { client.invalidateQueries({ queryKey: QUERY_KEYS.databridgeMCP }); toast.success(t('mcp.completed')) },
    onError: () => toast.error(t('mcp.actionError')),
  })
}
