import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { UsagePanel } from './UsagePanel'

const useUsage = vi.fn()
vi.mock('@/lib/hooks/use-databridge-usage', () => ({
  useDataBridgeUsage: (...args: unknown[]) => useUsage(...args),
}))

const page = {
  enabled: true,
  managed_model: 'gpt-6-astra',
  budget_limit_usd: 20,
  budget_remaining_usd: 19,
  total_pages: 2,
  records: [{
    request_id: 'request-1', timestamp: '2026-10-29T12:00:00Z',
    model: 'gpt-6-astra', input_tokens: 100, output_tokens: 20,
    cached_input_tokens: null, reasoning_tokens: 5,
    estimated_cost_usd: null, status: 'success',
  }],
}

describe('UsagePanel', () => {
  beforeEach(() => useUsage.mockReturnValue({ data: page, refetch: vi.fn() }))

  it('renders unknown pricing as unavailable, and real token categories', () => {
    render(<UsagePanel />)
    expect(screen.getByText('databridge.unavailable')).toBeInTheDocument()
    expect(screen.getByText('100 / 20')).toBeInTheDocument()
    expect(screen.getByText('databridge.cached: —')).toBeInTheDocument()
    expect(screen.getByText('databridge.reasoning: 5')).toBeInTheDocument()
  })

  it('renders small USD amounts without rounding them to free', () => {
    useUsage.mockReturnValue({ data: { ...page, records: [{ ...page.records[0], estimated_cost_usd: 0.000012 }] }, refetch: vi.fn() })
    render(<UsagePanel />)
    expect(screen.getByText('$0.000012 USD')).toBeInTheDocument()
  })

  it('resets pagination when date range changes', () => {
    render(<UsagePanel />)
    fireEvent.click(screen.getByText('databridge.next'))
    expect(useUsage.mock.lastCall?.[1]).toBe(2)
    fireEvent.change(screen.getByLabelText('databridge.period'), { target: { value: 'all' } })
    expect(useUsage.mock.lastCall).toEqual(['1970-01-01T00:00:00.000Z', 1])
  })

  it('shows budget exhaustion without hiding usage', () => {
    useUsage.mockReturnValue({ data: { ...page, budget_remaining_usd: 0 }, refetch: vi.fn() })
    render(<UsagePanel />)
    expect(screen.getByRole('alert')).toHaveTextContent('databridge.exhausted')
    expect(screen.getByText('100 / 20')).toBeInTheDocument()
  })

  it('shows a retry action on gateway failure', () => {
    const refetch = vi.fn()
    useUsage.mockReturnValue({ isError: true, refetch })
    render(<UsagePanel />)
    expect(screen.getByRole('alert')).toHaveTextContent('databridge.error')
    fireEvent.click(screen.getByText('databridge.refresh'))
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('leaves upstream settings unchanged when disabled', () => {
    useUsage.mockReturnValue({ data: { enabled: false } })
    const { container } = render(<UsagePanel />)
    expect(container).toBeEmptyDOMElement()
  })
})
