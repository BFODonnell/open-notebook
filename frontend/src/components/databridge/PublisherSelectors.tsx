'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useCatalogAction } from '@/lib/hooks/use-databridge-catalog'
import { catalogApi } from '@/lib/api/databridge-catalog'

export function PublisherSelectors({ onSelect }: { onSelect: (id: string) => void }) {
  const { t } = useTranslation()
  const action = useCatalogAction()
  const [start, setStart] = useState(2022)
  const [end, setEnd] = useState(2025)
  const [variables, setVariables] = useState('TAVG,PRCP')
  const input = 'rounded border bg-background p-2 text-sm'
  const error = action.error as { response?: { data?: { detail?: string } } } | null
  return <section className="space-y-3 rounded border p-4">
    <h2 className="font-display text-xl">{t('explorer.publishers')}</h2>
    <p>{t('explorer.censusSelection')}</p>
    <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate(async () => onSelect((await catalogApi.publisher('census', 2022, 2025, 'TAVG,PRCP')).id))}>{t('explorer.inspectCensus')}</Button>
    <p>{t('explorer.noaaSelection')}</p>
    <div className="flex flex-wrap gap-3">
      <label>{t('explorer.station')} <select className={input} aria-label={t('explorer.station')}><option>USW00014739 — Boston Logan</option></select></label>
      <label>{t('explorer.startYear')} <select className={input} value={start} onChange={e => setStart(Number(e.target.value))}>{[2022, 2023, 2024, 2025].map(y => <option key={y}>{y}</option>)}</select></label>
      <label>{t('explorer.endYear')} <select className={input} value={end} onChange={e => setEnd(Number(e.target.value))}>{[2022, 2023, 2024, 2025].map(y => <option key={y}>{y}</option>)}</select></label>
      <label>{t('explorer.weatherVariables')} <select className={input} value={variables} onChange={e => setVariables(e.target.value)}><option value="TAVG,PRCP">TAVG (°C), PRCP (mm)</option><option value="TAVG">TAVG (°C)</option><option value="PRCP">PRCP (mm)</option></select></label>
    </div>
    <Button variant="outline" disabled={action.isPending || start > end} onClick={() => action.mutate(async () => onSelect((await catalogApi.publisher('noaa', start, end, variables)).id))}>{t('explorer.inspectNoaa')}</Button>
    {action.isPending && <p role="status">{t('explorer.loading')}</p>}
    {action.isError && <p role="alert">{t('explorer.error')} {error?.response?.data?.detail}</p>}
  </section>
}
