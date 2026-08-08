import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import HoldingsTab from './HoldingsTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getHoldings: vi.fn(),
    getFundInsights: vi.fn(),
    getTransactions: vi.fn(),
  },
}))

vi.mock('./FundDetailDrawer', () => ({
  default: ({ fund, onClose }: any) =>
    fund ? (
      <div data-testid="fund-drawer">
        <span>Drawer:{fund.Fund}</span>
        <button type="button" onClick={onClose}>Close Drawer</button>
      </div>
    ) : null,
}))

const baseHoldings = [
  {
    Fund: 'HDFC Mid-Cap Opportunities Fund',
    Category: 'Equity',
    'Cap Type': 'Mid Cap',
    'Market Value': 500000,
    Gain: 120000,
    'Gain%': 31.5,
    'Weight%': 35.0,
    'Day Chg.': 2500,
    TER: '0.85',
    TER_fallback: false,
    ISIN: 'INF179K01BE2',
  },
  {
    Fund: 'Parag Parikh Flexi Cap Fund',
    Category: 'Equity',
    'Cap Type': 'Flexi Cap',
    'Market Value': 300000,
    Gain: 30000,
    'Gain%': 11.0,
    'Weight%': 21.0,
    'Day Chg.': -500,
    TER: '0.65',
    TER_fallback: false,
    ISIN: 'INF879O01019',
  },
  {
    Fund: 'Neutral Watch Fund',
    Category: 'Equity',
    'Cap Type': 'Large Cap',
    'Market Value': 80000,
    Gain: 2000,
    'Gain%': 2.5,
    'Weight%': 5.0,
    'Day Chg.': 0,
    TER: '',
    TER_fallback: false,
    ISIN: 'INFNEUTRAL01',
  },
  {
    Fund: 'Review Loser Fund',
    Category: 'Equity',
    'Cap Type': 'Small Cap',
    'Market Value': 60000,
    Gain: -8000,
    'Gain%': -11.8,
    'Weight%': 4.0,
    'Day Chg.': null,
    TER: '1.2',
    TER_fallback: true,
    ISIN: 'INFLOSER01',
  },
]

describe('HoldingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-holdings', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: baseHoldings,
      cap_types: ['Mid Cap', 'Flexi Cap', 'Large Cap', 'Small Cap'],
    } as any)
    vi.mocked(apiClient.getFundInsights).mockResolvedValue({} as any)
    vi.mocked(apiClient.getTransactions).mockResolvedValue([] as any)
  })

  it('renders search input, concentration risk warning, and holding cards', async () => {
    renderWithProviders(<HoldingsTab />)

    expect(screen.getByRole('heading', { name: 'Holdings Explorer' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Search Asset Ledger/i)).toBeInTheDocument()

    expect(await screen.findByText(/CONCENTRATION RISK AUDIT/i)).toBeInTheDocument()
    expect(screen.getByText('HDFC Mid-Cap Opportunities Fund')).toBeInTheDocument()
    expect(screen.getByText('Parag Parikh Flexi Cap Fund')).toBeInTheDocument()
    expect(screen.getAllByText('STRONG').length).toBeGreaterThan(0)
    expect(screen.getAllByText('WATCH').length).toBeGreaterThan(0)
    expect(screen.getAllByText('NEUTRAL').length).toBeGreaterThan(0)
    expect(screen.getAllByText('REVIEW').length).toBeGreaterThan(0)
    expect(screen.getByText(/~1\.20%/)).toBeInTheDocument()
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
  })

  it('opens and closes fund detail drawer on card click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HoldingsTab />)
    expect(await screen.findByText('HDFC Mid-Cap Opportunities Fund')).toBeInTheDocument()

    await user.click(screen.getByText('HDFC Mid-Cap Opportunities Fund'))
    expect(await screen.findByTestId('fund-drawer')).toBeInTheDocument()
    expect(screen.getByText('Drawer:HDFC Mid-Cap Opportunities Fund')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Close Drawer' }))
    await waitFor(() => {
      expect(screen.queryByTestId('fund-drawer')).not.toBeInTheDocument()
    })
  })

  it('filters by cap type and searches the ledger', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HoldingsTab />)
    expect(await screen.findByText('Parag Parikh Flexi Cap Fund')).toBeInTheDocument()

    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Small Cap' }))
    await waitFor(() => {
      expect(apiClient.getHoldings).toHaveBeenCalledWith(
        'sid-holdings',
        expect.objectContaining({ cap_filter: 'Small Cap' }),
      )
    })

    const search = screen.getByPlaceholderText(/Search Asset Ledger/i)
    await user.type(search, 'HDFC')
    await waitFor(() => {
      expect(apiClient.getHoldings).toHaveBeenCalledWith(
        'sid-holdings',
        expect.objectContaining({ search: 'HDFC' }),
      )
    }, { timeout: 5000 })
  })

  it('shows loading skeletons while holdings fetch', async () => {
    vi.mocked(apiClient.getHoldings).mockReturnValue(new Promise(() => {}) as any)
    renderWithProviders(<HoldingsTab />)
    expect(screen.getByRole('heading', { name: 'Holdings Explorer' })).toBeInTheDocument()
    await waitFor(() => {
      expect(document.querySelector('.MuiSkeleton-root')).toBeTruthy()
    })
  })

  it('hides concentration alert when no fund exceeds 25% weight', async () => {
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        {
          Fund: 'Balanced A',
          Category: 'Equity',
          'Cap Type': 'Large Cap',
          'Market Value': 100000,
          Gain: 10000,
          'Gain%': 10,
          'Weight%': 20,
          'Day Chg.': 100,
          TER: '0.5',
          TER_fallback: false,
          ISIN: 'A',
        },
        {
          Fund: 'Balanced B',
          Category: 'Equity',
          'Cap Type': 'Mid Cap',
          'Market Value': 90000,
          Gain: 5000,
          'Gain%': 6,
          'Weight%': 18,
          'Day Chg.': -50,
          TER: null,
          TER_fallback: false,
          ISIN: 'B',
        },
      ],
      cap_types: ['Large Cap', 'Mid Cap'],
    } as any)

    renderWithProviders(<HoldingsTab />)
    expect(await screen.findByText('Balanced A')).toBeInTheDocument()
    expect(screen.queryByText(/CONCENTRATION RISK AUDIT/i)).not.toBeInTheDocument()
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('handles empty holdings list without crashing', async () => {
    vi.mocked(apiClient.getHoldings).mockResolvedValue({ holdings: [], cap_types: [] } as any)
    renderWithProviders(<HoldingsTab />)
    expect(await screen.findByText(/ACTIVE ASSETS \(0 INSTRUMENTS\)/i)).toBeInTheDocument()
    expect(screen.queryByText(/CONCENTRATION RISK AUDIT/i)).not.toBeInTheDocument()
  })
})
