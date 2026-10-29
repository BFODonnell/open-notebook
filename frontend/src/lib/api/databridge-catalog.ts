import apiClient from './client'

export interface Column { original: string; column: string; type: string; nulls?: number; min?: string | null; max?: string | null }
export interface Profile { table: string; rows: number; columns: Column[]; profile: Column[]; preview: Record<string, string | null>[]; warnings: string[] }
export interface Assessment {
  status: 'checking' | 'ready' | 'connector_required' | 'unavailable'
  reason: string
  adapter?: string
  expires_at?: string
  download?: { bytes: number; sha256: string; final_url: string }
  profile?: Profile
}
export interface Resource { id: string; metadata: Record<string, unknown>; classification: Assessment; preflight?: Assessment }
export interface CatalogDataset { id: string; title: string; description: string; publisher: unknown; metadata: Record<string, unknown>; cached_at: string; resources: Resource[] }
export interface CatalogPage { results: CatalogDataset[]; after: string | null; source: string }
export interface ImportJob {
  id: string; title: string; status: 'queued' | 'running' | 'failed' | 'cancelled' | 'ready'; stage: string; notebook_id: string
  version_id: string; connection_id?: string; source_id?: string; recoverable: boolean; cancel_requested: boolean
  profile?: Profile; download?: { bytes: number; sha256: string; final_url: string; retrieved_at: string }
  manifest?: { sha256: string; schema_sha256: string }; catalog_snapshot: Record<string, unknown>; resource_snapshot: Record<string, unknown>
  error?: { code: string; retryable: boolean }; history?: { stage: string; at: string }[]
}
export interface SearchFilters { q: string; org_slug: string; keyword: string; after: string }
export const catalogApi = {
  search: async (filters: SearchFilters): Promise<CatalogPage> => (await apiClient.get('/databridge/catalog/search', { params: { ...filters, per_page: 10 } })).data,
  detail: async (id: string): Promise<CatalogDataset> => (await apiClient.get(`/databridge/catalog/datasets/${id}`)).data,
  preflight: async (id: string): Promise<Assessment> => (await apiClient.post(`/databridge/catalog/resources/${id}/preflight`)).data,
  imports: async (notebook: string): Promise<ImportJob[]> => (await apiClient.get('/databridge/imports', { params: { notebook_id: notebook } })).data,
  import: async (resource: string, notebook: string, key: string): Promise<ImportJob> => (await apiClient.post('/databridge/imports', { resource_id: resource, notebook_id: notebook, idempotency_key: key })).data,
  control: async (id: string, action: 'cancel' | 'retry', notebook: string): Promise<ImportJob> => (await apiClient.post(`/databridge/imports/${id}/${action}`, { notebook_id: notebook })).data,
}
