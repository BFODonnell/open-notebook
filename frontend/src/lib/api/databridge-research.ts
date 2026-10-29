import apiClient from './client'

export interface ResearchTurn {
  id: string; state: string; question: string; answer: string
  dataset?: { title: string; version_id: string; database_sha256: string; publisher: unknown; retrieved_at: string; download_url: string }
  plan?: { id: string; sql: string; expires_at: string }
  evidence?: { id: string; sql: string; rows: Record<string, unknown>[]; result_sha256: string; version_id: string }
  chart?: { year_column: string; value_column: string; points: { year: number; value: string }[]; change: string }
  approval_token?: string
}
export interface ResearchScope { notebook_id: string; session_id: string }
export const researchApi = {
  get: async (id: string, scope: ResearchScope): Promise<ResearchTurn> => (await apiClient.get(`/databridge/research/${id}`, { params: scope })).data,
  action: async (id: string, action: 'review' | 'execute' | 'resume', scope: ResearchScope, approval?: { plan_id: string; approval_token: string }): Promise<ResearchTurn> => (await apiClient.post(`/databridge/research/${id}/${action}`, { ...scope, ...approval })).data,
}
