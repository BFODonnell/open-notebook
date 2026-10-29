import { useQuery } from '@tanstack/react-query'
import apiClient from '@/lib/api/client'
import { QUERY_KEYS } from '@/lib/api/query-client'

export interface UsageRecord {
  request_id: string
  timestamp: string
  model: string
  model_alias: string | null
  session_id: string | null
  notebook_id: string | null
  trace_id: string | null
  task: string | null
  input_tokens: number | null
  output_tokens: number | null
  cached_input_tokens: number | null
  reasoning_tokens: number | null
  estimated_cost_usd: number | null
  pricing_status: string
  status: string
}

export interface UsagePage {
  enabled: boolean
  managed_model: string | null
  records: UsageRecord[]
  page: number
  total: number
  total_pages: number
  total_is_capped: boolean
  budget_limit_usd: number | null
  budget_spend_usd: number | null
  budget_remaining_usd: number | null
}

export function useDataBridgeUsage(start: string, page: number) {
  return useQuery({
    queryKey: [...QUERY_KEYS.databridgeUsage, start, page],
    queryFn: async () => (await apiClient.get<UsagePage>('/databridge/usage', { params: { start, page } })).data,
    retry: false,
    staleTime: 10_000,
  })
}
