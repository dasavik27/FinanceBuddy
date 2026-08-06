import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import AccountsTab from './AccountsTab'
import TransactionsTab from './TransactionsTab'
import InsightsTab from './InsightsTab'
import RulesTab from './RulesTab'
import { apiClient } from '../../../shared/api/client'
import type { BudgetTransaction } from '../types'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getBudgetAccounts: vi.fn(),
    updateBudgetAccount: vi.fn(),
    getBudgetCoverage: vi.fn(),
    getBudgetReconciliation: vi.fn(),
    getBudgetAnomalies: vi.fn(),
    getBudgetEnvelopes: vi.fn(),
    getBudgetForecast: vi.fn(),
    getBudgetRecurring: vi.fn(),
    setBudgetEnvelope: vi.fn(),
    getBudgetRules: vi.fn(),
    getBudgetMatchTypes: vi.fn(),
    createBudgetRule: vi.fn(),
    deleteBudgetRule: vi.fn(),
    testBudgetRules: vi.fn(),
    updateBudgetTransaction: vi.fn(),
  },
}))

const MOCK_ACCOUNT = {
  account_key: 'HDFC-savings-1234',
  bank: 'HDFC',
  kind: 'savings' as const,
  label: 'HDFC Savings',
  last4: '1234',
  is_card: false,
  credit_limit: null,
  statement_day: null,
  due_day: null,
  opening_balance: 50000,
  balance: 75000,
  outstanding: null,
  utilisation: null,
  utilisation_status: null,
  inflow: 60000,
  outflow: 35000,
  txn_count: 20,
  first_txn: '2026-01-01',
  last_txn: '2026-01-31',
  months_covered: ['2026-01'],
}

const MOCK_ACCOUNTS_RESPONSE = {
  accounts: [MOCK_ACCOUNT],
  totals: {
    deposit_balance: 75000,
    card_outstanding: 0,
    account_count: 1,
    card_count: 0,
  },
  utilisation_warnings: [],
  cards_missing_limit: [],
}

describe('Budget Domain Tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('AccountsTab', () => {
    it('renders accounts summary strip, account cards and reconciliation', async () => {
      vi.mocked(apiClient.getBudgetAccounts).mockResolvedValue(MOCK_ACCOUNTS_RESPONSE as any)

      vi.mocked(apiClient.getBudgetCoverage).mockResolvedValue({
        accounts: [
          {
            account_key: 'HDFC-savings-1234',
            bank: 'HDFC',
            missing_months: [],
            covered_months: ['2026-01'],
            coverage_pct: 100,
          },
        ],
      } as any)

      vi.mocked(apiClient.getBudgetReconciliation).mockResolvedValue({
        accounts: [
          {
            account_key: 'HDFC-savings-1234',
            rows_checked: 20,
            breaks: [],
            break_count: 0,
            opening_balance: 50000,
            closing_balance: 75000,
            status: 'reconciled',
            unexplained_total: 0,
          },
        ],
        checked: 1,
        reconciled: 1,
        status: 'reconciled',
        unverifiable_accounts: [],
      } as any)

      renderWithProviders(<AccountsTab sessionId="sess-1" />)

      // Account label and last4 both come from the rendered card
      expect(await screen.findByText('HDFC Savings')).toBeInTheDocument()
      expect(screen.getByText(/1234/)).toBeInTheDocument()
    })
  })

  describe('TransactionsTab', () => {
    it('renders transaction table rows with description and category', () => {
      const mockTransactions: BudgetTransaction[] = [
        {
          txn_id: 'tx-1',
          session_id: 'sess-1',
          date: '2026-01-15',
          description: 'ZOMATO ONLINE ORDER',
          category: 'Dining',
          amount: 450,
          type: 'debit',
          source_bank: 'HDFC',
          account_type: 'Savings Account',
          notes: 'Dinner',
        },
      ]

      renderWithProviders(
        <TransactionsTab
          transactions={mockTransactions}
          uniqueBanks={['HDFC']}
          onTransactionsUpdated={vi.fn()}
          totalAvailable={1}
        />
      )

      expect(screen.getByText('ZOMATO ONLINE ORDER')).toBeInTheDocument()
      expect(screen.getByText('Dining')).toBeInTheDocument()
    })

    it('renders empty state when no transactions passed', () => {
      renderWithProviders(
        <TransactionsTab
          transactions={[]}
          uniqueBanks={[]}
          onTransactionsUpdated={vi.fn()}
          totalAvailable={0}
        />
      )

      // Table renders with headers but 0 data rows
      expect(screen.getByText('Date')).toBeInTheDocument()
      expect(screen.getByText('Description')).toBeInTheDocument()
    })
  })

  describe('InsightsTab', () => {
    const MOCK_FORECAST = {
      as_of: '2026-01-20',
      month: '2026-01',
      days_elapsed: 20,
      days_remaining: 11,
      spent_this_month: 28000,
      received_this_month: 80000,
      typical_monthly_spend: 42000,
      typical_monthly_income: 80000,
      income_still_expected: 0,
      committed_upcoming_total: 2000,
      committed_upcoming: [],
      projected_month_end_spend: 42000,
      projected_month_end_net: 38000,
      available_balance: 52000,
      safe_to_spend_total: 50000,
      safe_to_spend_daily: 4545,
      confidence: 'high' as const,
    }

    const MOCK_RECURRING = {
      subscriptions: [
        {
          merchant: 'Netflix',
          category: 'Entertainment',
          account_key: 'HDFC-savings-1234',
          cadence: 'monthly',
          interval_days: 30,
          typical_amount: 649,
          last_amount: 649,
          last_seen: '2026-01-05',
          next_expected: '2026-02-05',
          occurrences: 6,
          total_paid: 3894,
          annualised_cost: 7788,
          regularity: 0.95,
          status: 'active' as const,
          price_changes: [],
        },
      ],
      active_count: 1,
      lapsed_count: 0,
      monthly_commitment: 649,
      annual_commitment: 7788,
      price_increases: [],
    }

    const MOCK_ENVELOPES = [
      {
        category: 'Dining',
        monthly_cap: 10000,
        spent: 8000,
        remaining: 2000,
        status: 'healthy',
      },
    ]

    const MOCK_ANOMALIES = {
      anomalies: [
        {
          type: 'category_spike' as const,
          severity: 'high' as const,
          title: 'High shopping spend',
          detail: 'Unusually high electronics purchase',
          amount: 25000,
          date: '2026-01-20',
          merchant: 'Amazon',
          category: 'Shopping',
          baseline: 5000,
          txn_ids: ['tx-spike'],
        },
      ],
      count: 1,
      high_severity_count: 1,
    }

    it('renders Safe to spend, Subscriptions, Anomalies and Budget envelopes sections', async () => {
      vi.mocked(apiClient.getBudgetForecast).mockResolvedValue(MOCK_FORECAST as any)
      vi.mocked(apiClient.getBudgetRecurring).mockResolvedValue(MOCK_RECURRING as any)
      vi.mocked(apiClient.getBudgetEnvelopes).mockResolvedValue(MOCK_ENVELOPES as any)
      vi.mocked(apiClient.getBudgetAnomalies).mockResolvedValue(MOCK_ANOMALIES as any)

      renderWithProviders(<InsightsTab sessionId="sess-1" />)

      // Section headings
      expect(await screen.findByText('Safe to spend')).toBeInTheDocument()
      expect(screen.getByText('Subscriptions')).toBeInTheDocument()
      expect(screen.getByText('Anomalies')).toBeInTheDocument()
      expect(screen.getByText('Budget envelopes')).toBeInTheDocument()
      // Content within sections (async - wait for subscriptions and envelopes to render)
      expect(await screen.findByText('Netflix')).toBeInTheDocument()
      expect(await screen.findByText('Dining')).toBeInTheDocument()
    })
  })

  describe('RulesTab', () => {
    it('renders existing rules, testing sandbox and rule form', async () => {
      vi.mocked(apiClient.getBudgetRules).mockResolvedValue([
        {
          rule_id: 'rule-1',
          pattern: 'SWIGGY',
          category: 'Dining',
          match_type: 'contains',
          match_count: 12,
        },
      ] as any)

      vi.mocked(apiClient.getBudgetMatchTypes).mockResolvedValue({
        match_types: ['contains', 'exact', 'starts_with', 'ends_with', 'regex'],
        max_pattern_length: 100,
        max_rules: 50,
      } as any)

      renderWithProviders(<RulesTab />)

      expect(await screen.findByText('SWIGGY')).toBeInTheDocument()
      expect(screen.getByText('Testing Sandbox')).toBeInTheDocument()
    })
  })
})
