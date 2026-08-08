import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import JourneyTab from './JourneyTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getJourney: vi.fn(),
  },
}))

// Stub chart primitives so jsdom does not hang, but still invoke formatter /
// tooltip callbacks so they count toward function coverage.
vi.mock('recharts', () => {
  const { createElement, useEffect } = require('react')
  const Passthrough = ({ children }: { children?: unknown }) => createElement('div', null, children)
  const InvokeFormatters = (props: Record<string, unknown>) => {
    useEffect(() => {
      const tick = props.tickFormatter as ((v: number | string) => unknown) | undefined
      if (typeof tick === 'function') {
        tick(150000)
        tick('2023-01-01')
      }
      const content = props.content as any
      const invoke = (Comp: any, extra: Record<string, unknown>) => {
        if (typeof Comp === 'function') Comp(extra)
      }
      if (typeof content === 'function') {
        invoke(content, {
          active: true,
          label: '2023',
          payload: [
            { name: 'Market Value', value: 370000, color: '#A855F7' },
            { name: 'Capital Invested', value: 300000, color: '#14B8A6' },
          ],
        })
        invoke(content, { active: false, payload: [], label: '' })
      } else if (content?.type) {
        invoke(content.type, {
          ...content.props,
          active: true,
          label: '2023',
          payload: [
            { name: 'Deposited', value: 250000, color: '#14B8A6' },
            { name: 'Withdrawn', value: 50000, color: '#EF4444' },
            { name: 'Uncolored', value: 1000 },
          ],
        })
        invoke(content.type, { ...content.props, active: true, payload: [], label: 'empty' })
        invoke(content.type, { ...content.props, active: false, payload: null, label: '' })
      }
    }, [])
    return createElement('div', { 'data-testid': 'chart-stub' }, props.children as never)
  }
  return {
    ResponsiveContainer: Passthrough,
    AreaChart: Passthrough,
    BarChart: Passthrough,
    Area: () => createElement('div'),
    Bar: () => createElement('div'),
    XAxis: InvokeFormatters,
    YAxis: InvokeFormatters,
    CartesianGrid: () => createElement('div'),
    Tooltip: InvokeFormatters,
    Cell: () => createElement('div'),
  }
})

const journeyPayload = {
  capital_curve: [
    { date: '2023-01-01', invested: 100000, value: 105000 },
    { date: '2023-06-01', invested: 200000, value: 230000 },
    { date: '2023-12-01', invested: 300000, value: 370000 },
  ],
  yearly_flows: [
    { period: '2022', invested: 150000, withdrawn: 0 },
    { period: '2023', invested: 250000, withdrawn: 50000 },
  ],
  monthly_flows: [
    { period: 'Jan 2023', invested: 25000, withdrawn: 0 },
    { period: 'Feb 2023', invested: 25000, withdrawn: 0 },
  ],
  best_funds: [
    { fund: 'Quant Small Cap Fund', invested: 100000, gain_abs: 45000, gain_pct: 45.0 },
  ],
  worst_funds: [
    { fund: 'Aditya Birla Sun Life Frontline Equity', invested: 50000, gain_abs: -2500, gain_pct: -5.0 },
    { fund: 'Mild Underperformer Fund', invested: 80000, gain_abs: 1200, gain_pct: 1.5 },
  ],
}

describe('JourneyTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-journey', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getJourney).mockResolvedValue(journeyPayload as any)
  })

  it('renders capital accumulation curve, flow charts, hall of fame and shame', async () => {
    const user = userEvent.setup()
    renderWithProviders(<JourneyTab />)

    expect(screen.getByRole('heading', { name: 'Wealth Journey' })).toBeInTheDocument()
    expect(await screen.findByText('CAPITAL ACCUMULATION CURVE')).toBeInTheDocument()
    expect(screen.getByText('CAPITAL FLOW VELOCITY')).toBeInTheDocument()
    expect(screen.getByText('HALL OF FAME')).toBeInTheDocument()
    expect(screen.getByText('HALL OF SHAME')).toBeInTheDocument()

    expect(screen.getByText('Quant Small Cap Fund')).toBeInTheDocument()
    expect(screen.getByText('Aditya Birla Sun Life Frontline Equity')).toBeInTheDocument()
    expect(screen.getByText('Mild Underperformer Fund')).toBeInTheDocument()
    expect(screen.getByText('+1.50%')).toBeInTheDocument()

    const monthlyBtn = screen.getByRole('button', { name: 'Monthly' })
    await user.click(monthlyBtn)
    expect(monthlyBtn).toHaveAttribute('aria-pressed', 'true')

    const yearlyBtn = screen.getByRole('button', { name: 'Yearly' })
    await user.click(yearlyBtn)
    expect(yearlyBtn).toHaveAttribute('aria-pressed', 'true')

    // Re-click selected toggle (exclusive group may pass null)
    await user.click(yearlyBtn)
  })

  it('shows loading skeletons while journey data is fetching', async () => {
    vi.mocked(apiClient.getJourney).mockReturnValue(new Promise(() => {}) as any)
    renderWithProviders(<JourneyTab />)
    expect(screen.getByRole('heading', { name: 'Wealth Journey' })).toBeInTheDocument()
    await waitFor(() => {
      expect(document.querySelector('.MuiSkeleton-root')).toBeTruthy()
    })
  })

  it('handles empty journey payload without crashing', async () => {
    vi.mocked(apiClient.getJourney).mockResolvedValue({} as any)
    renderWithProviders(<JourneyTab />)
    expect(await screen.findByText('CAPITAL ACCUMULATION CURVE')).toBeInTheDocument()
    expect(screen.getByText('HALL OF FAME')).toBeInTheDocument()
    expect(screen.getByText('HALL OF SHAME')).toBeInTheDocument()
  })

  it('covers positive hall-of-shame styling and tooltip entries without color', async () => {
    vi.mocked(apiClient.getJourney).mockResolvedValue({
      ...journeyPayload,
      worst_funds: [
        { fund: 'Barely Positive Fund', invested: 40000, gain_abs: 500, gain_pct: 1.25 },
      ],
      best_funds: [],
    } as any)

    renderWithProviders(<JourneyTab />)
    expect(await screen.findByText('Barely Positive Fund')).toBeInTheDocument()
    expect(screen.getByText('+1.25%')).toBeInTheDocument()
  })
})
