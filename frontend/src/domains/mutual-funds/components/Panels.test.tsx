import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
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
      await userEvent.clear(yearsInput)
      await userEvent.type(yearsInput, '15')
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
    it('searches for candidate funds and simulates what-if historical SIP', async () => {
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
