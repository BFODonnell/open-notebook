'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useMCPAction, useMCPConnections, useMCPEndpoints, useMCPRuns, useMCPStatus, useMCPVersions } from '@/lib/hooks/use-databridge-mcp'
import { Connection, ConnectionSpec, Discovery, Evidence, mcpApi, QueryPlan } from '@/lib/api/databridge-mcp'

const blank: ConnectionSpec = { name: '', backend: 'dbhub', endpoint_ref: 'dbhub', dialect: 'postgres', notebooks: [], tables: {}, curated_tools: [], schema_tool: null, version_id: null, max_rows: 100, max_bytes: 65536, timeout_seconds: 10, enabled: true }
const inputClass = 'w-full rounded border bg-background p-2 text-sm'

interface InitialSelection { initialNotebook?: string; initialConnection?: string; initialSql?: string }

export function ConnectionsPanel(props: InitialSelection = {}) {
  const status = useMCPStatus()
  if (!status.data?.enabled) return null
  return <ConnectionManager {...props} />
}

function ConnectionManager({ initialNotebook = '', initialConnection = '', initialSql = 'SELECT value FROM sample' }: InitialSelection) {
  const { t } = useTranslation()
  const notebooks = useNotebooks(false)
  const [notebook, setNotebook] = useState(initialNotebook)
  const [selected, setSelected] = useState(initialConnection)
  const [adminDraft, setAdminDraft] = useState('')
  const [admin, setAdmin] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<ConnectionSpec>(blank)
  const [tableText, setTableText] = useState('sample:value')
  const [token, setToken] = useState('')
  const [discovery, setDiscovery] = useState<Discovery | null>(null)
  const [schema, setSchema] = useState<unknown>(null)
  const [sql, setSql] = useState(initialSql)
  const [tool, setTool] = useState('')
  const [parameters, setParameters] = useState('{}')
  const [plan, setPlan] = useState<QueryPlan | null>(null)
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const connections = useMCPConnections(notebook)
  const endpoints = useMCPEndpoints(admin)
  const versions = useMCPVersions(admin)
  const runs = useMCPRuns(selected, notebook)
  const action = useMCPAction()
  const connection = connections.data?.find(c => c.id === selected)
  const busy = action.isPending
  const clearQuery = () => { setPlan(null); setEvidence(null); setSchema(null); setDiscovery(null) }
  const perform = (task: () => Promise<unknown>) => action.mutate(task)

  function edit(value?: Connection) {
    setEditing(value?.id || '')
    setForm(value ? {
      name: value.name, backend: value.backend, endpoint_ref: value.endpoint_ref, dialect: value.dialect,
      notebooks: value.notebooks, tables: value.tables, curated_tools: value.curated_tools, schema_tool: value.schema_tool,
      version_id: value.version_id, max_rows: value.max_rows, max_bytes: value.max_bytes, timeout_seconds: value.timeout_seconds, enabled: value.enabled,
    } : { ...blank, notebooks: notebook ? [notebook] : [] })
    setTableText(value ? Object.entries(value.tables).map(([name, cols]) => `${name}:${cols.join(',')}`).join('\n') : 'sample:value')
    setToken('')
  }

  return <section className="mt-8 space-y-4 rounded-lg border p-4" aria-label={t('mcp.title')}>
    <h2 className="font-display text-xl">{t('mcp.title')}</h2>
    <p className="text-sm text-muted-foreground">{t('mcp.scope')}</p>
    <label className="block">{t('mcp.notebook')}
      <select className={inputClass} disabled={busy} value={notebook} onChange={e => { setNotebook(e.target.value); setSelected(''); clearQuery() }}>
        <option value="">{t('mcp.choose')}</option>
        {notebooks.data?.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
      </select>
    </label>
    {(connections.isError || endpoints.isError || action.isError) && <p role="alert" className="text-destructive">{t('mcp.actionError')}</p>}
    {connections.isFetching && <p role="status">{t('mcp.loading')}</p>}
    <label className="block">{t('mcp.connection')}
      <select className={inputClass} disabled={busy} value={selected} onChange={e => { setSelected(e.target.value); setTool(''); clearQuery() }}>
        <option value="">{t('mcp.choose')}</option>
        {connections.data?.map(c => <option key={c.id} value={c.id}>{c.name} · {c.backend}{!c.enabled ? ` · ${t('mcp.disabled')}` : ''}</option>)}
      </select>
    </label>
    {connection && <>
      <p role="status">{t('mcp.health')}: {t(connection.health === 'ready' ? 'mcp.ready' : connection.health === 'unavailable' ? 'mcp.unavailable' : connection.health === 'approval_required' ? 'mcp.needsApproval' : 'mcp.untested')}{connection.last_test && ` · ${connection.last_test}`}</p>
      <p>{connection.approved_fingerprint ? t('mcp.approved') : t('mcp.needsApproval')} · {connection.max_rows} {t('mcp.rows')} · {connection.timeout_seconds} {t('mcp.seconds')}</p>
      {connection.version_id && <p className="break-all">{t('mcp.version')}: {connection.version_id}</p>}
      <Button variant="outline" disabled={busy || !connection.enabled} onClick={() => perform(async () => setSchema(await mcpApi.read(`/mcp/servers/${selected}/schema`, { notebook_id: notebook })))}>{t('mcp.inspectSchema')}</Button>
      {schema !== null && <pre className="max-h-60 overflow-auto rounded border p-3 text-xs">{JSON.stringify(schema, null, 2)}</pre>}
      {connection.backend === 'toolbox' ? <label className="block">{t('mcp.tool')}
        <select className={inputClass} value={tool} onChange={e => { setTool(e.target.value); setPlan(null) }}>
          <option value="">{t('mcp.choose')}</option>
          {connection.curated_tools.filter(name => name !== connection.schema_tool).map(name => <option key={name}>{name}</option>)}
        </select>
      </label> : <label className="block">{t('mcp.sql')}
        <textarea className={inputClass} rows={4} value={sql} onChange={e => { setSql(e.target.value); setPlan(null) }} />
      </label>}
      <label className="block">{t('mcp.parameters')}
        <textarea className={inputClass} rows={2} value={parameters} onChange={e => { setParameters(e.target.value); setPlan(null) }} />
      </label>
      <Button disabled={busy || !connection.enabled || !connection.approved_fingerprint} onClick={() => perform(async () => {
        setPlan(null); setEvidence(null)
        const draft = await mcpApi.write<QueryPlan>('/query/plans', { connection_id: selected, notebook_id: notebook, ...(connection.backend === 'toolbox' ? { tool } : { sql }), parameters: JSON.parse(parameters) })
        setPlan(draft)
      })}>{t('mcp.review')}</Button>
      {plan && <div className="space-y-3 rounded border p-3">
        <p>{t('mcp.approvalNotice')}</p>
        <pre className="overflow-auto text-xs">{plan.sql || JSON.stringify({ tool: plan.tool, parameters: plan.parameters }, null, 2)}</pre>
        <p className="break-all">{plan.version_id}</p>
        <Button disabled={busy} onClick={() => perform(async () => {
          const pending = plan; setPlan(null)
          setEvidence(await mcpApi.write<Evidence>(`/query/plans/${pending.id}/execute`, { notebook_id: notebook, approval_token: pending.approval_token }))
        })}>{t('mcp.approveExecute')}</Button>
      </div>}
      {evidence && <div className="space-y-2">
        <h3 className="font-semibold">{t('mcp.results')}</h3>
        <p className="break-all text-xs">{evidence.id}<br />{evidence.version_id}<br />{evidence.result_sha256}</p>
        <p>{evidence.row_count} {t('mcp.rows')} · {t('mcp.preview')}</p>
        <div className="overflow-auto"><table className="w-full text-left text-sm">
          <thead><tr>{Object.keys(evidence.rows?.[0] || {}).map(col => <th className="p-2" key={col}>{col}</th>)}</tr></thead>
          <tbody>{evidence.rows?.slice(0, 50).map((row, i) => <tr className="border-t" key={i}>{Object.entries(row).map(([col, value]) => <td className="max-w-64 break-words p-2" key={col}>{typeof value === 'string' ? value : JSON.stringify(value)}</td>)}</tr>)}</tbody>
        </table></div>
      </div>}
      <details><summary>{t('mcp.audit')}</summary>
        {runs.data?.map(run => <div className="flex flex-wrap gap-2 border-b py-2 text-xs" key={run.id}>
          <span>{run.timestamp}</span><span>{t(run.status === 'success' ? 'mcp.success' : run.status === 'denied' ? 'mcp.denied' : run.status === 'running' ? 'mcp.running' : 'mcp.failed')}</span>
          {run.status === 'success' && <Button variant="outline" size="sm" disabled={busy} onClick={() => perform(async () => setEvidence(await mcpApi.read<Evidence>(`/evidence/${run.id}`, { notebook_id: notebook })))}>{t('mcp.openEvidence')}</Button>}
        </div>)}
      </details>
    </>}
    <details><summary>{t('mcp.administration')}</summary>
      <div className="mt-3 space-y-3">
        <p className="text-sm text-muted-foreground">{t('mcp.adminNotice')}</p>
        <label className="block">{t('mcp.adminKey')}<input className={inputClass} type="password" autoComplete="off" value={adminDraft} onChange={e => setAdminDraft(e.target.value)} /></label>
        <Button variant="outline" onClick={() => { setAdmin(adminDraft); setAdminDraft('') }}>{t('mcp.unlock')}</Button>
        {admin && <>
          <Button variant="outline" onClick={() => { setAdmin(''); setEditing(null); setToken(''); setDiscovery(null) }}>{t('mcp.lock')}</Button>
          <Button variant="outline" onClick={() => edit()}>{t('mcp.add')}</Button>
          {connection && <>
            <Button variant="outline" onClick={() => edit(connection)}>{t('mcp.edit')}</Button>
            <Button variant="outline" disabled={busy} onClick={() => perform(async () => setDiscovery(await mcpApi.write<Discovery>(`/mcp/servers/${selected}/discover`, {}, admin)))}>{t('mcp.testDiscover')}</Button>
          </>}
          {discovery && <div className="space-y-2 rounded border p-3">
            <p>{t('mcp.inspectTools')}</p>
            <pre className="max-h-60 overflow-auto text-xs">{JSON.stringify(discovery.tools, null, 2)}</pre>
            <Button disabled={busy} onClick={() => perform(async () => { await mcpApi.write(`/mcp/servers/${selected}/approve`, { fingerprint: discovery.fingerprint }, admin); setDiscovery(null) })}>{t('mcp.approveTools')}</Button>
          </div>}
          {editing !== null && <form className="space-y-3 rounded border p-3" onSubmit={e => { e.preventDefault(); perform(async () => {
            const tables = Object.fromEntries(tableText.split('\n').filter(x => x.trim()).map(line => { const [name, cols] = line.split(':'); return [name.trim(), (cols || '').split(',').map(c => c.trim()).filter(Boolean)] }))
            const saved = await mcpApi.write<Connection>(editing ? `/mcp/servers/${editing}` : '/mcp/servers', { ...form, tables, ...(token ? { token } : {}) }, admin, editing ? 'put' : 'post')
            setSelected(saved.id); setEditing(null); setToken(''); clearQuery()
          }) }}>
            <label className="block">{t('mcp.name')}<input required className={inputClass} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
            <label className="block">{t('mcp.endpoint')}<select className={inputClass} value={form.endpoint_ref} onChange={e => { const item = endpoints.data?.find(x => x.ref === e.target.value); if (item) setForm({ ...form, endpoint_ref: item.ref, backend: item.backend, dialect: item.backend === 'duckdb' ? 'duckdb' : 'postgres', version_id: null }) }}>
              {endpoints.data?.map(item => <option key={item.ref} value={item.ref}>{item.ref} · {item.backend}</option>)}
            </select></label>
            <label className="block">{t('mcp.allowedNotebooks')}<select multiple className={inputClass} value={form.notebooks} onChange={e => setForm({ ...form, notebooks: Array.from(e.target.selectedOptions, o => o.value) })}>
              {notebooks.data?.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
            </select></label>
            <label className="block">{t('mcp.tables')}<textarea className={inputClass} rows={3} value={tableText} onChange={e => setTableText(e.target.value)} /></label>
            {form.backend === 'duckdb' && <label className="block">{t('mcp.version')}<select required className={inputClass} value={form.version_id || ''} onChange={e => setForm({ ...form, version_id: e.target.value })}>
              <option value="">{t('mcp.choose')}</option>{versions.data?.map(v => <option key={v.id} value={v.manifest.version_id}>{v.manifest.version_id}</option>)}
            </select></label>}
            {form.backend === 'toolbox' && <>
              <label className="block">{t('mcp.toolNames')}<input className={inputClass} value={form.curated_tools.join(',')} onChange={e => setForm({ ...form, curated_tools: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })} /></label>
              <label className="block">{t('mcp.schemaTool')}<input className={inputClass} value={form.schema_tool || ''} onChange={e => setForm({ ...form, schema_tool: e.target.value })} /></label>
            </>}
            <label className="block">{t('mcp.token')}<input className={inputClass} type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} /></label>
            <div className="grid gap-3 sm:grid-cols-3">
              <label>{t('mcp.rowLimit')}<input className={inputClass} type="number" min={1} max={1000} value={form.max_rows} onChange={e => setForm({ ...form, max_rows: Number(e.target.value) })} /></label>
              <label>{t('mcp.byteLimit')}<input className={inputClass} type="number" min={1024} max={262144} value={form.max_bytes} onChange={e => setForm({ ...form, max_bytes: Number(e.target.value) })} /></label>
              <label>{t('mcp.timeout')}<input className={inputClass} type="number" min={1} max={30} value={form.timeout_seconds} onChange={e => setForm({ ...form, timeout_seconds: Number(e.target.value) })} /></label>
            </div>
            <label className="flex gap-2"><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} />{t('mcp.enabled')}</label>
            <p className="text-sm text-muted-foreground">{t('mcp.saveNotice')}</p>
            <Button disabled={busy} type="submit">{t('mcp.save')}</Button>
          </form>}
        </>}
      </div>
    </details>
  </section>
}
