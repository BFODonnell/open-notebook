'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useDataBridgeUsage } from '@/lib/hooks/use-databridge-usage'

function startDate(period: string) {
  const now = new Date()
  if (period === 'all') return new Date(0).toISOString()
  if (period === 'today') now.setUTCHours(0, 0, 0, 0)
  else now.setTime(now.getTime() - 7 * 86400000)
  return now.toISOString()
}

export function UsagePanel() {
  const { t } = useTranslation()
  const [period, setPeriod] = useState('week')
  const [start, setStart] = useState(() => startDate('week'))
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch, isFetching } = useDataBridgeUsage(start, page)
  const money = (value: number | null) => value === null ? t('databridge.unavailable') : `$${value > 0 && value < 0.000001 ? value.toExponential(3) : value.toFixed(6)} USD`

  if (data && !data.enabled) return null
  return (
    <section className="mt-8 space-y-4 rounded-lg border p-4" aria-label={t('databridge.title')}>
      <h2 className="font-display text-xl">{t('databridge.title')}</h2>
      <p className="text-sm text-muted-foreground">{t('databridge.coverage')}</p>
      {isPending && <p role="status">{t('databridge.loading')}</p>}
      {isError && <p role="alert" className="text-destructive">{t('databridge.error')}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="usage-period">{t('databridge.period')}</label>
        <select id="usage-period" className="rounded border bg-background p-2" value={period} onChange={event => {
          setPeriod(event.target.value)
          setStart(startDate(event.target.value))
          setPage(1)
        }}>
          <option value="today">{t('databridge.today')}</option>
          <option value="week">{t('databridge.week')}</option>
          <option value="all">{t('databridge.all')}</option>
        </select>
        <Button variant="outline" disabled={isFetching} onClick={() => refetch()}>{t('databridge.refresh')}</Button>
      </div>
      {data?.enabled && <>
        <p>{t('databridge.managed')}: <strong>{data.managed_model}</strong></p>
        <p>{t('databridge.budget')}: {money(data.budget_remaining_usd)} / {money(data.budget_limit_usd)}</p>
        {data.budget_remaining_usd === 0 && <p role="alert" className="text-warn">{t('databridge.exhausted')}</p>}
        <p className="text-sm text-muted-foreground">{t('databridge.estimate')}</p>
        {data.records.length === 0 ? <p>{t('databridge.empty')}</p> : <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>
              <th className="p-2">{t('databridge.request')}</th>
              <th className="p-2">{t('databridge.tokens')}</th>
              <th className="p-2">{t('databridge.cost')}</th>
            </tr></thead>
            <tbody>{data.records.map(row => <tr key={row.request_id} className="border-t">
              <td className="p-2">
                <div>{row.model_alias || row.model}</div>
                <div>{new Date(row.timestamp).toLocaleString()}</div>
                <div>{row.status === 'success' ? t('databridge.success') : t('databridge.failed')}</div>
                <details><summary>{t('databridge.details')}</summary>
                  <div className="max-w-72 break-all">{row.request_id}<br />{row.trace_id}<br />{row.notebook_id}<br />{row.session_id}<br />{row.task}</div>
                </details>
              </td>
              <td className="p-2">
                <div>{row.input_tokens ?? '—'} / {row.output_tokens ?? '—'}</div>
                <div>{t('databridge.cached')}: {row.cached_input_tokens ?? '—'}</div>
                <div>{t('databridge.reasoning')}: {row.reasoning_tokens ?? '—'}</div>
              </td>
              <td className="p-2">{money(row.estimated_cost_usd)}</td>
            </tr>)}</tbody>
          </table>
        </div>}
        <div className="flex items-center gap-3">
          <Button variant="outline" disabled={page <= 1 || isFetching} onClick={() => setPage(page - 1)}>{t('databridge.previous')}</Button>
          <span>{page} / {Math.max(1, data.total_pages)}</span>
          <Button variant="outline" disabled={page >= data.total_pages || isFetching} onClick={() => setPage(page + 1)}>{t('databridge.next')}</Button>
        </div>
        {data.total_is_capped && <p>{t('databridge.capped')}</p>}
      </>}
    </section>
  )
}
