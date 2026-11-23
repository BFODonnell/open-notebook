'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useCatalogAction } from '@/lib/hooks/use-databridge-catalog'
import { catalogApi, ComparisonReview, ImportJob } from '@/lib/api/databridge-catalog'

export function ComparisonBuilder({ notebook, jobs }: { notebook: string; jobs: ImportJob[] }) {
  const { t } = useTranslation()
  const action = useCatalogAction()
  const [sources, setSources] = useState({ transit: '', population: '', weather: '' })
  const [review, setReview] = useState<ComparisonReview | null>(null)
  const error = action.error as { response?: { data?: { detail?: string } } } | null
  const roles = ['transit', 'population', 'weather'] as const
  const labels = { transit: 'explorer.transit', population: 'explorer.population', weather: 'explorer.weather' } as const
  return <section className="space-y-3 rounded border p-4">
    <h2 className="font-display text-xl">{t('explorer.comparison')}</h2>
    <p>{t('explorer.comparisonScope')}</p>
    <div className="grid gap-3 md:grid-cols-3">{roles.map(role => <label key={role}>{t(labels[role])}<select className="w-full rounded border bg-background p-2 text-sm" value={sources[role]} disabled={action.isPending} onChange={e => { setSources({ ...sources, [role]: e.target.value }); setReview(null) }}>
      <option value="">{t('explorer.selectDataset')}</option>{jobs.filter(j => j.status === 'ready' && !j.analysis).map(j => <option key={j.id} value={j.id}>{j.title} — {j.version_id}</option>)}
    </select></label>)}</div>
    <Button variant="outline" disabled={!notebook || roles.some(r => !sources[r]) || action.isPending} onClick={() => action.mutate(async () => setReview(await catalogApi.comparison(notebook, sources)))}>{t('explorer.reviewComparison')}</Button>
    {review?.analysis && <div className="space-y-3">
      {Object.entries(review.analysis.contract).map(([key, value]) => <p key={key}>{value}</p>)}
      <details><summary>{t('explorer.provenance')}</summary><pre className="overflow-auto text-xs">{JSON.stringify(review.analysis.sources, null, 2)}</pre></details>
      {review.analysis.queries.map(query => <pre key={query.name} className="overflow-auto rounded border p-2 text-xs">{query.sql}</pre>)}
      {review.status === 'awaiting_approval' && review.approval_token ? <Button disabled={action.isPending} onClick={() => action.mutate(async () => setReview(await catalogApi.approveComparison(review.id, notebook, review.approval_token!)))}>{t('explorer.approveComparison')}</Button> : <p role="status">{t('explorer.importSubmitted')} {review.id}</p>}
    </div>}
    {action.isPending && <p role="status">{t('explorer.processing')}</p>}
    {action.isError && <p role="alert">{t('explorer.error')} {error?.response?.data?.detail}</p>}
  </section>
}
