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

  it('filters directives by buy/sell and shows tax/exit-load chips', async () => {
    vi.mocked(apiClient.getRebalancePlan).mockResolvedValue({
      drift_score: 9.5,
      status: 'Needs Attention',
      drifts: { Equity: 12.0, Debt: -8.0 },
      orders: [
        {
          action: 'SELL',
          fund: 'Quant Small Cap Fund',
          amount: 50000,
          note: 'Trim equity',
          tax_estimate: 2500,
          exit_load_estimate: 400,
        },
        {
          action: 'BUY',
          fund: 'HDFC Corporate Bond Fund',
          amount: 50000,
          note: 'Add debt',
        },
        {
          action: 'SWITCH',
          fund: 'Parag Parikh Flexi Cap Fund',
          amount: 20000,
          note: 'Rotate mandate',
        },
      ],
    } as any)

    const user = userEvent.setup()
    renderWithProviders(<RebalanceTab />)

    expect(await screen.findByText('Quant Small Cap Fund')).toBeInTheDocument()
    expect(screen.getByText(/~₹2,500 tax/i)).toBeInTheDocument()
    expect(screen.getByText(/exit load/i)).toBeInTheDocument()

    await user.click(screen.getByText('🔴 Trims'))
    expect(screen.getByText('Quant Small Cap Fund')).toBeInTheDocument()
    expect(screen.queryByText('HDFC Corporate Bond Fund')).not.toBeInTheDocument()

    await user.click(screen.getByText('🟢 Buys'))
    expect(screen.getByText('HDFC Corporate Bond Fund')).toBeInTheDocument()
    expect(screen.queryByText('Quant Small Cap Fund')).not.toBeInTheDocument()

    await user.click(screen.getByText('🔄 Switches'))
    expect(screen.getByText('Parag Parikh Flexi Cap Fund')).toBeInTheDocument()
  })

  it('shows equilibrium empty state when there are no orders', async () => {
    vi.mocked(apiClient.getRebalancePlan).mockResolvedValue({
      drift_score: 1.2,
      status: 'Balanced',
      drifts: { Equity: 1.0, Debt: -1.0 },
      orders: [],
    } as any)

    renderWithProviders(<RebalanceTab />)
    expect(await screen.findByText(/Euclidean\/RMSD Equilibrium Achieved/i)).toBeInTheDocument()
  })
})
