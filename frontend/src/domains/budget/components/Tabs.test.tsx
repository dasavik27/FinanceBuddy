import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    testBudgetRule: vi.fn(),
    applyBudgetRules: vi.fn(),
    updateBudgetTransactions: vi.fn(),
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

const MOCK_CARD = {
  ...MOCK_ACCOUNT,
  account_key: 'HDFC-card-9999',
  kind: 'card' as const,
  label: 'HDFC Millennia',
  last4: '9999',
  is_card: true,
  credit_limit: 200000,
  outstanding: 80000,
  utilisation: 0.4,
  utilisation_status: 'high' as const,
  balance: null,
  opening_balance: null,
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

const MOCK_COVERAGE = {
  accounts: [
    {
      account_key: 'HDFC-savings-1234',
      bank: 'HDFC',
      missing_months: [],
      covered_months: ['2026-01'],
      coverage_pct: 100,
      complete: true,
      months_covered: ['2026-01'],
    },
  ],
}

const MOCK_RECONCILIATION = {
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
}

function mockAccountsHappyPath(overrides: Partial<typeof MOCK_ACCOUNTS_RESPONSE> = {}) {
  vi.mocked(apiClient.getBudgetAccounts).mockResolvedValue({
    ...MOCK_ACCOUNTS_RESPONSE,
    ...overrides,
  } as any)
  vi.mocked(apiClient.getBudgetCoverage).mockResolvedValue(MOCK_COVERAGE as any)
  vi.mocked(apiClient.getBudgetReconciliation).mockResolvedValue(MOCK_RECONCILIATION as any)
}

describe('Budget Domain Tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('AccountsTab', () => {
    it('renders accounts summary strip, account cards and reconciliation', async () => {
      mockAccountsHappyPath()
      renderWithProviders(<AccountsTab sessionId="sess-1" />)

      expect(await screen.findByText('HDFC Savings')).toBeInTheDocument()
      expect(screen.getByText(/1234/)).toBeInTheDocument()
      expect(screen.getByText(/Deposit balance/i)).toBeInTheDocument()
    })

    it('shows empty state when no accounts exist', async () => {
      vi.mocked(apiClient.getBudgetAccounts).mockResolvedValue({
        accounts: [],
        totals: { deposit_balance: 0, card_outstanding: 0, account_count: 0, card_count: 0 },
        utilisation_warnings: [],
        cards_missing_limit: [],
      } as any)
      vi.mocked(apiClient.getBudgetCoverage).mockResolvedValue({ accounts: [] } as any)
      vi.mocked(apiClient.getBudgetReconciliation).mockResolvedValue({
        accounts: [],
        checked: 0,
        reconciled: 0,
        status: 'reconciled',
        unverifiable_accounts: [],
      } as any)

      renderWithProviders(<AccountsTab sessionId="sess-1" />)
      expect(await screen.findByText(/Upload a statement to see your accounts/i)).toBeInTheDocument()
    })

    it('shows error panel and retries all queries', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getBudgetAccounts).mockRejectedValue({
        response: { status: 500, data: { detail: 'Accounts down' } },
      })
      vi.mocked(apiClient.getBudgetCoverage).mockResolvedValue({ accounts: [] } as any)
      vi.mocked(apiClient.getBudgetReconciliation).mockResolvedValue({
        accounts: [], checked: 0, reconciled: 0, status: 'reconciled', unverifiable_accounts: [],
      } as any)

      renderWithProviders(<AccountsTab sessionId="sess-1" />)
      expect(await screen.findByText('Could not load your accounts', {}, { timeout: 5000 })).toBeInTheDocument()
      expect(screen.getByText('Accounts down')).toBeInTheDocument()

      vi.mocked(apiClient.getBudgetAccounts).mockResolvedValue(MOCK_ACCOUNTS_RESPONSE as any)
      await user.click(screen.getByRole('button', { name: /Retry/i }))
      expect(await screen.findByText('HDFC Savings')).toBeInTheDocument()
    })

    it('opens edit dialog, validates, and saves account details', async () => {
      const user = userEvent.setup()
      mockAccountsHappyPath()
      vi.mocked(apiClient.updateBudgetAccount).mockResolvedValue({ status: 'ok' } as any)

      renderWithProviders(<AccountsTab sessionId="sess-1" />)
      expect(await screen.findByText('HDFC Savings')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /Edit account details/i }))
      expect(await screen.findByText(/Edit HDFC Savings/i)).toBeInTheDocument()

      const label = screen.getByLabelText(/^Label/i)
      await user.clear(label)
      await user.click(screen.getByRole('button', { name: /Save/i }))
      expect(await screen.findByText(/A label is required/i)).toBeInTheDocument()

      await user.type(label, 'HDFC Primary')
      await user.click(screen.getByRole('button', { name: /Save/i }))
      await waitFor(() => {
        expect(apiClient.updateBudgetAccount).toHaveBeenCalled()
      })
    })

    it('shows utilisation warning and missing credit-limit prompt for cards', async () => {
      mockAccountsHappyPath({
        accounts: [
          MOCK_CARD,
          { ...MOCK_CARD, account_key: 'HDFC-card-1111', label: 'HDFC Regalia', last4: '1111', credit_limit: null, utilisation: null, utilisation_status: null },
        ],
        totals: {
          deposit_balance: 0,
          card_outstanding: 80000,
          account_count: 0,
          card_count: 2,
        },
        utilisation_warnings: [{
          account_key: 'HDFC-card-9999',
          label: 'HDFC Millennia',
          utilisation: 0.4,
          status: 'high',
        }],
        cards_missing_limit: ['HDFC-card-1111'],
      })

      renderWithProviders(<AccountsTab sessionId="sess-1" />)
      expect(await screen.findByText(/Card utilisation above 30%/i)).toBeInTheDocument()
      expect(screen.getAllByText(/HDFC Millennia/).length).toBeGreaterThan(0)
      expect(screen.getByText(/Set a credit limit to track utilisation/i)).toBeInTheDocument()
    })
  })

  describe('TransactionsTab', () => {
    const debitTxn: BudgetTransaction = {
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
    }

    const creditTxn: BudgetTransaction = {
      txn_id: 'tx-2',
      session_id: 'sess-1',
      date: '2026-01-01',
      description: 'SALARY CREDIT',
      category: 'Income',
      amount: 100000,
      type: 'credit',
      source_bank: 'ICICI',
      account_type: 'Savings Account',
      notes: '',
    }

    const uncategorized: BudgetTransaction = {
      txn_id: 'tx-3',
      session_id: 'sess-1',
      date: '2026-01-20',
      description: 'UNKNOWN MERCHANT',
      category: 'Uncategorized',
      amount: 200,
      type: 'debit',
      source_bank: 'HDFC',
      account_type: 'Credit Card',
      notes: '',
    }

    it('renders transaction table rows with description and category', () => {
      renderWithProviders(
        <TransactionsTab
          transactions={[debitTxn]}
          uniqueBanks={['HDFC']}
          onTransactionsUpdated={vi.fn()}
          totalAvailable={1}
        />,
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
        />,
      )

      expect(screen.getByText('Date')).toBeInTheDocument()
      expect(screen.getByText('Description')).toBeInTheDocument()
    })

    it('filters by search, flow type, bank, account type and needs-review', async () => {
      const user = userEvent.setup()
      renderWithProviders(
        <TransactionsTab
          transactions={[debitTxn, creditTxn, uncategorized]}
          uniqueBanks={['HDFC', 'ICICI']}
          onTransactionsUpdated={vi.fn()}
          totalAvailable={3}
        />,
      )

      expect(screen.getByText('ZOMATO ONLINE ORDER')).toBeInTheDocument()
      expect(screen.getByText('SALARY CREDIT')).toBeInTheDocument()

      await user.type(screen.getByPlaceholderText(/Search description/i), 'ZOMATO')
      expect(screen.getByText('ZOMATO ONLINE ORDER')).toBeInTheDocument()
      expect(screen.queryByText('SALARY CREDIT')).not.toBeInTheDocument()
      await user.clear(screen.getByPlaceholderText(/Search description/i))

      const selects = screen.getAllByRole('combobox')
      await user.click(selects[0])
      await user.click(await screen.findByRole('option', { name: /Credits Only/i }))
      expect(screen.getByText('SALARY CREDIT')).toBeInTheDocument()
      expect(screen.queryByText('ZOMATO ONLINE ORDER')).not.toBeInTheDocument()

      await user.click(selects[0])
      await user.click(await screen.findByRole('option', { name: /All Flow Types/i }))

      await user.click(selects[1])
      await user.click(await screen.findByRole('option', { name: 'HDFC' }))
      expect(screen.queryByText('SALARY CREDIT')).not.toBeInTheDocument()

      await user.click(selects[1])
      await user.click(await screen.findByRole('option', { name: /All Banks/i }))

      await user.click(selects[2])
      await user.click(await screen.findByRole('option', { name: /Credit Card/i }))
      expect(screen.getByText('UNKNOWN MERCHANT')).toBeInTheDocument()
      expect(screen.queryByText('ZOMATO ONLINE ORDER')).not.toBeInTheDocument()

      await user.click(selects[2])
      await user.click(await screen.findByRole('option', { name: /All Account Types/i }))

      await user.click(screen.getByRole('button', { name: /Needs Review/i }))
      expect(screen.getByText('UNKNOWN MERCHANT')).toBeInTheDocument()
      expect(screen.queryByText('ZOMATO ONLINE ORDER')).not.toBeInTheDocument()
    })

    it('edits a row inline and saves via updateBudgetTransactions', async () => {
      const user = userEvent.setup()
      const onUpdated = vi.fn()
      vi.mocked(apiClient.updateBudgetTransactions).mockResolvedValue({ updated: 1 } as any)

      renderWithProviders(
        <TransactionsTab
          transactions={[debitTxn]}
          uniqueBanks={['HDFC']}
          onTransactionsUpdated={onUpdated}
          totalAvailable={1}
        />,
      )

      await user.click(screen.getByRole('button', { name: /Edit Category & Notes/i }))

      const categoryInput = await screen.findByDisplayValue('Dining')
      await user.clear(categoryInput)
      await user.type(categoryInput, 'Food')
      const notesInput = screen.getByPlaceholderText(/Add note/i)
      await user.clear(notesInput)
      await user.type(notesInput, 'Lunch')

      await user.click(screen.getByRole('button', { name: /^Save$/i }))
      await waitFor(() => {
        expect(apiClient.updateBudgetTransactions).toHaveBeenCalledWith([
          expect.objectContaining({
            txn_id: 'tx-1',
            category: 'Food',
            notes: 'Lunch',
          }),
        ])
      })
      expect(onUpdated).toHaveBeenCalled()
    })

    it('cancels an inline edit without calling the API', async () => {
      const user = userEvent.setup()
      renderWithProviders(
        <TransactionsTab
          transactions={[debitTxn]}
          uniqueBanks={['HDFC']}
          onTransactionsUpdated={vi.fn()}
          totalAvailable={1}
        />,
      )

      await user.click(screen.getByRole('button', { name: /Edit Category & Notes/i }))
      expect(await screen.findByDisplayValue('Dining')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /Cancel/i }))
      expect(screen.queryByDisplayValue('Dining')).not.toBeInTheDocument()
      expect(apiClient.updateBudgetTransactions).not.toHaveBeenCalled()
    })

    it('bulk-assigns a category to selected rows', async () => {
      const user = userEvent.setup()
      const onUpdated = vi.fn()
      vi.mocked(apiClient.updateBudgetTransactions).mockResolvedValue({ updated: 2 } as any)

      renderWithProviders(
        <TransactionsTab
          transactions={[debitTxn, uncategorized]}
          uniqueBanks={['HDFC']}
          onTransactionsUpdated={onUpdated}
          totalAvailable={2}
        />,
      )

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[0]) // select all
      expect(screen.getByText(/2 selected/i)).toBeInTheDocument()

      await user.type(screen.getByPlaceholderText(/Assign Category/i), 'Shopping')
      await user.click(screen.getByRole('button', { name: /^Apply$/i }))

      await waitFor(() => {
        expect(apiClient.updateBudgetTransactions).toHaveBeenCalled()
        expect(onUpdated).toHaveBeenCalled()
      })
    })

    it('shows truncation notice when results are paged', () => {
      renderWithProviders(
        <TransactionsTab
          transactions={[debitTxn]}
          uniqueBanks={['HDFC']}
          onTransactionsUpdated={vi.fn()}
          totalAvailable={500}
          truncated
        />,
      )

      expect(screen.getByText(/most recent of/i)).toBeInTheDocument()
      expect(screen.getByText('500')).toBeInTheDocument()
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
        used_pct: 80,
        month_progress_pct: 65,
        status: 'slightly_ahead' as const,
        daily_allowance: 181,
        projected_month_end: 12000,
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

    function mockInsightsHappyPath() {
      vi.mocked(apiClient.getBudgetForecast).mockResolvedValue(MOCK_FORECAST as any)
      vi.mocked(apiClient.getBudgetRecurring).mockResolvedValue(MOCK_RECURRING as any)
      vi.mocked(apiClient.getBudgetEnvelopes).mockResolvedValue(MOCK_ENVELOPES as any)
      vi.mocked(apiClient.getBudgetAnomalies).mockResolvedValue(MOCK_ANOMALIES as any)
    }

    it('renders Safe to spend, Subscriptions, Anomalies and Budget envelopes sections', async () => {
      mockInsightsHappyPath()
      renderWithProviders(<InsightsTab sessionId="sess-1" />)

      expect(await screen.findByText('Safe to spend')).toBeInTheDocument()
      expect(screen.getByText('Subscriptions')).toBeInTheDocument()
      expect(screen.getByText('Anomalies')).toBeInTheDocument()
      expect(screen.getByText('Budget envelopes')).toBeInTheDocument()
      expect(await screen.findByText('Netflix')).toBeInTheDocument()
      expect(await screen.findByText('Dining')).toBeInTheDocument()
      expect(await screen.findByText('High shopping spend')).toBeInTheDocument()
    })

    it('shows section errors with retry', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getBudgetForecast).mockRejectedValue({
        response: { status: 500, data: { detail: 'Forecast failed' } },
      })
      vi.mocked(apiClient.getBudgetRecurring).mockRejectedValue({ message: 'Recurring failed' })
      vi.mocked(apiClient.getBudgetEnvelopes).mockRejectedValue({ message: 'Envelope failed' })
      vi.mocked(apiClient.getBudgetAnomalies).mockRejectedValue({ message: 'Anomaly failed' })

      renderWithProviders(<InsightsTab sessionId="sess-1" />)

      expect(await screen.findByText('Forecast failed', {}, { timeout: 5000 })).toBeInTheDocument()
      const retryButtons = await screen.findAllByRole('button', { name: /Retry/i })
      expect(retryButtons.length).toBeGreaterThan(0)

      vi.mocked(apiClient.getBudgetForecast).mockResolvedValue(MOCK_FORECAST as any)
      await user.click(retryButtons[0])
      await waitFor(() => {
        expect(apiClient.getBudgetForecast.mock.calls.length).toBeGreaterThanOrEqual(2)
      })
    })

    it('adds a budget envelope', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getBudgetForecast).mockResolvedValue(MOCK_FORECAST as any)
      vi.mocked(apiClient.getBudgetRecurring).mockResolvedValue({ ...MOCK_RECURRING, subscriptions: [] } as any)
      vi.mocked(apiClient.getBudgetAnomalies).mockResolvedValue({ anomalies: [], count: 0, high_severity_count: 0 } as any)
      vi.mocked(apiClient.getBudgetEnvelopes).mockResolvedValue([] as any)
      vi.mocked(apiClient.setBudgetEnvelope).mockResolvedValue({ status: 'ok' } as any)

      renderWithProviders(<InsightsTab sessionId="sess-1" />)
      expect(await screen.findByText(/No budgets set/i)).toBeInTheDocument()

      await user.type(screen.getByPlaceholderText('Category'), 'Groceries')
      await user.type(screen.getByPlaceholderText(/Monthly cap/i), '15000')
      await user.click(screen.getByRole('button', { name: /Add budget/i }))

      await waitFor(() => {
        expect(apiClient.setBudgetEnvelope).toHaveBeenCalledWith('Groceries', 15000)
      })
    })

    it('deletes an existing budget envelope by clearing the cap', async () => {
      const user = userEvent.setup()
      mockInsightsHappyPath()
      vi.mocked(apiClient.setBudgetEnvelope).mockResolvedValue({ status: 'ok' } as any)

      renderWithProviders(<InsightsTab sessionId="sess-1" />)
      expect(await screen.findByText('Slightly ahead')).toBeInTheDocument()
      await user.click(screen.getByTestId('DeleteOutlineIcon'))
      await waitFor(() => {
        expect(apiClient.setBudgetEnvelope).toHaveBeenCalledWith('Dining', null)
      })
    })
  })

  describe('RulesTab', () => {
    beforeEach(() => {
      vi.mocked(apiClient.getBudgetMatchTypes).mockResolvedValue({
        match_types: ['contains', 'exact', 'starts_with', 'ends_with', 'regex'],
        max_pattern_length: 100,
        max_rules: 50,
      } as any)
    })

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

      renderWithProviders(<RulesTab />)

      expect(await screen.findByText('SWIGGY')).toBeInTheDocument()
      expect(screen.getByText('Testing Sandbox')).toBeInTheDocument()
    })

    it('shows empty rules table copy', async () => {
      vi.mocked(apiClient.getBudgetRules).mockResolvedValue([] as any)
      renderWithProviders(<RulesTab />)
      expect(await screen.findByText(/No automation rules created yet/i)).toBeInTheDocument()
    })

    it('creates a rule and clears the form', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getBudgetRules).mockResolvedValue([] as any)
      vi.mocked(apiClient.createBudgetRule).mockResolvedValue({
        rule_id: 'rule-2',
        pattern: 'ZOMATO',
        category: 'Dining',
        match_type: 'contains',
      } as any)

      renderWithProviders(<RulesTab />)
      await screen.findByText(/No automation rules created yet/i)

      const inputs = screen.getAllByRole('textbox')
      await user.type(inputs[0], 'ZOMATO')
      await user.type(inputs[1], 'Dining')
      await user.click(screen.getByRole('button', { name: /Add Rule/i }))

      await waitFor(() => {
        expect(apiClient.createBudgetRule).toHaveBeenCalledWith({
          pattern: 'ZOMATO',
          category: 'Dining',
          match_type: 'contains',
        })
      })
    })

    it('surfaces create errors from the server', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getBudgetRules).mockResolvedValue([] as any)
      vi.mocked(apiClient.createBudgetRule).mockRejectedValue({
        response: { data: { detail: 'Pattern already exists' }, status: 422 },
      })

      renderWithProviders(<RulesTab />)
      await screen.findByText(/No automation rules created yet/i)
      const inputs = screen.getAllByRole('textbox')
      await user.type(inputs[0], 'DUP')
      await user.type(inputs[1], 'Food')
      await user.click(screen.getByRole('button', { name: /Add Rule/i }))

      expect(await screen.findByText('Pattern already exists')).toBeInTheDocument()
    })

    it('deletes a rule and applies all rules', async () => {
      const user = userEvent.setup()
      const onRulesApplied = vi.fn()
      vi.mocked(apiClient.getBudgetRules).mockResolvedValue([
        {
          rule_id: 'rule-1',
          pattern: 'SWIGGY',
          category: 'Dining',
          match_type: 'contains',
          match_count: 12,
        },
      ] as any)
      vi.mocked(apiClient.deleteBudgetRule).mockResolvedValue({ status: 'ok' } as any)
      vi.mocked(apiClient.applyBudgetRules).mockResolvedValue({ transactions_recalculated: 42 } as any)

      renderWithProviders(<RulesTab onRulesApplied={onRulesApplied} />)
      expect(await screen.findByText('SWIGGY')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: '' }))
      const deleteBtn = screen.getAllByRole('button').find(b =>
        b.querySelector('[data-testid="DeleteIcon"]') || b.className.includes('MuiIconButton'),
      )
      // Prefer the error-colored icon button in the rules table
      const iconButtons = within(screen.getByText('SWIGGY').closest('tr')!).getAllByRole('button')
      await user.click(iconButtons[0])
      await waitFor(() => {
        expect(apiClient.deleteBudgetRule).toHaveBeenCalledWith('rule-1')
      })

      await user.click(screen.getByRole('button', { name: /Re-apply Rules/i }))
      await waitFor(() => {
        expect(apiClient.applyBudgetRules).toHaveBeenCalled()
        expect(onRulesApplied).toHaveBeenCalled()
      })
      expect(await screen.findByText(/Successfully re-categorized 42 transactions/i)).toBeInTheDocument()
    })

    it('tests a draft rule in the sandbox', async () => {
      const user = userEvent.setup()
      vi.mocked(apiClient.getBudgetRules).mockResolvedValue([] as any)
      vi.mocked(apiClient.testBudgetRule).mockResolvedValue({
        matches: true,
        valid: true,
      } as any)

      renderWithProviders(<RulesTab />)
      await screen.findByText('Testing Sandbox')

      const inputs = screen.getAllByRole('textbox')
      // pattern, category, then sandbox description
      await user.type(inputs[0], 'SWIGGY')
      await user.type(inputs[1], 'FoodDelivery')
      await user.type(inputs[inputs.length - 1], 'SWIGGY BANGALORE ORDER')

      await waitFor(() => {
        expect(apiClient.testBudgetRule).toHaveBeenCalled()
      }, { timeout: 3000 })
      expect(await screen.findByText('Rule Matched!')).toBeInTheDocument()
      expect(screen.getByText(/FoodDelivery/i)).toBeInTheDocument()
    })
  })
})
