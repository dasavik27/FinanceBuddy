import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import BudgetDashboard from './BudgetDashboard'

const mockOverview = {
  total_income: 120000,
  total_expense: 80000,
  net_flow: 40000,
  net_savings: 40000,
  savings_rate: 33.3,
  banks: ['HDFC', 'ICICI'],
  account_types: ['Savings Account'],
  categories: ['Food', 'Rent'],
  bank_breakdown: [{
    bank: 'HDFC',
    income: 120000,
    expense: 80000,
    net: 40000,
    transactions: 25,
    account_type: 'Savings Account',
  }],
  top_merchants: [{ merchant: 'Swiggy', amount: 5000, count: 10 }],
  top_inflows: [{ merchant: 'Salary', amount: 100000, count: 1 }],
  cumulative_trend: [{ month: '2026-01', cumulative: 40000 }],
  monthly_trend: [{ month: '2026-01', income: 120000, expense: 80000 }],
  day_of_week_spend: [{ day: 'Mon', spend: 5000, count: 3, avg_spend: 1666 }],
  health_metrics: {
    needs_pct: 45,
    wants_pct: 25,
    savings_pct: 30,
    health_score: 85,
  },
}

const mockCategories = {
  categories: [
    { category: 'Food', amount: 15000, count: 20, nature: 'wants' },
    { category: 'Rent', amount: 30000, count: 1, nature: 'needs' },
  ],
  all_categories: ['Food', 'Rent'],
  is_drilldown: false,
}

const mockSessions = [
  {
    session_id: 'sess-1',
    filename: 'hdfc_jan.csv',
    bank: 'HDFC',
    account_type: 'Savings Account',
    rows: 25,
    total_income: 50000,
    total_expense: 30000,
    created_at: '2026-01-15T10:00:00Z',
  },
]

vi.mock('../hooks/useBudget', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useBudget')>()
  const idleQuery = {
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
  return {
    ...actual,
    useBudgetSessions: vi.fn(() => ({
      data: mockSessions,
      isSuccess: true,
      isPending: false,
      error: null,
    })),
    useBudgetOverview: vi.fn(() => ({
      data: mockOverview,
      isPending: false,
      error: null,
    })),
    useBudgetCategories: vi.fn(() => ({
      data: mockCategories,
      isPending: false,
      error: null,
    })),
    useBudgetTransactions: vi.fn(() => ({
      data: { transactions: [], total: 0, has_more: false },
      isPending: false,
      error: null,
    })),
    useBudgetTransfers: vi.fn(() => ({
      data: {
        pairs: [],
        count: 0,
        excluded_from_income: 0,
        excluded_from_expense: 0,
        card_payment_total: 0,
      },
      ...idleQuery,
    })),
    useBudgetSankey: vi.fn(() => ({
      data: { nodes: [], links: [] },
      ...idleQuery,
    })),
    useUploadStatement: vi.fn(() => ({
      mutateAsync: vi.fn().mockResolvedValue({ parsed: 10, skipped: 0 }),
      isPending: false,
    })),
    useDeleteBudgetSession: vi.fn(() => ({
      mutateAsync: vi.fn().mockResolvedValue(undefined),
      isPending: false,
    })),
    useInvalidateBudgetAnalytics: vi.fn(() => vi.fn()),
    useResetSessionOnMissing: vi.fn(),
  }
})

describe('BudgetDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders master budget header and overview tab', async () => {
    renderWithProviders(<BudgetDashboard />)

    expect(await screen.findByText('Master Budget & Accounts')).toBeInTheDocument()
    expect(screen.getByText('All Accounts Combined')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Overview/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Transactions/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Accounts/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Insights/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Rules/i })).toBeInTheDocument()
  })

  it('switches to transactions tab', async () => {
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')

    await userEvent.click(screen.getByRole('tab', { name: /Transactions/i }))

    await waitFor(() => {
      expect(screen.getByText('Date')).toBeInTheDocument()
    })
  })

  it('opens upload statement modal', async () => {
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')

    await userEvent.click(screen.getByRole('button', { name: /Upload Statement/i }))

    expect(await screen.findByText('Upload Bank / Card Statement')).toBeInTheDocument()
  })

  it('opens sessions modal from session chip', async () => {
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('All Accounts Combined')

    await userEvent.click(screen.getByText('All Accounts Combined'))

    expect(await screen.findByText('Statement Sessions & Accounts History')).toBeInTheDocument()
  })

  it('shows empty upload prompt when no sessions exist', async () => {
    const { useBudgetSessions } = await import('../hooks/useBudget')
    vi.mocked(useBudgetSessions).mockReturnValue({
      data: [],
      isSuccess: true,
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)

    expect(await screen.findByText('No statements yet')).toBeInTheDocument()
  })
})
