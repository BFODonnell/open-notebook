'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { researchApi, ResearchTurn as Turn } from '@/lib/api/databridge-research'
import { QUERY_KEYS } from '@/lib/api/query-client'

export function ResearchTurn({ id, notebookId, sessionId }: { id: string; notebookId: string; sessionId: string }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [approval, setApproval] = useState<{ plan_id: string; approval_token: string } | null>(null)
  const scope = { notebook_id: notebookId, session_id: sessionId }
  const key = [...QUERY_KEYS.databridgeResearch, id, sessionId, notebookId]
  const query = useQuery({ queryKey: key, queryFn: () => researchApi.get(id, scope), retry: false,
    refetchInterval: state => ['executing', 'synthesizing', 'reviewing'].includes(state.state.data?.state || '') ? 2000 : false })
  const action = useMutation({ mutationFn: (name: 'review' | 'execute' | 'resume') => researchApi.action(id, name, scope, name === 'execute' ? approval! : undefined), retry: false,
    onSuccess: (data: Turn) => {
      const { approval_token, ...safe } = data
      // The bearer approval lives only in component memory, never query cache/storage.
      setApproval(approval_token && data.plan ? { plan_id: data.plan.id, approval_token } : null)
      client.setQueryData(key, safe)
      client.invalidateQueries({ queryKey: QUERY_KEYS.notebookChatSession(sessionId) })
      client.invalidateQueries({ queryKey: QUERY_KEYS.databridgeMCP })
    },
    onError: () => { setApproval(null); client.invalidateQueries({ queryKey: key }); toast.error(t('research.error')) } })
  const turn = query.data
  const turnState = turn?.state
  useEffect(() => {
    if (turnState && ['completed', 'answer_failed', 'failed'].includes(turnState)) {
      client.invalidateQueries({ queryKey: QUERY_KEYS.notebookChatSession(sessionId) })
    }
  }, [turnState, client, sessionId]) // Refresh repaired checkpoints after reload.
  if (!turn) return <p role={query.isError ? 'alert' : 'status'}>{t(query.isError ? 'research.error' : 'research.loading')}</p>
  const canReview = !!turn.plan && ['awaiting_review', 'awaiting_approval', 'failed'].includes(turn.state)
  const canResume = ['answer_failed', 'evidence_ready', 'executing', 'synthesizing'].includes(turn.state)
  const max = Math.max(1, ...(turn.chart?.points.map(p => Math.abs(Number(p.value))) || []))
  return <section className="space-y-3 rounded border p-3 text-sm" aria-label={t('research.title')}>
    <p className="font-semibold">{t('research.title')}</p>
    <p>{turn.question}</p>
    <p role="status">{t('research.status')}: <code>{turn.state}</code></p>
    {turn.dataset && <p className="break-all">{turn.dataset.title}<br />{t('research.version')}: <code>{turn.dataset.version_id}</code></p>}
    {turn.plan && <><pre className="overflow-auto whitespace-pre-wrap text-xs">{turn.plan.sql}</pre><p>{t('research.expiry')}: {turn.plan.expires_at}</p></>}
    <p className="text-muted-foreground">{t('research.notice')}</p>
    {canReview && <Button variant="outline" disabled={action.isPending} onClick={() => { setApproval(null); action.mutate('review') }}>{t('research.review')}</Button>}
    {approval && turn.state === 'awaiting_approval' && approval.plan_id === turn.plan?.id && <Button disabled={action.isPending || (turn.plan?.expires_at || '') < new Date().toISOString()} onClick={() => action.mutate('execute')}>{t('research.approve')}</Button>}
    {canResume && <Button variant="outline" disabled={action.isPending} onClick={() => action.mutate('resume')}>{t('research.resume')}</Button>}
    {action.isError && <p role="alert" className="text-destructive">{t('research.error')}</p>}
    {['completed', 'answer_failed', 'failed', 'blocked'].includes(turn.state) && <p className="whitespace-pre-wrap">{turn.answer}</p>}
    {turn.chart && <figure aria-label={t('research.trend')} className="space-y-2">
      <figcaption>{t('research.trend')}: {turn.chart.value_column}</figcaption>
      {turn.chart.points.map(point => <div key={point.year} className="grid grid-cols-[4rem_1fr_5rem] items-center gap-2"><span>{point.year}</span><div className="h-3 rounded bg-teal" style={{ width: `${Math.abs(Number(point.value)) / max * 100}%` }} /><span>{point.value}</span></div>)}
      <p className="text-xs text-muted-foreground">{t('research.chartNotice')}</p>
    </figure>}
    <details><summary>{t('research.provenance')}</summary><pre className="max-h-80 overflow-auto text-xs">{JSON.stringify({ dataset: turn.dataset, plan: turn.plan, evidence: turn.evidence }, null, 2)}</pre></details>
  </section>
}
