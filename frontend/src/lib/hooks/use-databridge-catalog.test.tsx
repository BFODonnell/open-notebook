import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { useImports } from './use-databridge-catalog'
import { QUERY_KEYS } from '@/lib/api/query-client'

vi.mock('@/lib/api/databridge-catalog', () => ({ catalogApi: { imports: vi.fn().mockResolvedValue([{ id: 'job', version_id: 'version', status: 'running' }]) } }))

it('refreshes notebook sources and MCP connections only after worker completion', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result, unmount } = renderHook(() => useImports('notebook:1'), { wrapper })
  await waitFor(() => expect(result.current.data?.[0].status).toBe('running'))
  expect(invalidate).not.toHaveBeenCalled()
  client.setQueryData([...QUERY_KEYS.databridgeCatalog, 'imports', 'notebook:1'], [{ id: 'job', version_id: 'version', status: 'ready' }])
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['sources'] }))
  expect(invalidate).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.databridgeMCP })
  unmount()
  client.clear()
})
