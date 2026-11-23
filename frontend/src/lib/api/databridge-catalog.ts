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
  resources?: Resource[]
  provenance?: Record<string, unknown>
}
export interface Resource { id: string; metadata: Record<string, unknown>; classification: Assessment; preflight?: Assessment }
export interface CatalogDataset { id: string; title: string; description: string; publisher: unknown; metadata: Record<string, unknown>; cached_at: string; resources: Resource[]; resources_status?: string }
export interface CatalogPage { results: CatalogDataset[]; after: string | null; source: string }
export interface ImportJob {
  id: string; title: string; status: 'awaiting_approval' | 'queued' | 'running' | 'failed' | 'cancelled' | 'ready'; stage: string; notebook_id: string
  version_id: string; connection_id?: string; source_id?: string; recoverable: boolean; cancel_requested: boolean
  profile?: Profile; download?: { bytes: number; sha256: string; final_url: string; retrieved_at: string }
  manifest?: { sha256: string; schema_sha256: string }; catalog_snapshot: Record<string, unknown>; resource_snapshot: Record<string, unknown>
  error?: { code: string; retryable: boolean }; history?: { stage: string; at: string }[]
  analysis?: { contract: Record<string, string>; sources: Record<string, { version_id: string }>; queries: { name: string; sql: string }[] }
  provenance?: Record<string, unknown>
}
export interface SearchFilters { q: string; org_slug: string; keyword: string; after: string }
export interface ComparisonReview extends ImportJob { approval_token?: string }
export const catalogApi = {
  publisher: async (publisher: 'census' | 'noaa', start_year: number, end_year: number, variables: string): Promise<CatalogDataset> => (await apiClient.post('/databridge/catalog/publishers/select', { publisher, start_year, end_year, variables })).data,
  comparison: async (notebook_id: string, sources: Record<'transit' | 'population' | 'weather', string>): Promise<ComparisonReview> => (await apiClient.post('/databridge/comparisons/review', { notebook_id, ...sources })).data,
  approveComparison: async (id: string, notebook_id: string, approval_token: string): Promise<ImportJob> => (await apiClient.post(`/databridge/comparisons/${id}/approve`, { notebook_id, approval_token })).data,
  search: async (filters: SearchFilters): Promise<CatalogPage> => (await apiClient.get('/databridge/catalog/search', { params: { ...filters, per_page: 10 } })).data,
  detail: async (id: string): Promise<CatalogDataset> => (await apiClient.get(`/databridge/catalog/datasets/${id}`)).data,
  preflight: async (id: string): Promise<Assessment> => (await apiClient.post(`/databridge/catalog/resources/${id}/preflight`)).data,
  imports: async (notebook: string): Promise<ImportJob[]> => (await apiClient.get('/databridge/imports', { params: { notebook_id: notebook } })).data,
  import: async (resource: string, notebook: string, key: string): Promise<ImportJob> => (await apiClient.post('/databridge/imports', { resource_id: resource, notebook_id: notebook, idempotency_key: key })).data,
  control: async (id: string, action: 'cancel' | 'retry', notebook: string): Promise<ImportJob> => (await apiClient.post(`/databridge/imports/${id}/${action}`, { notebook_id: notebook })).data,
}
