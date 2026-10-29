import apiClient from './client'

export interface ToolInfo {
  name: string
  description?: string
  inputSchema: Record<string, unknown>
}
export interface ConnectionSpec {
  name: string
  backend: 'dbhub' | 'toolbox' | 'duckdb'
  endpoint_ref: string
  dialect: 'postgres' | 'duckdb' | 'sqlite'
  notebooks: string[]
  tables: Record<string, string[]>
  curated_tools: string[]
  schema_tool: string | null
  version_id: string | null
  max_rows: number
  max_bytes: number
  timeout_seconds: number
  enabled: boolean
}
export interface Connection extends ConnectionSpec {
  id: string
  health: string
  last_test?: string | null
  revision: string
  approved_fingerprint: string | null
  tools: ToolInfo[]
  has_token: boolean
}
export interface Discovery { fingerprint: string; tools: ToolInfo[]; health: string }
export interface QueryPlan {
  id: string
  approval_token: string
  expires_at: string
  sql: string | null
  tool: string | null
  parameters: Record<string, unknown>
  version_id: string | null
}
export interface Evidence {
  id: string
  status: string
  sql?: string
  version_id?: string
  result_sha256?: string
  rows?: Record<string, unknown>[]
  row_count?: number
  timestamp?: string
}
export interface Endpoint { ref: string; backend: ConnectionSpec['backend'] }
export interface Version { id: string; manifest: { version_id: string; dataset_id: string; sha256: string; tables: Record<string, string[]> } }

export const mcpApi = {
  read: async <T>(path: string, params?: Record<string, string>, admin?: string): Promise<T> =>
    (await apiClient.get<T>(`/databridge${path}`, { params, headers: admin ? { 'X-DataBridge-Admin': admin } : {} })).data,
  write: async <T>(path: string, data: unknown, admin?: string, method: 'post' | 'put' = 'post'): Promise<T> =>
    (await apiClient[method]<T>(`/databridge${path}`, data, { headers: admin ? { 'X-DataBridge-Admin': admin } : {} })).data,
}
