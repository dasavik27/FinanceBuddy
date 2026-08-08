import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
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
  account_types: ['Savings Account', 'Credit Card'],
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
  cumulative_trend: [{ date: '2026-01', cumulative: 40000 }],
  monthly_trend: [{ month: '2026-01', income: 120000, expense: 80000 }],
  day_of_week_spend: [{ day: 'Mon', spend: 5000, count: 3, avg_spend: 1666 }],
  health_metrics: {
    needs_pct: 45,
    wants_pct: 25,
    savings_pct: 30,
    health_score: 85,
    avg_monthly_burn: 42000,
    avg_daily_spend: 1400,
    largest_debit: { amount: 30000, description: 'Rent' },
    largest_credit: { amount: 100000, description: 'Salary' },
  },
  budget_50_30_20: {
    health_score: 82,
    base_amount: 100000,
    base_type: 'income' as const,
    needs: {
      amount: 45000,
      percentage: 45,
      target_pct: 50,
      target_amount: 50000,
      status: 'optimal' as const,
      categories: [{ name: 'Rent', amount: 30000 }],
    },
    wants: {
      amount: 25000,
      percentage: 25,
      target_pct: 30,
      target_amount: 30000,
      status: 'optimal' as const,
      categories: [{ name: 'Food', amount: 15000 }],
    },
    investments: {
      amount: 30000,
      percentage: 30,
      target_pct: 20,
      target_amount: 20000,
      status: 'optimal' as const,
      categories: [{ name: 'SIP', amount: 30000 }],
    },
    transfers_amount: 5000,
    recommendations: ['Keep discretionary spend under control'],
  },
  biggest_change: {
    category: 'Shopping',
    increase_amount: 12000,
  },
  recurring_charges: [
    { description: 'Netflix', amount: 649, frequency: 6 },
  ],
}

const mockCategories = {
  categories: [
    { category: 'Food', amount: 15000, count: 20, nature: 'wants', top_merchants: [{ name: 'Swiggy' }] },
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

const mutateUpload = vi.fn().mockResolvedValue({ parsed: 10, skipped: 0 })
const mutateDelete = vi.fn().mockResolvedValue(undefined)
const invalidateAnalytics = vi.fn()

const idleQuery = {
  isPending: false,
  isError: false,
  isSuccess: true,
  error: null,
  refetch: vi.fn(),
}

function defaultSessionsReturn() {
  return {
    data: mockSessions,
    isSuccess: true,
    isPending: false,
    error: null,
  }
}

function defaultOverviewReturn() {
  return {
    data: mockOverview,
    isPending: false,
    error: null,
  }
}

function defaultCategoriesReturn() {
  return {
    data: mockCategories,
    isPending: false,
    error: null,
  }
}

function defaultTransactionsReturn() {
  return {
    data: { transactions: [], total: 0, has_more: false },
    isPending: false,
    error: null,
  }
}

vi.mock('./AccountsTab', () => {
  const { createElement } = require('react')
  return {
    default: () => createElement('div', { 'data-testid': 'accounts-tab-stub' }, 'Accounts Tab'),
  }
})
vi.mock('./InsightsTab', () => {
  const { createElement } = require('react')
  return {
    default: () => createElement('div', { 'data-testid': 'insights-tab-stub' }, 'Insights Tab'),
  }
})
vi.mock('./RulesTab', () => {
  const { createElement } = require('react')
  return {
    default: ({ onRulesApplied }: { onRulesApplied?: () => void }) =>
      createElement(
        'div',
        { 'data-testid': 'rules-tab-stub' },
        createElement('button', { type: 'button', onClick: () => onRulesApplied?.() }, 'Apply rules stub'),
      ),
  }
})

// Stub chart primitives so jsdom does not hang, but still invoke formatter
// callbacks so they count toward function coverage.
vi.mock('recharts', () => {
  const { createElement } = require('react')
  const Passthrough = ({ children }: { children?: unknown }) => createElement('div', null, children)
  const InvokeFormatters = (props: Record<string, unknown>) => {
    const tick = props.tickFormatter as ((v: number) => unknown) | undefined
    const fmt = props.formatter as ((v: number, name?: string) => unknown) | undefined
    // Cover both <1k and >=1k branches inside tick/tooltip formatters.
    if (typeof tick === 'function') {
      tick(500)
      tick(5000)
    }
    if (typeof fmt === 'function') {
      fmt(500, 'Sample')
      fmt(5000, 'Sample')
    }
    return createElement('div', { 'data-testid': 'chart-stub' }, props.children as never)
  }
  return {
    ResponsiveContainer: Passthrough,
    AreaChart: Passthrough,
    BarChart: Passthrough,
    PieChart: Passthrough,
    Pie: InvokeFormatters,
    Cell: () => createElement('div'),
    Area: InvokeFormatters,
    Bar: InvokeFormatters,
    XAxis: InvokeFormatters,
    YAxis: InvokeFormatters,
    CartesianGrid: () => createElement('div'),
    Tooltip: InvokeFormatters,
    Legend: () => createElement('div'),
    Sankey: () => createElement('div', { 'data-testid': 'chart-stub' }),
  }
})

vi.mock('../hooks/useBudget', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useBudget')>()
  return {
    ...actual,
    useBudgetSessions: vi.fn(() => defaultSessionsReturn()),
    useBudgetOverview: vi.fn(() => defaultOverviewReturn()),
    useBudgetCategories: vi.fn(() => defaultCategoriesReturn()),
    useBudgetTransactions: vi.fn(() => defaultTransactionsReturn()),
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
      mutateAsync: mutateUpload,
      isPending: false,
    })),
    useDeleteBudgetSession: vi.fn(() => ({
      mutateAsync: mutateDelete,
      isPending: false,
    })),
    useInvalidateBudgetAnalytics: vi.fn(() => invalidateAnalytics),
    useResetSessionOnMissing: vi.fn(),
  }
})

async function setupHooks() {
  const hooks = await import('../hooks/useBudget')
  vi.mocked(hooks.useBudgetSessions).mockReturnValue(defaultSessionsReturn() as any)
  vi.mocked(hooks.useBudgetOverview).mockReturnValue(defaultOverviewReturn() as any)
  vi.mocked(hooks.useBudgetCategories).mockReturnValue(defaultCategoriesReturn() as any)
  vi.mocked(hooks.useBudgetTransactions).mockReturnValue(defaultTransactionsReturn() as any)
  vi.mocked(hooks.useUploadStatement).mockReturnValue({
    mutateAsync: mutateUpload,
    isPending: false,
  } as any)
  vi.mocked(hooks.useDeleteBudgetSession).mockReturnValue({
    mutateAsync: mutateDelete,
    isPending: false,
  } as any)
  vi.mocked(hooks.useInvalidateBudgetAnalytics).mockReturnValue(invalidateAnalytics as any)
  return hooks
}

/** The toolbar "Filters" control (avoids matching "Reset all filters" title). */
function getFiltersToolbarButton() {
  const tune = screen.getByTestId('TuneIcon')
  const btn = tune.closest('button')
  if (!btn) throw new Error('Filters toolbar button not found')
  return btn
}

describe('BudgetDashboard', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    mutateUpload.mockResolvedValue({ parsed: 10, skipped: 0 })
    mutateDelete.mockResolvedValue(undefined)
    await setupHooks()
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
    expect(screen.getByText('Total Inflow')).toBeInTheDocument()
    expect(screen.getByText('Total Outflow')).toBeInTheDocument()
    expect(screen.getByText('Net Cash Flow')).toBeInTheDocument()
    expect(screen.getByText('Savings Rate')).toBeInTheDocument()
  })

  it('shows loading spinner while overview is pending without data', async () => {
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: undefined,
      isPending: true,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect(document.querySelector('.MuiCircularProgress-root')).toBeTruthy()
  })

  it('switches across overview, transactions, accounts, insights and rules tabs', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')

    await user.click(screen.getByRole('tab', { name: /Transactions/i }))
    await waitFor(() => {
      expect(screen.getByText('Date')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: /Accounts/i }))
    expect(await screen.findByTestId('accounts-tab-stub')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Insights/i }))
    expect(await screen.findByTestId('insights-tab-stub')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Rules/i }))
    expect(await screen.findByTestId('rules-tab-stub')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Apply rules stub/i }))
    expect(invalidateAnalytics).toHaveBeenCalled()

    await user.click(screen.getByRole('tab', { name: /Overview/i }))
    expect(await screen.findByText('Total Inflow')).toBeInTheDocument()
  })

  it('opens upload statement modal', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')

    await user.click(screen.getByRole('button', { name: /Upload Statement/i }))
    expect(await screen.findByText('Upload Bank / Card Statement')).toBeInTheDocument()
  })

  it('uploads a statement and shows parse notice when rows are skipped', async () => {
    const user = userEvent.setup()
    mutateUpload.mockResolvedValue({
      parsed: 8,
      skipped: 2,
      truncated: true,
      reasons: { bad_date: 2 },
    })

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')
    await user.click(screen.getByRole('button', { name: /^Upload Statement$/i }))
    expect(await screen.findByText('Upload Bank / Card Statement')).toBeInTheDocument()

    const file = new File(['date,desc,amount\n'], 'stmt.csv', { type: 'text/csv' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, file)
    await user.click(screen.getByRole('button', { name: /Import Statement/i }))

    expect(mutateUpload).toHaveBeenCalled()
    expect(await screen.findByText(/8 transactions imported/i)).toBeInTheDocument()
    expect(screen.getByText(/2 rows skipped/i)).toBeInTheDocument()

    const notice = screen.getByText(/8 transactions imported/i).closest('.MuiCard-root')!
    await user.click(within(notice).getByTestId('CloseIcon'))
    await waitFor(() => {
      expect(screen.queryByText(/8 transactions imported/i)).not.toBeInTheDocument()
    })
  })

  it('surfaces upload failures as action errors', async () => {
    const user = userEvent.setup()
    mutateUpload.mockRejectedValue({
      response: { data: { detail: 'File too large' }, status: 422 },
    })

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')
    await user.click(screen.getByRole('button', { name: /^Upload Statement$/i }))

    const file = new File(['x'], 'big.csv', { type: 'text/csv' })
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file)
    await user.click(screen.getByRole('button', { name: /Import Statement/i }))

    expect((await screen.findAllByText('File too large')).length).toBeGreaterThan(0)
  })

  it('opens sessions modal, switches session, and deletes a session', async () => {
    const user = userEvent.setup()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('All Accounts Combined')

    await user.click(screen.getByText('All Accounts Combined'))
    expect(await screen.findByText('Statement Sessions & Accounts History')).toBeInTheDocument()

    await user.click(screen.getByText('hdfc_jan.csv'))
    await waitFor(() => {
      expect(screen.getByText(/HDFC \(Savings Account\)/i)).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /Accounts & Statements/i }))
    const sessionsDialog = await screen.findByRole('dialog')
    expect(within(sessionsDialog).getByText('Statement Sessions & Accounts History')).toBeInTheDocument()

    await user.click(within(sessionsDialog).getByRole('button', { name: /Delete this statement session/i }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(mutateDelete).toHaveBeenCalledWith('sess-1')

    confirmSpy.mockRestore()
  })

  it('shows delete failure as action error', async () => {
    const user = userEvent.setup()
    mutateDelete.mockRejectedValue({ response: { data: { detail: 'Delete blocked' } } })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('All Accounts Combined')
    await user.click(screen.getByText('All Accounts Combined'))
    const sessionsDialog = await screen.findByRole('dialog')
    await user.click(within(sessionsDialog).getByRole('button', { name: /Delete this statement session/i }))

    expect(await screen.findByText('Delete blocked')).toBeInTheDocument()
  })

  it('shows empty upload prompt when no sessions exist', async () => {
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetSessions).mockReturnValue({
      data: [],
      isSuccess: true,
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect(await screen.findByText('No statements yet')).toBeInTheDocument()
  })

  it('shows analytics error state and retries via invalidate', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: null,
      isPending: false,
      error: {
        response: { status: 500, data: { detail: 'Upstream exploded' } },
        message: 'Request failed',
      },
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect(await screen.findByText('Could not load your budget data')).toBeInTheDocument()
    expect(screen.getByText('Upstream exploded')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Retry/i }))
    expect(invalidateAnalytics).toHaveBeenCalled()
  })

  it('treats overview 404 as non-fatal and shows empty-data CTA when totals are zero', async () => {
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: {
        ...mockOverview,
        total_income: 0,
        total_expense: 0,
        banks: [],
        bank_breakdown: [],
      },
      isPending: false,
      error: { response: { status: 404 } },
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect(await screen.findByText('No accounts uploaded yet')).toBeInTheDocument()
  })

  it('shows filter-empty state and resets filters', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: {
        ...mockOverview,
        total_income: 0,
        total_expense: 0,
        banks: ['HDFC'],
        bank_breakdown: [],
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Master Budget & Accounts')

    await user.click(screen.getByRole('button', { name: /30D/i }))
    expect(await screen.findByText('No transactions match the selected filters')).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: /Reset All Filters/i })[0])
    await waitFor(() => {
      expect(screen.queryByText('No transactions match the selected filters')).not.toBeInTheDocument()
    })
  })

  it('applies bank, date, search and advanced filters with reset chips', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Total Inflow')

    const search = screen.getByPlaceholderText(/Search transactions, payees, tags/i)
    await user.type(search, 'swiggy')
    expect(search).toHaveValue('swiggy')

    await user.click(screen.getByRole('button', { name: /90D/i }))
    expect(screen.getByText(/Active filters:/i)).toBeInTheDocument()
    expect(screen.getByText(/Time: 90D/i)).toBeInTheDocument()

    await user.click(getFiltersToolbarButton())
    expect(await screen.findByText('Advanced Filters')).toBeInTheDocument()

    await user.click(screen.getByText('Debits (Out)'))
    await user.click(screen.getByText('Micro (< ₹500)'))
    await user.click(screen.getByText('UPI / QR'))
    await user.click(screen.getByText('Credit Card'))

    const popoverPaper = screen.getByText('Advanced Filters').closest('.MuiPaper-root') as HTMLElement
    const categorySelect = within(popoverPaper).getAllByRole('combobox')[0]
    await user.click(categorySelect)
    await user.click(await screen.findByRole('option', { name: /^Food/i }))

    await user.click(within(popoverPaper).getByRole('button', { name: /^Apply$/i }))

    expect(screen.getByText(/Flow: Debits Only/i)).toBeInTheDocument()
    expect(screen.getByText(/Amount:/i)).toBeInTheDocument()
    expect(screen.getByText(/Mode: UPI/i)).toBeInTheDocument()
    expect(screen.getByText(/Category: Food/i)).toBeInTheDocument()
    expect(screen.getByText(/Account: Credit Card/i)).toBeInTheDocument()

    await user.click(screen.getByText(/Clear all/i))
    await waitFor(() => {
      expect(screen.queryByText(/Active filters:/i)).not.toBeInTheDocument()
    })
  }, 60000)

  it('filters by bank from the bank breakdown card', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Accounts & Bank Breakdown')

    await user.click(screen.getByText('Filter'))
    expect(await screen.findByText('● Active')).toBeInTheDocument()
    expect(screen.getByText(/Bank: HDFC/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Show All Banks/i }))
    await waitFor(() => {
      expect(screen.queryByText(/Bank: HDFC/i)).not.toBeInTheDocument()
    })
  })

  it('toggles merchant inflows/outflows and category analytics controls', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Top Payees (Expenses)')
    expect(screen.getByText('Swiggy')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Inflows$/i }))
    expect(await screen.findByText('Top Inflows (Sources)')).toBeInTheDocument()
    expect(screen.getByText('Salary')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Outflows$/i }))
    expect(await screen.findByText('Top Payees (Expenses)')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Credits$/i }))
    expect(screen.getAllByText(/Total Inflow/i).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /^Debits$/i }))
    await user.click(screen.getByRole('button', { name: /Needs/i }))
    expect(screen.getByText('Rent')).toBeInTheDocument()
    expect(screen.queryByText('Food')).not.toBeInTheDocument()

    const allNatureChips = screen.getAllByRole('button', { name: /^All$/i })
    await user.click(allNatureChips[allNatureChips.length - 1])
    const catSearch = screen.getByPlaceholderText('Search categories...')
    await user.type(catSearch, 'food')
    expect(screen.getByText('Food')).toBeInTheDocument()
    expect(screen.queryByText('Rent')).not.toBeInTheDocument()

    await user.clear(catSearch)
    const sortSelects = screen.getAllByRole('combobox')
    const sortSelect = sortSelects[sortSelects.length - 1]
    await user.click(sortSelect)
    await user.click(await screen.findByRole('option', { name: /Txn Count/i }))
    await user.click(sortSelect)
    await user.click(await screen.findByRole('option', { name: /Name \(A-Z\)/i }))
  }, 60000)

  it('drills into a category and returns via All Categories', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Category Spend Analytics')

    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [{ category: 'Food', amount: 15000, count: 20, nature: 'wants' }],
        all_categories: ['Food', 'Rent'],
        is_drilldown: true,
        category_stats: {
          amount: 15000,
          percentage_of_total: 18.75,
          count: 20,
          avg_ticket: 750,
          merchants: [{ merchant: 'Swiggy', amount: 5000, percentage: 33 }],
        },
      },
      isPending: false,
      error: null,
    } as any)

    await user.click(screen.getByText('Food'))
    expect(await screen.findByText(/Food Drilldown/i)).toBeInTheDocument()
    expect(screen.getByText('Total Spent')).toBeInTheDocument()
    expect(screen.getByText(/Payees \/ Merchants for Food/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /All Categories/i }))
    await waitFor(() => {
      expect(screen.queryByText(/Food Drilldown/i)).not.toBeInTheDocument()
    })
  })

  it('switches day-of-week metrics and renders health / money-flow sections', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)

    expect(await screen.findByText('50 / 30 / 20 Budget Health Evaluation')).toBeInTheDocument()
    expect(screen.getByText('Avg Monthly Burn')).toBeInTheDocument()
    expect(screen.getByText('Money flow')).toBeInTheDocument()
    expect(screen.getByText(/Spend Acceleration Alert/i)).toBeInTheDocument()
    expect(screen.getByText('Shopping')).toBeInTheDocument()
    expect(screen.getByText('Netflix')).toBeInTheDocument()
    expect(screen.getByText('Cumulative Cash Flow Trajectory')).toBeInTheDocument()
    expect(screen.getByText('Monthly Inflows vs Outflows')).toBeInTheDocument()
    expect(screen.getByText('Spending by Day of Week')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Txn Count/i }))
    expect(screen.getByText(/Number of transactions executed per weekday/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Avg ₹\/Txn/i }))
    expect(screen.getByText(/Average spend ticket per day/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Total ₹/i }))
    expect(screen.getByText(/Total debit volume per day of week/i)).toBeInTheDocument()
  })

  it('applies category filter when health card category chip is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    const healthHeading = await screen.findByText('50 / 30 / 20 Budget Health Evaluation')
    const healthCard = healthHeading.closest('.MuiCard-root') as HTMLElement

    await user.click(within(healthCard).getByText(/Rent:/i))
    expect(await screen.findByText(/Category: Rent/i)).toBeInTheDocument()
  })

  it('renders deficit cash-flow styling and empty chart fallbacks', async () => {
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: {
        ...mockOverview,
        net_savings: -5000,
        savings_rate: -4.2,
        cumulative_trend: [],
        monthly_trend: [],
        day_of_week_spend: [],
        top_merchants: [],
        top_inflows: [],
        biggest_change: undefined,
        recurring_charges: [],
        budget_50_30_20: undefined,
      },
      isPending: false,
      error: null,
    } as any)
    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: { categories: [], all_categories: [], is_drilldown: false },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect(await screen.findByText(/Deficit spend/i)).toBeInTheDocument()
    expect(screen.getByText('No trajectory data available')).toBeInTheDocument()
    expect(screen.getByText('No monthly breakdown available')).toBeInTheDocument()
    expect(screen.getByText('No day-of-week data')).toBeInTheDocument()
    expect(screen.getByText('No records matching filter')).toBeInTheDocument()
    expect(screen.getByText('No categories matching selection')).toBeInTheDocument()
  })

  it('merges long category tails into an Other donut slice', async () => {
    const hooks = await setupHooks()
    const many = Array.from({ length: 12 }, (_, i) => ({
      category: `Cat${i}`,
      amount: 12000 - i * 500,
      count: 10 - (i % 5),
      nature: i % 2 === 0 ? 'needs' : 'wants',
    }))
    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: many,
        all_categories: many.map(c => c.category),
        is_drilldown: false,
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    // Donut merges the tail into Other; ranked list still shows every category.
    expect(await screen.findByText('Cat0')).toBeInTheDocument()
    expect(screen.getByText('Cat11')).toBeInTheDocument()
    expect(screen.getByText(/12 Categories/i)).toBeInTheDocument()
  })

  it('opens empty-state upload CTA from no-statements card', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetSessions).mockReturnValue({
      data: [],
      isSuccess: true,
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('No statements yet')
    const uploadBtns = screen.getAllByRole('button', { name: /Upload Statement/i })
    await user.click(uploadBtns[uploadBtns.length - 1])
    expect(await screen.findByText('Upload Bank / Card Statement')).toBeInTheDocument()
  })

  it('clears search, changes bank select, and dismisses each active filter chip', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Total Inflow')

    const search = screen.getByPlaceholderText(/Search transactions, payees, tags/i)
    await user.type(search, 'swiggy')
    expect(search).toHaveValue('swiggy')
    await user.click(screen.getByTestId('ClearIcon'))
    expect(search).toHaveValue('')

    const bankSelect = screen.getAllByRole('combobox')[0]
    await user.click(bankSelect)
    await user.click(await screen.findByRole('option', { name: /HDFC/i }))
    expect(await screen.findByText(/Bank: HDFC/i)).toBeInTheDocument()

    await user.click(getFiltersToolbarButton())
    const popover = await screen.findByText('Advanced Filters')
    const popoverPaper = popover.closest('.MuiPaper-root') as HTMLElement
    await user.click(within(popoverPaper).getByText('Debits (Out)'))
    await user.click(within(popoverPaper).getByText('Micro (< ₹500)'))
    await user.click(within(popoverPaper).getByText('UPI / QR'))
    await user.click(within(popoverPaper).getByText('Credit Card'))
    const categorySelect = within(popoverPaper).getAllByRole('combobox')[0]
    await user.click(categorySelect)
    await user.click(await screen.findByRole('option', { name: /^Food/i }))
    // Close via header IconButton (covers onClick close)
    await user.click(within(popoverPaper).getAllByRole('button')[0])
    await waitFor(() => {
      expect(screen.queryByText('Advanced Filters')).not.toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /90D/i }))

    // Dismiss each chip via its delete icon (covers every onDelete handler)
    const chipLabels = [
      /Bank: HDFC/i,
      /Flow: Debits Only/i,
      /Time: 90D/i,
      /Amount:/i,
      /Mode: UPI/i,
      /Category: Food/i,
      /Account: Credit Card/i,
    ]
    for (const label of chipLabels) {
      const chip = screen.getByText(label).closest('.MuiChip-root') as HTMLElement
      const deleteIcon = within(chip).getByTestId('CancelIcon')
      await user.click(deleteIcon)
    }
    await waitFor(() => {
      expect(screen.queryByText(/Active filters:/i)).not.toBeInTheDocument()
    })
  }, 60000)

  it('closes advanced filters via Escape and resets account-type to All', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Total Inflow')

    await user.click(getFiltersToolbarButton())
    let popoverPaper = (await screen.findByText('Advanced Filters')).closest('.MuiPaper-root') as HTMLElement
    await user.click(within(popoverPaper).getByText('Credit Card'))
    expect(await screen.findByText(/Account: Credit Card/i)).toBeInTheDocument()

    // Reset account type via the All Types chip, then Escape-close (covers Popover onClose)
    await user.click(within(popoverPaper).getByRole('button', { name: /All Types/i }))
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByText('Advanced Filters')).not.toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.queryByText(/Account: Credit Card/i)).not.toBeInTheDocument()
    })
  })

  it('opens upload from zero-totals empty state when sessions exist', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: {
        ...mockOverview,
        total_income: 0,
        total_expense: 0,
        banks: [],
        bank_breakdown: [],
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect(await screen.findByText('No accounts uploaded yet')).toBeInTheDocument()
    const uploadBtns = screen.getAllByRole('button', { name: /Upload Statement/i })
    await user.click(uploadBtns[uploadBtns.length - 1])
    expect(await screen.findByText('Upload Bank / Card Statement')).toBeInTheDocument()
  })

  it('drills via category select, shows no-payees empty, and formats small amounts', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [
          { category: 'Tips', amount: 250, count: 2, nature: 'wants' },
          { category: 'Coffee', amount: 400, count: 3, nature: 'wants' },
        ],
        all_categories: ['Tips', 'Coffee', 'Food'],
        is_drilldown: false,
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Category Spend Analytics')
    // Center metric uses the < ₹1k branch when totals are small
    expect(screen.getByText('₹650')).toBeInTheDocument()

    // Category picker Select onChange (header dropdown)
    const categoryPicker = screen.getAllByRole('combobox').find(el =>
      /All Categories|Tips|Coffee/i.test(el.textContent || '') || el.getAttribute('aria-labelledby'),
    ) || screen.getAllByRole('combobox')[1]
    await user.click(categoryPicker as HTMLElement)

    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [],
        all_categories: ['Tips', 'Coffee', 'Food'],
        is_drilldown: true,
        category_stats: {
          amount: 250,
          percentage_of_total: 5,
          count: 2,
          avg_ticket: 125,
          merchants: [],
        },
      },
      isPending: false,
      error: null,
    } as any)

    await user.click(await screen.findByRole('option', { name: /Tips/i }))
    expect(await screen.findByText(/Tips Drilldown/i)).toBeInTheDocument()
    expect(screen.getByText('No payees found in this category')).toBeInTheDocument()
    // Drilldown center amount uses the raw <1000 branch
    expect(screen.getByText('₹250')).toBeInTheDocument()
  })

  it('formats large drilldown amounts in lakhs and toggles selected category off', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [
          { category: 'Investments', amount: 250000, count: 4, nature: 'investments' },
        ],
        all_categories: ['Investments'],
        is_drilldown: false,
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    expect((await screen.findAllByText('₹2.5L')).length).toBeGreaterThan(0)

    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [{ category: 'Investments', amount: 250000, count: 4, nature: 'investments' }],
        all_categories: ['Investments'],
        is_drilldown: true,
        category_stats: {
          amount: 250000,
          percentage_of_total: 40,
          count: 4,
          avg_ticket: 62500,
          merchants: [{ merchant: 'Zerodha', amount: 250000, percentage: 100 }],
        },
      },
      isPending: false,
      error: null,
    } as any)

    await user.click(screen.getByText('Investments'))
    expect(await screen.findByText(/Investments Drilldown/i)).toBeInTheDocument()
    expect(screen.getAllByText('₹2.5L').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /All Categories/i }))
    await waitFor(() => {
      expect(screen.queryByText(/Investments Drilldown/i)).not.toBeInTheDocument()
    })
  })

  it('exercises day-of-week formatter branches for count and currency ticks', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Spending by Day of Week')

    await user.click(screen.getByRole('button', { name: /Txn Count/i }))
    expect(screen.getByText(/Number of transactions executed per weekday/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Avg ₹\/Txn/i }))
    expect(screen.getByText(/Average spend ticket per day/i)).toBeInTheDocument()
    // Recharts mock invokes tickFormatter/formatter for both <1k and >=1k values
    await user.click(screen.getByRole('button', { name: /Total ₹/i }))
    expect(screen.getByText(/Total debit volume per day of week/i)).toBeInTheDocument()
  })

  it('covers credit-flow chip, singular skip notice, card bank row, and category toggle-off', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    mutateUpload.mockResolvedValue({
      parsed: 1,
      skipped: 1,
      reasons: { bad_row: 1 },
    })
    vi.mocked(hooks.useBudgetOverview).mockReturnValue({
      data: {
        ...mockOverview,
        bank_breakdown: [
          {
            bank: 'ICICI',
            income: 0,
            expense: 20000,
            net: -20000,
            transactions: 8,
            account_type: 'Credit Card',
          },
        ],
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    await screen.findByText('Accounts & Bank Breakdown')
    expect(screen.getAllByText(/Credit Card/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Net:/i)).toBeInTheDocument()

    await user.click(getFiltersToolbarButton())
    const popoverPaper = (await screen.findByText('Advanced Filters')).closest('.MuiPaper-root') as HTMLElement
    await user.click(within(popoverPaper).getByText('Credits (In)'))
    await user.click(within(popoverPaper).getByRole('button', { name: /^Apply$/i }))
    expect(await screen.findByText(/Flow: Credits Only/i)).toBeInTheDocument()
    const flowChip = screen.getByText(/Flow: Credits Only/i).closest('.MuiChip-root') as HTMLElement
    await user.click(within(flowChip).getByTestId('CancelIcon'))

    // Singular "1 row skipped" upload notice branch
    await user.click(screen.getAllByRole('button', { name: /Upload Statement/i })[0])
    const file = new File(['x'], 'one.csv', { type: 'text/csv' })
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file)
    await user.click(screen.getByRole('button', { name: /Import Statement/i }))
    expect(await screen.findByText(/1 row skipped/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('Upload Bank / Card Statement')).not.toBeInTheDocument()
    })
  })

  it('formats mid-size drilldown amounts and clears categoryFilter via All Categories', async () => {
    const user = userEvent.setup()
    const hooks = await setupHooks()
    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [
          { category: 'Food', amount: 5500, count: 3, nature: 'wants' },
          { category: 'SIP', amount: 8000, count: 1, nature: 'investments' },
        ],
        all_categories: ['Food', 'SIP'],
        is_drilldown: false,
      },
      isPending: false,
      error: null,
    } as any)

    renderWithProviders(<BudgetDashboard />)
    const categoryCard = (await screen.findByText('Category Spend Analytics')).closest('.MuiCard-root') as HTMLElement
    expect(within(categoryCard).getByText('Food')).toBeInTheDocument()

    // Investments nature filter (emoji/nature branch)
    await user.click(within(categoryCard).getByRole('button', { name: /Investments/i }))
    expect(within(categoryCard).getByText('SIP')).toBeInTheDocument()
    expect(within(categoryCard).queryByText('Food')).not.toBeInTheDocument()
    await user.click(within(categoryCard).getByRole('button', { name: /^All$/i }))

    // Toggle the same ranked category on then off while still in multi-category mode
    const foodRow = () => within(categoryCard).getAllByText('Food').at(-1)!
    await user.click(foodRow())
    await user.click(foodRow())

    // Global category filter chip (so All Categories also clears categoryFilter)
    const healthHeading = screen.getByText('50 / 30 / 20 Budget Health Evaluation')
    await user.click(within(healthHeading.closest('.MuiCard-root') as HTMLElement).getByText(/Food:/i))
    expect(await screen.findByText(/Category: Food/i)).toBeInTheDocument()

    vi.mocked(hooks.useBudgetCategories).mockReturnValue({
      data: {
        categories: [{ category: 'Food', amount: 5500, count: 3, nature: 'wants' }],
        all_categories: ['Food', 'SIP'],
        is_drilldown: true,
        category_stats: {
          amount: 5500,
          percentage_of_total: 10,
          count: 3,
          avg_ticket: 1833,
          merchants: [{ merchant: 'Cafe', amount: 5500, percentage: 100 }],
        },
      },
      isPending: false,
      error: null,
    } as any)

    // Re-render with drilldown payload (categoryFilter already makes effectiveCategory=Food)
    await user.click(within(categoryCard).getByRole('button', { name: /^Credits$/i }))
    await user.click(within(categoryCard).getByRole('button', { name: /^Debits$/i }))
    expect(await screen.findByText(/Food Drilldown/i)).toBeInTheDocument()
    expect(screen.getAllByText('₹6k').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /All Categories/i }))
    await waitFor(() => {
      expect(screen.queryByText(/Food Drilldown/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/Category: Food/i)).not.toBeInTheDocument()
    })
  }, 60000)
})
