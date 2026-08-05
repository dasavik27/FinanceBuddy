import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import RebalanceTab from './RebalanceTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getRebalancePlan: vi.fn(),
  },
}))

describe('RebalanceTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-rebalance', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getRebalancePlan).mockResolvedValue({
      drift_score: 14.2,
      status: 'Moderate Divergence',
      drifts: { Equity: 15.0, Debt: -10.0 },
      orders: [
        {
          action: 'SELL',
          fund: 'Quant Small Cap Fund',
          amount: 50000,
          note: 'Excess equity allocation beyond target envelope',
        },
        {
          action: 'BUY',
          fund: 'HDFC Corporate Bond Fund',
          amount: 50000,
          note: 'Deficit debt allocation against target envelope',
        },
      ],
    } as any)
  })

  it('renders rebalancing target profiles, drift score, and suggested rebalance orders', async () => {
    renderWithProviders(<RebalanceTab />)

    expect(screen.getByRole('heading', { name: 'Strategic Rebalancing' })).toBeInTheDocument()
    expect(screen.getByText('TARGET ARCHITECTURE')).toBeInTheDocument()
    expect(screen.getByText('Auto (Detected)')).toBeInTheDocument()
    expect(screen.getByText('Balanced Profile')).toBeInTheDocument()

    expect(await screen.findByText(/14.2%/i)).toBeInTheDocument()
    expect(screen.getByText('Moderate Divergence')).toBeInTheDocument()
    expect(screen.getByText('Quant Small Cap Fund')).toBeInTheDocument()
    expect(screen.getByText('HDFC Corporate Bond Fund')).toBeInTheDocument()

    // Switch profile
    const balancedBtn = screen.getByText('Balanced Profile')
    await userEvent.click(balancedBtn)
    expect(apiClient.getRebalancePlan).toHaveBeenCalledWith('sid-rebalance', { profile: 'Balanced' })
  })
})
