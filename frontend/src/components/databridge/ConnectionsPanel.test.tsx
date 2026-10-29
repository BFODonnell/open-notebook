import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ConnectionsPanel } from './ConnectionsPanel'

const mocks = vi.hoisted(() => ({ status: vi.fn(), connections: vi.fn(), write: vi.fn(), endpoints: vi.fn(), action: vi.fn() }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: () => ({ data: [{ id: 'notebook:1', name: 'Research' }] }) }))
vi.mock('@/lib/hooks/use-databridge-mcp', () => ({
  useMCPStatus: mocks.status, useMCPConnections: mocks.connections, useMCPEndpoints: mocks.endpoints,
  useMCPVersions: () => ({ data: [] }), useMCPRuns: () => ({ data: [] }), useMCPAction: mocks.action,
}))
vi.mock('@/lib/api/databridge-mcp', () => ({ mcpApi: { write: mocks.write, read: vi.fn() } }))

const connection = { id: 'db_connection:1', name: 'Synthetic', backend: 'duckdb', endpoint_ref: 'duckdb', dialect: 'duckdb', notebooks: ['notebook:1'], tables: { sample: ['value'] }, curated_tools: [], schema_tool: null, version_id: 'version-1', max_rows: 2, max_bytes: 1024, timeout_seconds: 10, enabled: true, approved_fingerprint: 'approved' }

function selectConnection() {
  fireEvent.change(screen.getByLabelText('mcp.notebook'), { target: { value: 'notebook:1' } })
  fireEvent.change(screen.getByLabelText('mcp.connection'), { target: { value: connection.id } })
}

describe('ConnectionsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.status.mockReturnValue({ data: { enabled: true } })
    mocks.connections.mockReturnValue({ data: [connection] })
    mocks.endpoints.mockReturnValue({ data: [{ ref: 'duckdb', backend: 'duckdb' }] })
    mocks.action.mockReturnValue({ mutate: (fn: () => Promise<unknown>) => { void fn() }, isPending: false })
    mocks.write.mockResolvedValue({ id: 'db_query_plan:1', sql: 'SELECT value FROM sample LIMIT 2', approval_token: 'one-use-secret', version_id: 'version-1' })
  })

  it('preserves the existing settings UI when MCP is disabled', () => {
    mocks.status.mockReturnValue({ data: { enabled: false } })
    expect(render(<ConnectionsPanel />).container).toBeEmptyDOMElement()
  })

  it('shows loading and safe error feedback', () => {
    mocks.connections.mockReturnValue({ isFetching: true, isError: true })
    render(<ConnectionsPanel />)
    expect(screen.getByRole('status')).toHaveTextContent('mcp.loading')
    expect(screen.getByRole('alert')).toHaveTextContent('mcp.actionError')
  })

  it('requires a separate explicit execution approval and renders results as text', async () => {
    const { container } = render(<ConnectionsPanel />)
    selectConnection()
    fireEvent.click(screen.getByText('mcp.review'))
    await screen.findByText('SELECT value FROM sample LIMIT 2')
    expect(mocks.write).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('one-use-secret')).not.toBeInTheDocument()
    mocks.write.mockResolvedValueOnce({ id: 'db_query_run:1', rows: [{ value: '<img src=x onerror=alert(1)>' }], row_count: 1, result_sha256: 'hash', version_id: 'version-1' })
    fireEvent.click(screen.getByText('mcp.approveExecute'))
    await screen.findByText('<img src=x onerror=alert(1)>')
    expect(container.querySelector('img')).toBeNull()
    expect(mocks.write).toHaveBeenLastCalledWith('/query/plans/db_query_plan:1/execute', { notebook_id: 'notebook:1', approval_token: 'one-use-secret' })
    expect(screen.queryByText('mcp.approveExecute')).not.toBeInTheDocument()
  })

  it('discards approval when the query changes', async () => {
    render(<ConnectionsPanel />)
    selectConnection()
    fireEvent.click(screen.getByText('mcp.review'))
    await screen.findByText('mcp.approveExecute')
    fireEvent.change(screen.getByLabelText('mcp.sql'), { target: { value: 'SELECT SUM(value) FROM sample' } })
    expect(screen.queryByText('mcp.approveExecute')).not.toBeInTheDocument()
    expect(mocks.write).toHaveBeenCalledTimes(1)
  })

  it('prevents review of an unapproved connection', () => {
    mocks.connections.mockReturnValue({ data: [{ ...connection, approved_fingerprint: null }] })
    render(<ConnectionsPanel />)
    selectConnection()
    expect(screen.getByText('mcp.review')).toBeDisabled()
  })

  it('clears the administrator password input and locks administration', async () => {
    render(<ConnectionsPanel />)
    fireEvent.click(screen.getByText('mcp.administration'))
    fireEvent.change(screen.getByLabelText('mcp.adminKey'), { target: { value: 'administrator-secret' } })
    fireEvent.click(screen.getByText('mcp.unlock'))
    await waitFor(() => expect(mocks.endpoints).toHaveBeenLastCalledWith('administrator-secret'))
    expect(screen.getByLabelText('mcp.adminKey')).toHaveValue('')
    expect(localStorage.getItem('administrator-secret')).toBeNull()
    fireEvent.click(screen.getByText('mcp.lock'))
    expect(screen.queryByText('mcp.add')).not.toBeInTheDocument()
    expect(mocks.endpoints).toHaveBeenLastCalledWith('')
  })
})
