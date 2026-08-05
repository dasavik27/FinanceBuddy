import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
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

describe('JourneyTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-journey', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getJourney).mockResolvedValue({
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
      ],
    } as any)
  })

  it('renders capital accumulation curve, flow charts, hall of fame and shame', async () => {
    renderWithProviders(<JourneyTab />)

    expect(screen.getByRole('heading', { name: 'Wealth Journey' })).toBeInTheDocument()
    expect(await screen.findByText('CAPITAL ACCUMULATION CURVE')).toBeInTheDocument()
    expect(screen.getByText('CAPITAL FLOW VELOCITY')).toBeInTheDocument()
    expect(screen.getByText('HALL OF FAME')).toBeInTheDocument()
    expect(screen.getByText('HALL OF SHAME')).toBeInTheDocument()

    expect(screen.getByText('Quant Small Cap Fund')).toBeInTheDocument()
    expect(screen.getByText('Aditya Birla Sun Life Frontline Equity')).toBeInTheDocument()

    // Switch flow view to monthly
    const monthlyBtn = screen.getByRole('button', { name: 'Monthly' })
    await userEvent.click(monthlyBtn)
    expect(monthlyBtn).toHaveAttribute('aria-pressed', 'true')
  })
})
