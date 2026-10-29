'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useCatalogAction, useCatalogDetail, useCatalogSearch, useImports } from '@/lib/hooks/use-databridge-catalog'
import { Assessment, catalogApi, Profile, SearchFilters } from '@/lib/api/databridge-catalog'
import { ConnectionsPanel } from './ConnectionsPanel'

const input = 'w-full rounded border bg-background p-2 text-sm'

function Preview({ profile }: { profile: Profile }) {
  const { t } = useTranslation()
  return <div className="space-y-2">
    <p>{profile.rows.toLocaleString()} {t('explorer.rows')} · {profile.columns.length} {t('explorer.columns')}</p>
    <div className="overflow-auto"><table className="w-full text-left text-xs">
      <thead><tr>{profile.columns.map(col => <th className="p-2" key={col.column}>{col.original}<br /><code>{col.column}</code><br />{col.type}</th>)}</tr></thead>
      <tbody>{profile.preview.map((row, i) => <tr key={i}>{profile.columns.map(col => <td className="max-w-64 break-words border-t p-2" key={col.column}>{row[col.column] ?? '—'}</td>)}</tr>)}</tbody>
    </table></div>
    <p className="text-sm text-muted-foreground">{t('explorer.mappingNotice')}</p>
  </div>
}

export function Explorer() {
  const { t } = useTranslation()
  const notebooks = useNotebooks(false)
  const [notebook, setNotebook] = useState('')
  const [query, setQuery] = useState('National Transit Database')
  const [agency, setAgency] = useState('')
  const [keyword, setKeyword] = useState('')
  const [filters, setFilters] = useState<SearchFilters | null>(null)
  const [selected, setSelected] = useState('')
  const [checks, setChecks] = useState<Record<string, Assessment>>({})
  const [confirmation, setConfirmation] = useState<{ id: string; key: string } | null>(null)
  const [queryJob, setQueryJob] = useState('')
  const search = useCatalogSearch(filters)
  const detail = useCatalogDetail(selected)
  const imports = useImports(notebook)
  const action = useCatalogAction()
  const busy = action.isPending || detail.isFetching
  const perform = (task: () => Promise<unknown>) => action.mutate(task)
  const ready = imports.data?.find(job => job.id === queryJob && job.status === 'ready')
  const stateLabel = (value: Assessment['status']) => value === 'ready' ? t('explorer.ready') : value === 'checking' ? t('explorer.checking') : value === 'connector_required' ? t('explorer.connectorRequired') : t('explorer.unavailable')
  const reason = (code: string) => code === 'VALIDATED' ? t('explorer.validated') : code === 'PREFLIGHT_REQUIRED' ? t('explorer.checkRequired') : code.includes('ADAPTER') || code.includes('STRUCTURE') || code.includes('SELECTION') || code === 'DIRECT_DOWNLOAD_REQUIRED' ? t('explorer.adapterReason') : code.includes('LIMIT') ? t('explorer.limitReason') : code.includes('RESTRICTED') || code.includes('RIGHTS') || code.includes('AUTH') || code.includes('BLOCKED') ? t('explorer.blockedReason') : t('explorer.unavailableReason')
  const stageLabel = (stage: string) => {
    const keys = { queued: 'explorer.queued', resolving: 'explorer.resolving', downloading: 'explorer.downloading', validating: 'explorer.validating', parsing: 'explorer.parsing', staging: 'explorer.staging', profiling: 'explorer.profiling', publishing: 'explorer.publishing', registering: 'explorer.registering', ready: 'explorer.imported', failed: 'explorer.failed', cancelled: 'explorer.cancelled' } as const
    return t(keys[stage as keyof typeof keys] || 'explorer.processing')
  }

  return <div className="mx-auto max-w-6xl space-y-6 p-6">
    <header><h1 className="font-display text-3xl">{t('explorer.title')}</h1><p className="mt-2 text-muted-foreground">{t('explorer.intro')}</p></header>
    <label className="block">{t('explorer.notebook')}<select className={input} value={notebook} disabled={busy} onChange={e => { setNotebook(e.target.value); setConfirmation(null); setQueryJob('') }}>
      <option value="">{t('explorer.chooseNotebook')}</option>{notebooks.data?.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
    </select></label>
    <form className="space-y-3 rounded-lg border p-4" onSubmit={e => { e.preventDefault(); setFilters({ q: query, org_slug: agency, keyword, after: '' }); setSelected(''); setConfirmation(null) }}>
      <div className="grid gap-3 md:grid-cols-3">
        <label>{t('explorer.searchTerms')}<input className={input} value={query} maxLength={250} onChange={e => setQuery(e.target.value)} /></label>
        <label>{t('explorer.agency')}<input className={input} value={agency} maxLength={100} onChange={e => setAgency(e.target.value)} /></label>
        <label>{t('explorer.keyword')}<input className={input} value={keyword} maxLength={100} onChange={e => setKeyword(e.target.value)} /></label>
      </div>
      <Button type="submit" disabled={search.isFetching}>{t('explorer.search')}</Button>
      <p className="text-sm text-muted-foreground">{t('explorer.ntdNotice')}</p>
    </form>
    {(search.isError || detail.isError || imports.isError || action.isError) && <p role="alert" className="text-destructive">{t('explorer.error')}</p>}
    {(search.isFetching || detail.isFetching || action.isPending) && <p role="status">{t('explorer.loading')}</p>}
    {search.data && <section className="space-y-3" aria-label={t('explorer.results')}>
      {!search.data.results.length && <p>{t('explorer.noResults')}</p>}
      {search.data.results.map(item => <article key={item.id} className="rounded border p-4">
        <h2 className="font-semibold">{item.title}</h2><p className="line-clamp-3 text-sm">{item.description}</p>
        <p className="text-sm text-muted-foreground">{typeof item.publisher === 'string' ? item.publisher : JSON.stringify(item.publisher)}</p>
        <Button variant="outline" disabled={busy} onClick={() => { setSelected(item.id); setConfirmation(null) }}>{t('explorer.inspect')}</Button>
      </article>)}
      {search.data.after && <Button variant="outline" disabled={search.isFetching} onClick={() => { if (filters) { setFilters({ ...filters, after: search.data.after! }); setSelected('') } }}>{t('explorer.next')}</Button>}
    </section>}
    {detail.data && <section className="space-y-4 rounded-lg border p-4" aria-label={t('explorer.details')}>
      <h2 className="font-display text-xl">{detail.data.title}</h2><p>{detail.data.description}</p>
      <details><summary>{t('explorer.catalogMetadata')}</summary><pre className="max-h-80 overflow-auto text-xs">{JSON.stringify(detail.data.metadata, null, 2)}</pre></details>
      {!detail.data.resources.length && <p>{t('explorer.noResources')}</p>}
      {detail.data.resources.map(resource => {
        const check = checks[resource.id] || resource.preflight || resource.classification
        return <article className="space-y-3 rounded border p-3" key={resource.id}>
          <h3 className="font-semibold">{String(resource.metadata.title || resource.metadata.format || t('explorer.resource'))}</h3>
          <p>{stateLabel(check.status)} · {reason(check.reason)} <code className="text-xs">{check.reason}</code></p>
          <p className="break-all text-xs">{String(resource.metadata.downloadURL || resource.metadata.accessURL || '')}</p>
          <Button variant="outline" disabled={busy} onClick={() => perform(async () => { const checked = await catalogApi.preflight(resource.id); setChecks(current => ({ ...current, [resource.id]: checked })); setConfirmation(null) })}>{t('explorer.preview')}</Button>
          {check.profile && <Preview profile={check.profile} />}
          {check.download && <p className="text-sm">{check.download.bytes.toLocaleString()} {t('explorer.bytes')} · SHA-256: <code className="break-all text-xs">{check.download.sha256}</code></p>}
          <Button disabled={busy || !notebook || check.status !== 'ready' || !check.expires_at || check.expires_at < new Date().toISOString()} onClick={() => setConfirmation({ id: resource.id, key: crypto.randomUUID() })}>{t('explorer.import')}</Button>
          {confirmation?.id === resource.id && <div className="space-y-2 border-t pt-3">
            <p>{t('explorer.confirmNotice')}</p>
            <Button disabled={busy} onClick={() => perform(async () => { await catalogApi.import(resource.id, notebook, confirmation.key); setConfirmation(null) })}>{t('explorer.confirmImport')}</Button>
          </div>}
        </article>
      })}
    </section>}
    <section className="space-y-3" aria-label={t('explorer.myDatasets')}>
      <h2 className="font-display text-xl">{t('explorer.myDatasets')}</h2>
      {!imports.data?.length && <p className="text-muted-foreground">{t('explorer.noImports')}</p>}
      {imports.data?.map(job => <article className="space-y-3 rounded-lg border p-4" key={job.id}>
        <h3 className="font-semibold">{job.title}</h3><p role="status" aria-live="polite">{stageLabel(job.stage)}</p>
        {job.cancel_requested && job.status === 'running' && <p>{t('explorer.cancelling')}</p>}
        {job.error && <p role="alert" className="text-destructive">{t('explorer.importError')} <code>{job.error.code}</code></p>}
        {['queued', 'running'].includes(job.status) && !['publishing', 'registering'].includes(job.stage) && <Button variant="outline" disabled={busy || job.cancel_requested} onClick={() => perform(() => catalogApi.control(job.id, 'cancel', notebook))}>{t('explorer.cancel')}</Button>}
        {job.recoverable && <Button variant="outline" disabled={busy} onClick={() => perform(() => catalogApi.control(job.id, 'retry', notebook))}>{t('explorer.retry')}</Button>}
        {job.status === 'ready' && <>
          {job.profile && <Preview profile={job.profile} />}
          <p className="break-all text-xs">{t('explorer.version')}: {job.version_id}</p>
          <Button variant="outline" onClick={() => setQueryJob(job.id)}>{t('explorer.query')}</Button>
          <Link className="ml-4 underline" href={`/notebooks/${notebook}`}>{t('explorer.openNotebook')}</Link>
          <p className="text-sm text-muted-foreground">{t('explorer.chatBoundary')}</p>
        </>}
        <details><summary>{t('explorer.provenance')}</summary><pre className="max-h-96 overflow-auto text-xs">{JSON.stringify({ catalog: job.catalog_snapshot, resource: job.resource_snapshot, download: job.download, version_id: job.version_id, manifest: job.manifest, profile: job.profile, history: job.history }, null, 2)}</pre></details>
      </article>)}
    </section>
    {ready?.connection_id && <ConnectionsPanel key={ready.id} initialNotebook={notebook} initialConnection={ready.connection_id} initialSql="SELECT COUNT(*) AS rows FROM data" />}
  </div>
}
