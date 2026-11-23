import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Explorer, publisherName } from './Explorer'

const mocks = vi.hoisted(() => ({ search: vi.fn(), detail: vi.fn(), imports: vi.fn(), action: vi.fn(), preflight: vi.fn(), import: vi.fn(), control: vi.fn() }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: () => ({ data: [{ id: 'notebook:1', name: 'Research' }] }) }))
vi.mock('@/lib/hooks/use-databridge-catalog', () => ({ useCatalogSearch: mocks.search, useCatalogDetail: mocks.detail, useImports: mocks.imports, useCatalogAction: mocks.action }))
vi.mock('@/lib/api/databridge-catalog', () => ({ catalogApi: { preflight: mocks.preflight, import: mocks.import, control: mocks.control } }))
vi.mock('./ConnectionsPanel', () => ({ ConnectionsPanel: (props: { initialNotebook: string; initialConnection: string }) => <div data-testid="query-panel">{props.initialNotebook} {props.initialConnection}</div> }))

const profile = { rows: 1, columns: [{ original: 'NTD ID', column: 'c_1_ntd_id', type: 'VARCHAR' }], preview: [{ c_1_ntd_id: '00001' }] }
const ready = { status: 'ready', reason: 'VALIDATED', expires_at: '2099-01-01', profile }
const resource = { id: 'db_resource:1', metadata: { title: 'Transit CSV', downloadURL: 'https://data.transportation.gov/data.csv' }, classification: { status: 'checking', reason: 'PREFLIGHT_REQUIRED' } }
const dataset = { id: 'db_catalog:1', title: 'Transit data', description: '<script>untrusted</script>', resources: [resource] }

describe('Open Data Explorer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.search.mockReturnValue({})
    mocks.detail.mockReturnValue({ data: dataset })
    mocks.imports.mockReturnValue({ data: [] })
    mocks.action.mockReturnValue({ mutate: (fn: () => Promise<unknown>) => { void fn() }, isPending: false })
    mocks.preflight.mockResolvedValue(ready)
    mocks.import.mockResolvedValue({ id: 'db_import:1' })
  })

  it('passes search filters and inspects a selected catalog record', async () => {
    mocks.search.mockReturnValue({ data: { results: [dataset], after: 'cursor' } })
    render(<Explorer />)
    fireEvent.change(screen.getByLabelText('explorer.agency'), { target: { value: 'dot' } })
    fireEvent.click(screen.getByText('explorer.search'))
    await waitFor(() => expect(mocks.search).toHaveBeenLastCalledWith({ q: 'National Transit Database', org_slug: 'dot', keyword: '', after: '' }))
    fireEvent.click(screen.getByText('explorer.inspect'))
    expect(mocks.detail).toHaveBeenLastCalledWith(dataset.id)
    fireEvent.click(screen.getByText('explorer.next'))
    expect(mocks.search).toHaveBeenLastCalledWith(expect.objectContaining({ after: 'cursor' }))
  })

  it('requires a valid preview, destination notebook and explicit import confirmation', async () => {
    render(<Explorer />)
    expect(screen.getByText('explorer.import')).toBeDisabled()
    fireEvent.click(screen.getByText('explorer.preview'))
    await screen.findByText('00001')
    expect(screen.getByText('explorer.import')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    fireEvent.click(screen.getByText('explorer.import'))
    expect(mocks.import).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Research')
    fireEvent.click(screen.getByRole('button', { name: 'explorer.confirmImport' }))
    await waitFor(() => expect(mocks.import).toHaveBeenCalledWith(resource.id, 'notebook:1', expect.any(String)))
    await screen.findByText(/explorer.importSubmitted/)
  })

  it('blocks expired and adapter-required resources', () => {
    mocks.detail.mockReturnValue({ data: { ...dataset, resources: [{ ...resource, preflight: { ...ready, expires_at: '2000-01-01' } }, { ...resource, id: 'db_resource:2', classification: { status: 'connector_required', reason: 'FORMAT_ADAPTER_REQUIRED' } }] } })
    render(<Explorer />)
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    for (const button of screen.getAllByText('explorer.import')) expect(button).toBeDisabled()
    expect(screen.getByText(/explorer.connectorRequired/)).toBeInTheDocument()
  })

  it('renders untrusted metadata as text and exposes safe error feedback', () => {
    mocks.search.mockReturnValue({ isError: true })
    const { container } = render(<Explorer />)
    expect(screen.getByText(dataset.description)).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByRole('alert')).toHaveTextContent('explorer.error')
  })

  it('shows processing, cancellation and recoverable jobs', () => {
    mocks.imports.mockReturnValue({ data: [{ id: 'db_import:1', status: 'running', stage: 'downloading', recoverable: true }] })
    render(<Explorer />)
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    expect(screen.getByRole('status')).toHaveTextContent('explorer.downloading')
    fireEvent.click(screen.getByText('explorer.cancel'))
    expect(mocks.control).toHaveBeenCalledWith('db_import:1', 'cancel', 'notebook:1')
    fireEvent.click(screen.getByText('explorer.retry'))
    expect(mocks.control).toHaveBeenCalledWith('db_import:1', 'retry', 'notebook:1')
  })

  it('distinguishes no notebook, loading, empty and failed notebook queries', () => {
    const { rerender } = render(<Explorer />)
    expect(screen.getByText('explorer.noImports')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    expect(mocks.imports).toHaveBeenLastCalledWith('notebook:1')
    expect(screen.queryByText('explorer.noImports')).toBeNull()
    expect(screen.getByText('explorer.emptyNotebook')).toBeInTheDocument()
    mocks.imports.mockReturnValue({ isPending: true })
    rerender(<Explorer />)
    expect(screen.getByText('explorer.loadingImports')).toBeInTheDocument()
    mocks.imports.mockReturnValue({ isError: true })
    rerender(<Explorer />)
    expect(screen.queryByText('explorer.emptyNotebook')).toBeNull()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('requires selection among discovered downloads before preview and import', async () => {
    const children = [1, 2].map(i => ({ ...resource, id: `child:${i}`, metadata: { title: `File ${i}` } }))
    mocks.preflight.mockResolvedValue({ status: 'connector_required', reason: 'DOWNLOAD_SELECTION_REQUIRED', resources: children })
    render(<Explorer />)
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    fireEvent.click(screen.getByText('explorer.preview'))
    await screen.findByLabelText('explorer.selectResource')
    expect(screen.getAllByText('explorer.preview')).toHaveLength(1)
    fireEvent.change(screen.getByLabelText('explorer.selectResource'), { target: { value: 'child:2' } })
    mocks.preflight.mockResolvedValue(ready)
    fireEvent.click(screen.getAllByText('explorer.preview')[1])
    await screen.findByText('00001')
    expect(mocks.preflight).toHaveBeenLastCalledWith('child:2')
    fireEvent.click(screen.getAllByText('explorer.import')[1])
    fireEvent.click(screen.getByRole('button', { name: 'explorer.confirmImport' }))
    await waitFor(() => expect(mocks.import).toHaveBeenCalledWith('child:2', 'notebook:1', expect.any(String)))
  })

  it('reuses the request key when confirmation is reopened for the same resource', async () => {
    render(<Explorer />)
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    fireEvent.click(screen.getByText('explorer.preview'))
    await screen.findByText('00001')
    for (let i = 0; i < 2; i++) {
      fireEvent.click(screen.getByText('explorer.import'))
      fireEvent.click(screen.getByRole('button', { name: 'explorer.confirmImport' }))
      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    }
    expect(mocks.import.mock.calls[0]).toEqual(mocks.import.mock.calls[1])
  })

  it('renders readable publishers without losing structured detail metadata', () => {
    expect(publisherName({ name: 'Federal Transit Administration', '@type': 'Organization' })).toBe('Federal Transit Administration')
    expect(publisherName('[{"name":"FTA"}]')).toBe('FTA')
    expect(publisherName({ '@id': 'unknown' })).toBe('')
  })

  it('opens the scoped MCP query UI and preserves provenance and chat boundary', () => {
    mocks.imports.mockReturnValue({ data: [{ id: 'db_import:1', title: 'Imported', status: 'ready', stage: 'ready', connection_id: 'db_connection:1', version_id: 'version-1', download: { sha256: 'raw-hash' } }] })
    render(<Explorer />)
    fireEvent.change(screen.getByLabelText('explorer.notebook'), { target: { value: 'notebook:1' } })
    fireEvent.click(screen.getByText('explorer.query'))
    expect(screen.getByTestId('query-panel')).toHaveTextContent('notebook:1 db_connection:1')
    expect(screen.getByText('explorer.chatBoundary')).toBeInTheDocument()
    expect(screen.getByText(/"raw-hash"/)).toBeInTheDocument()
  })
})
