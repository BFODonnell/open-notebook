import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ResearchTurn } from './ResearchTurn'

const mocks = vi.hoisted(() => ({ get: vi.fn(), action: vi.fn() }))
vi.mock('@/lib/api/databridge-research', () => ({ researchApi: mocks }))
const proposed = { id: 'db_research_turn:1', state: 'awaiting_review', question: 'Total trips?', answer: 'Review required', dataset: { title: 'Synthetic transit', version_id: 'version-one' }, plan: { id: 'plan-one', sql: 'SELECT SUM(trips) FROM data LIMIT 100', expires_at: '2099-01-01' } }

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const rendered = render(<QueryClientProvider client={client}><ResearchTurn id={proposed.id} notebookId="notebook:1" sessionId="chat_session:1" /></QueryClientProvider>)
  return { client, ...rendered }
}

describe('Conversational database approval', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.get.mockResolvedValue(proposed) })

  it('does not execute before explicit review and approval, and never caches the token', async () => {
    const { client } = setup()
    await screen.findByText(proposed.plan.sql)
    expect(mocks.action).not.toHaveBeenCalled()
    expect(screen.queryByText('research.approve')).not.toBeInTheDocument()
    mocks.action.mockResolvedValueOnce({ ...proposed, state: 'awaiting_approval', approval_token: 'memory-only-secret' })
    fireEvent.click(screen.getByText('research.review'))
    await screen.findByText('research.approve')
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.state.data))).not.toContain('memory-only-secret')
    expect(screen.queryByText('memory-only-secret')).not.toBeInTheDocument()
    mocks.action.mockResolvedValueOnce({ ...proposed, state: 'completed', answer: 'Verified total: 700' })
    fireEvent.click(screen.getByText('research.approve'))
    await screen.findByText('Verified total: 700')
    expect(mocks.action).toHaveBeenLastCalledWith(proposed.id, 'execute', { notebook_id: 'notebook:1', session_id: 'chat_session:1' }, { plan_id: 'plan-one', approval_token: 'memory-only-secret' })
    expect(screen.queryByText('research.approve')).not.toBeInTheDocument()
  })

  it('requires fresh review after reload and disables an expired token', async () => {
    mocks.get.mockResolvedValue({ ...proposed, state: 'awaiting_approval' })
    setup()
    await screen.findByText('research.review')
    expect(screen.queryByText('research.approve')).not.toBeInTheDocument()
    mocks.action.mockResolvedValueOnce({ ...proposed, state: 'awaiting_approval', approval_token: 'expired', plan: { ...proposed.plan, expires_at: '2000-01-01' } })
    fireEvent.click(screen.getByText('research.review'))
    expect(await screen.findByText('research.approve')).toBeDisabled()
  })

  it('resumes synthesis without executing SQL again', async () => {
    mocks.get.mockResolvedValue({ ...proposed, state: 'answer_failed' })
    mocks.action.mockResolvedValue({ ...proposed, state: 'completed', answer: 'Recovered answer' })
    setup()
    fireEvent.click(await screen.findByText('research.resume'))
    await screen.findByText('Recovered answer')
    expect(mocks.action).toHaveBeenCalledWith(proposed.id, 'resume', expect.any(Object), undefined)
    expect(screen.queryByText('research.review')).not.toBeInTheDocument()
  })

  it('renders version/provenance and safe trend values without trusting metadata HTML', async () => {
    mocks.get.mockResolvedValue({ ...proposed, state: 'completed', dataset: { ...proposed.dataset, title: '<img src=x onerror=alert(1)>' }, answer: 'Verified', chart: { value_column: 'trips', points: [{ year: 2022, value: '100' }, { year: 2025, value: '250' }], change: '150' }, evidence: { id: 'evidence-one', result_sha256: 'hash' } })
    const { container } = setup()
    await screen.findByText('Verified')
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('version-one')).toBeInTheDocument()
    expect(screen.getByRole('figure')).toHaveTextContent('2022')
    expect(screen.getByText(/"evidence-one"/)).toBeInTheDocument()
  })

  it('reports service/authorization errors without silently retrying', async () => {
    mocks.get.mockRejectedValue(new Error('private diagnostic'))
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('research.error')
    expect(screen.queryByText('private diagnostic')).not.toBeInTheDocument()
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1))
  })
})
