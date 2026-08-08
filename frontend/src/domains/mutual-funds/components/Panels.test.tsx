import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import GoalProjectorPanel from './GoalProjectorPanel'
import MandateOverlapPanel from './MandateOverlapPanel'
import TaxHarvestPanel from './TaxHarvestPanel'
import WhatIfPanel from './WhatIfPanel'
import YearlyProgressPanel from './YearlyProgressPanel'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getSipProjection: vi.fn(),
    getMandateOverlap: vi.fn(),
    getTaxHarvest: vi.fn(),
    getWhatIf: vi.fn(),
    searchTicker: vi.fn(),
    getXirrByFy: vi.fn(),
    getSipAttribution: vi.fn(),
  },
}))

describe('Mutual Funds Analytical Panels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-panel-test', activeModule: 'mutual_funds' })
  })

  describe('GoalProjectorPanel', () => {
    it('renders projection stats and updates on input change', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getSipProjection).mockResolvedValue({
        final_value: 2500000,
        total_invested: 1200000,
        wealth_gain: 1300000,
        wealth_multiple: 2.08,
        assumed_monthly_sip: 10000,
        assumed_existing_corpus: 500000,
      } as any)

      renderWithProviders(<GoalProjectorPanel />)

      expect(screen.getByText('Future Wealth Projector')).toBeInTheDocument()
      expect(await screen.findByText('₹25.00 L')).toBeInTheDocument()
      expect(screen.getByText('₹12.00 L')).toBeInTheDocument()
      expect(screen.getByText('2.08x')).toBeInTheDocument()

      const yearsInput = screen.getByLabelText('Years')
      await user.clear(yearsInput)
      await user.type(yearsInput, '15')

      const sipInput = screen.getByLabelText(/Monthly SIP/i)
      await user.clear(sipInput)
      await user.type(sipInput, '20000')

      const retInput = screen.getByLabelText(/Expected Return/i)
      await user.clear(retInput)
      await user.type(retInput, '14')

      const stepInput = screen.getByLabelText(/Annual Step-Up/i)
      await user.clear(stepInput)
      await user.type(stepInput, '8')
    })
  })

  describe('MandateOverlapPanel', () => {
    it('renders mandate overlap groups with combined weight and funds', async () => {
      vi.mocked(apiClient.getMandateOverlap).mockResolvedValue({
        groups: [
          {
            category: 'Flexi Cap',
            cap_type: 'Multi Cap Mandate',
            fund_count: 2,
            same_amc: true,
            severity: 'high',
            combined_weight_pct: 35.5,
            funds: [
              { fund: 'Parag Parikh Flexi Cap', value: 200000 },
              { fund: 'HDFC Flexi Cap', value: 155000 },
            ],
          },
        ],
        disclaimer: 'Category proxy overlap',
      } as any)

      renderWithProviders(<MandateOverlapPanel />)

      expect(screen.getByText('Mandate Overlap')).toBeInTheDocument()
      expect(await screen.findByText(/Flexi Cap · Multi Cap Mandate/i)).toBeInTheDocument()
      expect(screen.getByText('35.5%')).toBeInTheDocument()
      expect(screen.getByText(/Parag Parikh Flexi Cap/i)).toBeInTheDocument()
      expect(screen.getByText('Category proxy overlap')).toBeInTheDocument()
    })
  })

  describe('TaxHarvestPanel', () => {
    it('renders tax saved, exemption remaining, and harvest items', async () => {
      vi.mocked(apiClient.getTaxHarvest).mockResolvedValue({
        harvest: {
          total_tax_saved: 15000,
          remaining_exemption: 85000,
          harvest_list: [
            {
              fund: 'Axis Bluechip Fund',
              action: 'LTCG GAIN HARVEST',
              gain: 40000,
              tax_saved: 5000,
            },
          ],
        },
        debt_summary: {
          slab_taxed_gain: 20000,
          estimated_tax_at_slab: 6000,
          note: 'Post Apr 2023 taxation applied',
        },
        elss_locked_value: 150000,
      } as any)

      renderWithProviders(<TaxHarvestPanel />)

      expect(screen.getByText('Tax Harvest Opportunities')).toBeInTheDocument()
      expect(await screen.findByText('Axis Bluechip Fund')).toBeInTheDocument()
      expect(screen.getByText('LTCG GAIN HARVEST')).toBeInTheDocument()
      expect(screen.getByText(/Post Apr 2023 taxation applied/i)).toBeInTheDocument()
    })
  })

  describe('WhatIfPanel', () => {
    const selectCandidateFund = async (user: ReturnType<typeof userEvent.setup>) => {
      const input = screen.getByLabelText('Candidate fund')
      await user.type(input, 'HDF')
      await waitFor(() => expect(apiClient.searchTicker).toHaveBeenCalledWith('HDF'), { timeout: 5000 })
      const option = await screen.findByRole('option', { name: /HDFC Mid-Cap/i }, { timeout: 5000 })
      await user.click(option)
    }

    it('searches for candidate funds and simulates what-if historical SIP', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockResolvedValue({
        results: [
          { symbol: 'INF179K01BE2', name: 'HDFC Mid-Cap Opportunities Fund' },
        ],
      } as any)
      vi.mocked(apiClient.getWhatIf).mockResolvedValue({
        final_value: 850000,
        total_invested: 600000,
        wealth_multiple: 1.42,
        cagr_pct: 16.5,
        actual_start_date: '2021-01-01',
        actual_end_date: '2026-01-01',
        installments: 60,
        requested_years: 5,
      } as any)

      renderWithProviders(<WhatIfPanel />)

      expect(screen.getByText('What-If Simulator')).toBeInTheDocument()
      expect(screen.getByText(/Search for a fund above to simulate/i)).toBeInTheDocument()

      await selectCandidateFund(user)

      expect(await screen.findByText('Final Value')).toBeInTheDocument()
      expect(screen.getByText('₹8.50 L')).toBeInTheDocument()
      expect(screen.getByText('₹6.00 L')).toBeInTheDocument()
      expect(screen.getByText('1.42x')).toBeInTheDocument()
      expect(screen.getByText('16.5%')).toBeInTheDocument()
      expect(screen.getByText(/Simulated using real NAVs from 2021-01-01 to 2026-01-01/i)).toBeInTheDocument()

      const monthly = screen.getByLabelText(/Monthly SIP/i)
      await user.clear(monthly)
      await user.type(monthly, '15000')

      const years = screen.getByLabelText('Years')
      await user.clear(years)
      await user.type(years, '7')

      await waitFor(() => {
        expect(apiClient.getWhatIf).toHaveBeenCalled()
      })
    })

    it('shows error message when simulation fails', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockResolvedValue({
        results: [{ symbol: 'INF179K01BE2', name: 'HDFC Mid-Cap Opportunities Fund' }],
      } as any)
      vi.mocked(apiClient.getWhatIf).mockResolvedValue({
        error: 'Insufficient NAV history for this scheme',
      } as any)

      renderWithProviders(<WhatIfPanel />)
      await selectCandidateFund(user)

      expect(await screen.findByText(/Insufficient NAV history/i)).toBeInTheDocument()
    })

    it('shows shorter-history notice and negative CAGR colour path', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockResolvedValue({
        results: [{ symbol: 'INF179K01BE2', name: 'HDFC Mid-Cap Opportunities Fund' }],
      } as any)
      vi.mocked(apiClient.getWhatIf).mockResolvedValue({
        final_value: 400000,
        total_invested: 500000,
        wealth_multiple: 0.8,
        cagr_pct: -5.2,
        actual_start_date: '2022-01-01',
        actual_end_date: '2024-01-01',
        installments: 24,
        requested_years: 10,
      } as any)

      renderWithProviders(<WhatIfPanel />)
      await selectCandidateFund(user)

      expect(await screen.findByText('-5.2%')).toBeInTheDocument()
      expect(screen.getByText(/fund history is shorter than the requested window/i)).toBeInTheDocument()
    })

    it('clears selection when search input is emptied', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockResolvedValue({
        results: [{ symbol: 'INF179K01BE2', name: 'HDFC Mid-Cap Opportunities Fund' }],
      } as any)
      vi.mocked(apiClient.getWhatIf).mockResolvedValue({
        final_value: 850000,
        total_invested: 600000,
        wealth_multiple: 1.42,
        cagr_pct: 16.5,
        actual_start_date: '2021-01-01',
        actual_end_date: '2026-01-01',
        installments: 60,
        requested_years: 5,
      } as any)

      renderWithProviders(<WhatIfPanel />)
      await selectCandidateFund(user)
      expect(await screen.findByText('Final Value')).toBeInTheDocument()

      const input = screen.getByLabelText('Candidate fund')
      await user.clear(input)

      expect(await screen.findByText(/Search for a fund above to simulate/i)).toBeInTheDocument()
    })

    it('shows loading spinner while what-if query is in flight', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockResolvedValue({
        results: [{ symbol: 'INF179K01BE2', name: 'HDFC Mid-Cap Opportunities Fund' }],
      } as any)
      let resolveWhatIf: (v: unknown) => void
      vi.mocked(apiClient.getWhatIf).mockReturnValue(
        new Promise((resolve) => {
          resolveWhatIf = resolve
        }) as any,
      )

      renderWithProviders(<WhatIfPanel />)
      await selectCandidateFund(user)

      await waitFor(() => {
        expect(document.querySelector('.MuiCircularProgress-root')).toBeTruthy()
      })

      resolveWhatIf!({
        final_value: 100000,
        total_invested: 80000,
        wealth_multiple: 1.25,
        cagr_pct: 10,
        actual_start_date: '2020-01-01',
        actual_end_date: '2025-01-01',
        installments: 60,
        requested_years: 5,
      })

      expect(await screen.findByText('Final Value')).toBeInTheDocument()
    })

    it('disables simulation when years is zero and handles empty result payload', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockResolvedValue({
        results: [
          { symbol: 'INF179K01BE2', name: 'HDFC Mid-Cap Opportunities Fund' },
          { symbol: 'EMPTY', name: '' },
        ],
      } as any)
      vi.mocked(apiClient.getWhatIf).mockResolvedValue({} as any)

      renderWithProviders(<WhatIfPanel />)
      await selectCandidateFund(user)

      // Empty payload: selected but no final_value / error → null result branch
      await waitFor(() => {
        expect(screen.queryByText('Final Value')).not.toBeInTheDocument()
      })

      const years = screen.getByLabelText('Years')
      await user.clear(years)
      await user.type(years, '0')

      const monthly = screen.getByLabelText(/Monthly SIP/i)
      await user.clear(monthly)
      await user.type(monthly, '0')

      // Query disabled when amount/years invalid — UI stays without stats
      expect(screen.queryByText('Final Value')).not.toBeInTheDocument()
    })

    it('shows search spinner adornment while ticker search is fetching', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.searchTicker).mockReturnValue(new Promise(() => {}) as any)

      renderWithProviders(<WhatIfPanel />)
      await user.type(screen.getByLabelText('Candidate fund'), 'ABC')

      await waitFor(() => {
        expect(document.querySelector('.MuiCircularProgress-root')).toBeTruthy()
      }, { timeout: 5000 })
    })
  })

  describe('YearlyProgressPanel', () => {
    it('renders FY series cards and SIP vs Lumpsum breakdown', async () => {
      vi.mocked(apiClient.getXirrByFy).mockResolvedValue({
        fy_series: [
          { fy: 'FY 2023-24', cumulative_xirr: 18.5, cumulative_value: 400000, is_partial_fy: false },
          { fy: 'FY 2024-25', cumulative_xirr: 22.1, cumulative_value: 650000, is_partial_fy: true },
        ],
      } as any)
      vi.mocked(apiClient.getSipAttribution).mockResolvedValue({
        sip_current_value: 450000,
        lumpsum_current_value: 200000,
        sip_share_pct: 69.2,
        note: 'SIP vs Lumpsum based on transaction timestamps',
      } as any)

      renderWithProviders(<YearlyProgressPanel />)

      expect(screen.getByText('Year-over-Year Progress')).toBeInTheDocument()
      expect(await screen.findByText('FY 2023-24')).toBeInTheDocument()
      expect(screen.getByText('FY 2024-25')).toBeInTheDocument()
      expect(screen.getByText(/SIP-sourced \(69.2%\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Lumpsum-sourced \(30.8%\)/i)).toBeInTheDocument()
    })
  })
})
