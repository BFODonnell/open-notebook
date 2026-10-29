import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { toast } from 'sonner'
import { catalogApi, SearchFilters } from '@/lib/api/databridge-catalog'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useTranslation } from './use-translation'

export function useCatalogSearch(filters: SearchFilters | null) {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeCatalog, 'search', filters], queryFn: () => catalogApi.search(filters!), enabled: !!filters, retry: false })
}
export function useCatalogDetail(id: string) {
  return useQuery({ queryKey: [...QUERY_KEYS.databridgeCatalog, 'detail', id], queryFn: () => catalogApi.detail(id), enabled: !!id, retry: false })
}
export function useImports(notebook: string) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: [...QUERY_KEYS.databridgeCatalog, 'imports', notebook], queryFn: () => catalogApi.imports(notebook), enabled: !!notebook, retry: false,
    refetchInterval: query => query.state.data?.some(j => ['queued', 'running'].includes(j.status)) ? 2000 : false })
  const readyVersions = query.data?.filter(job => job.status === 'ready').map(job => job.version_id).join(',') || ''
  useEffect(() => {
    if (readyVersions) {
      // The queue mutation finishes before the worker attaches documentation.
      // Invalidate again on completion so cached notebook/connection views refresh.
      client.invalidateQueries({ queryKey: ['sources'] })
      client.invalidateQueries({ queryKey: QUERY_KEYS.databridgeMCP })
    }
  }, [readyVersions, client])
  return query
}
export function useCatalogAction() {
  const client = useQueryClient()
  const { t } = useTranslation()
  return useMutation({ mutationFn: (action: () => Promise<unknown>) => action(), retry: false,
    onSuccess: () => { client.invalidateQueries({ queryKey: QUERY_KEYS.databridgeCatalog }); client.invalidateQueries({ queryKey: QUERY_KEYS.databridgeMCP }); client.invalidateQueries({ queryKey: ['sources'] }); toast.success(t('explorer.completed')) },
    onError: () => toast.error(t('explorer.error')) })
}
