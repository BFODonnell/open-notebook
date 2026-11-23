import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { useImports } from './use-databridge-catalog'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { catalogApi } from '@/lib/api/databridge-catalog'

vi.mock('@/lib/api/databridge-catalog', () => ({ catalogApi: { imports: vi.fn().mockResolvedValue([{ id: 'job', version_id: 'version', status: 'running' }]) } }))

it('fetches imports with the selected notebook ID and keeps notebook caches separate', async () => {
  vi.mocked(catalogApi.imports).mockClear()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { rerender, unmount } = renderHook(({ notebook }) => useImports(notebook), { wrapper, initialProps: { notebook: '' } })
  expect(catalogApi.imports).not.toHaveBeenCalled()
  rerender({ notebook: 'notebook:demo' })
  await waitFor(() => expect(catalogApi.imports).toHaveBeenCalledWith('notebook:demo'))
  rerender({ notebook: 'notebook:other' })
  await waitFor(() => expect(catalogApi.imports).toHaveBeenCalledWith('notebook:other'))
  expect(client.getQueryData([...QUERY_KEYS.databridgeCatalog, 'imports', 'notebook:demo'])).toBeDefined()
  unmount()
  client.clear()
})

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
