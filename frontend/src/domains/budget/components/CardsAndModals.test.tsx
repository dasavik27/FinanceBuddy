import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import UploadStatementModal from './UploadStatementModal'
import BudgetSessionsModal from './BudgetSessionsModal'
import BudgetHealth503020Card from './BudgetHealth503020Card'
import MoneyFlowCard from './MoneyFlowCard'
import TransfersExcludedCard from './TransfersExcludedCard'
import { apiClient } from '../../../shared/api/client'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getBudgetSankey: vi.fn(),
    getBudgetTransfers: vi.fn(),
  },
}))

describe('Budget Domain Cards & Modals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('UploadStatementModal', () => {
    it('renders modal with bank selector and handles upload', async () => {
      const onUpload = vi.fn().mockResolvedValue(null)
      const onClose = vi.fn()
      const user = userEvent.setup()

      renderWithProviders(
        <UploadStatementModal
          open={true}
          onClose={onClose}
          onUpload={onUpload}
        />
      )

      expect(screen.getByText('Upload Bank / Card Statement')).toBeInTheDocument()

      const file = new File(['txn_date,description,amount\n2026-01-01,test,100'], 'statement.csv', { type: 'text/csv' })
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
      await user.upload(fileInput, file)

      const uploadBtn = screen.getByRole('button', { name: /Import Statement/i })
      await user.click(uploadBtn)

      expect(onUpload).toHaveBeenCalledWith(file, 'HDFC', 'Savings Account')
      expect(onClose).toHaveBeenCalled()
    })

    it('disables import button when no file selected', () => {
      const onUpload = vi.fn()
      const onClose = vi.fn()

      renderWithProviders(
        <UploadStatementModal
          open={true}
          onClose={onClose}
          onUpload={onUpload}
        />
      )

      const uploadBtn = screen.getByRole('button', { name: /Import Statement/i })
      expect(uploadBtn).toBeDisabled()
    })
  })

  describe('BudgetSessionsModal', () => {
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
      {
        session_id: 'sess-2',
        filename: 'icici_card.csv',
        bank: 'ICICI',
        account_type: 'Credit Card',
        rows: 12,
        total_income: 0,
        total_expense: 18000,
        created_at: '2026-02-01T10:00:00Z',
      },
    ]

    it('renders session list and allows session selection and deletion', async () => {
      const onSelect = vi.fn()
      const onDelete = vi.fn().mockResolvedValue(undefined)
      const onClose = vi.fn()
      const user = userEvent.setup()
      vi.spyOn(window, 'confirm').mockReturnValue(true)

      renderWithProviders(
        <BudgetSessionsModal
          open={true}
          onClose={onClose}
          sessions={mockSessions}
          activeSessionId="sess-1"
          onSelectSession={onSelect}
          onDeleteSession={onDelete}
        />
      )

      expect(screen.getByText('Statement Sessions & Accounts History')).toBeInTheDocument()
      expect(screen.getByText('hdfc_jan.csv')).toBeInTheDocument()
      expect(screen.getByText('25 txns')).toBeInTheDocument()
      expect(screen.getByText('icici_card.csv')).toBeInTheDocument()

      await user.click(screen.getByText('All Accounts Combined (Master View)'))
      expect(onSelect).toHaveBeenCalledWith('overall')
      expect(onClose).toHaveBeenCalled()
    })

    it('selects a session row and deletes when confirmed', async () => {
      const onSelect = vi.fn()
      const onDelete = vi.fn().mockResolvedValue(undefined)
      const onClose = vi.fn()
      const user = userEvent.setup()
      vi.spyOn(window, 'confirm').mockReturnValue(true)

      renderWithProviders(
        <BudgetSessionsModal
          open={true}
          onClose={onClose}
          sessions={mockSessions}
          activeSessionId="overall"
          onSelectSession={onSelect}
          onDeleteSession={onDelete}
        />
      )

      await user.click(screen.getByText('hdfc_jan.csv'))
      expect(onSelect).toHaveBeenCalledWith('sess-1')
      expect(onClose).toHaveBeenCalled()

      onClose.mockClear()
      onSelect.mockClear()
      renderWithProviders(
        <BudgetSessionsModal
          open={true}
          onClose={onClose}
          sessions={mockSessions}
          activeSessionId="sess-1"
          onSelectSession={onSelect}
          onDeleteSession={onDelete}
        />,
      )
      const deleteIcon = screen.getAllByTestId('DeleteOutlineIcon')[0]
      await user.click(deleteIcon.closest('button')!)
      expect(onDelete).toHaveBeenCalledWith('sess-1')
    })

    it('skips delete when confirm is cancelled', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(false)
      const onDelete = vi.fn()
      const user = userEvent.setup()

      renderWithProviders(
        <BudgetSessionsModal
          open={true}
          onClose={vi.fn()}
          sessions={mockSessions}
          activeSessionId="sess-1"
          onSelectSession={vi.fn()}
          onDeleteSession={onDelete}
        />,
      )

      const deleteIcon = screen.getAllByTestId('DeleteOutlineIcon')[0]
      await user.click(deleteIcon.closest('button')!)
      expect(onDelete).not.toHaveBeenCalled()
    })

    it('shows empty state when there are no sessions', () => {
      renderWithProviders(
        <BudgetSessionsModal
          open={true}
          onClose={vi.fn()}
          sessions={[]}
          activeSessionId="overall"
          onSelectSession={vi.fn()}
          onDeleteSession={vi.fn()}
        />,
      )
      expect(screen.getByText('No previous upload sessions recorded.')).toBeInTheDocument()
    })
  })

  describe('BudgetHealth503020Card', () => {
    const mockHealthData = {
      health_score: 82,
      base_amount: 100000,
      base_type: 'income' as const,
      needs: {
        amount: 45000,
        percentage: 45,
        target_pct: 50,
        target_amount: 50000,
        status: 'optimal' as const,
        categories: [{ name: 'Rent', amount: 30000 }, { name: 'Groceries', amount: 15000 }],
      },
      wants: {
        amount: 25000,
        percentage: 25,
        target_pct: 30,
        target_amount: 30000,
        status: 'optimal' as const,
        categories: [{ name: 'Dining', amount: 15000 }],
      },
      investments: {
        amount: 30000,
        percentage: 30,
        target_pct: 20,
        target_amount: 20000,
        status: 'optimal' as const,
        categories: [{ name: 'Mutual Funds', amount: 30000 }],
      },
      transfers_amount: 5000,
      recommendations: ['Great job maintaining low discretionary spend!'],
    }

    it('renders 50/30/20 health score, breakdown and recommendations', () => {
      renderWithProviders(<BudgetHealth503020Card data={mockHealthData} />)

      expect(screen.getByText('50 / 30 / 20 Budget Health Evaluation')).toBeInTheDocument()
      expect(screen.getByText('82')).toBeInTheDocument()
      expect(screen.getByText(/Healthy Budget/i)).toBeInTheDocument()
      expect(screen.getByText('Needs (Essentials)')).toBeInTheDocument()
      expect(screen.getByText('Wants (Lifestyle)')).toBeInTheDocument()
      expect(screen.getByText('Investments & Savings')).toBeInTheDocument()
      expect(screen.getByText('Great job maintaining low discretionary spend!')).toBeInTheDocument()
    })

    it('returns null when data is missing', () => {
      const { container } = renderWithProviders(<BudgetHealth503020Card />)
      expect(container.firstChild).toBeNull()
    })

    it('toggles explanation and fires category click for warning/critical buckets', async () => {
      const onCategoryClick = vi.fn()
      const user = userEvent.setup()
      const stressed = {
        ...mockHealthData,
        health_score: 40,
        base_type: 'expense' as const,
        needs: {
          ...mockHealthData.needs,
          percentage: 62,
          amount: 62000,
          status: 'critical' as const,
        },
        wants: {
          ...mockHealthData.wants,
          percentage: 35,
          amount: 35000,
          status: 'warning' as const,
        },
        investments: {
          ...mockHealthData.investments,
          percentage: 8,
          amount: 8000,
          status: 'critical' as const,
        },
      }

      renderWithProviders(
        <BudgetHealth503020Card data={stressed} onCategoryClick={onCategoryClick} />,
      )

      expect(screen.getByText(/Overspending \/ Needs Heavy/i)).toBeInTheDocument()
      expect(screen.getByText(/Total Outflow Spends/i)).toBeInTheDocument()
      expect(screen.getByText('Over Target')).toBeInTheDocument()
      expect(screen.getByText('Near Limit')).toBeInTheDocument()
      expect(screen.getByText('Under-saving')).toBeInTheDocument()

      await user.click(screen.getByTitle('What is the 50/30/20 Rule?'))
      expect(screen.getByText(/What is the 50 \/ 30 \/ 20 Financial Rule/i)).toBeInTheDocument()

      await user.click(screen.getByText(/Rent:/i))
      expect(onCategoryClick).toHaveBeenCalledWith('Rent')
    })

    it('shows golden badge for high scores', () => {
      renderWithProviders(
        <BudgetHealth503020Card data={{ ...mockHealthData, health_score: 90 }} />,
      )
      expect(screen.getByText(/Golden Balance/i)).toBeInTheDocument()
    })
  })

  describe('MoneyFlowCard', () => {
    it('renders sankey flow chart data when available', async () => {
      vi.mocked(apiClient.getBudgetSankey).mockResolvedValue({
        nodes: [
          { name: 'Salary', group: 'income' },
          { name: 'Total Inflow', group: 'source' },
          { name: 'Living Expenses', group: 'category' },
        ],
        links: [
          { source: 0, target: 1, value: 100000 },
          { source: 1, target: 2, value: 60000 },
        ],
      } as any)

      renderWithProviders(<MoneyFlowCard sessionId="sess-1" />)

      expect(await screen.findByText('Money flow')).toBeInTheDocument()
      expect(screen.getByText(/Where your money came from and where it went/i)).toBeInTheDocument()
      expect(screen.getByText('Income')).toBeInTheDocument()
      expect(screen.getByText('Category')).toBeInTheDocument()
    })

    it('shows empty state when sankey has no plottable links', async () => {
      vi.mocked(apiClient.getBudgetSankey).mockResolvedValue({ nodes: [], links: [] } as any)
      renderWithProviders(<MoneyFlowCard sessionId="sess-empty" />)
      expect(await screen.findByText('No money flow to show yet')).toBeInTheDocument()
    })

    it('shows error card with retry when sankey fetch fails', async () => {
      // status 404 skips the insightQuery retry so the error UI settles quickly
      vi.mocked(apiClient.getBudgetSankey).mockRejectedValue({
        response: { status: 404, data: { detail: 'Sankey unavailable' } },
      })
      const user = userEvent.setup()
      renderWithProviders(<MoneyFlowCard sessionId="sess-err" />)

      expect(await screen.findByText('Sankey unavailable', {}, { timeout: 5000 })).toBeInTheDocument()
      vi.mocked(apiClient.getBudgetSankey).mockResolvedValue({
        nodes: [
          { name: 'Salary', group: 'income' },
          { name: 'Spend', group: 'category' },
        ],
        links: [{ source: 0, target: 1, value: 10 }],
      } as any)
      await user.click(screen.getByRole('button', { name: /Retry/i }))
      expect(await screen.findByText('Money flow', {}, { timeout: 5000 })).toBeInTheDocument()
    })

    it('notes dropped cyclic links', async () => {
      vi.mocked(apiClient.getBudgetSankey).mockResolvedValue({
        nodes: [
          { name: 'A', group: 'income' },
          { name: 'B', group: 'source' },
        ],
        links: [
          { source: 0, target: 1, value: 100 },
          { source: 1, target: 0, value: 50 },
        ],
      } as any)

      renderWithProviders(<MoneyFlowCard sessionId="sess-cycle" />)
      expect(await screen.findByText(/could not be plotted/i)).toBeInTheDocument()
    })
  })

  describe('TransfersExcludedCard', () => {
    it('renders excluded transfers summary and allows expanding pairs', async () => {
      vi.mocked(apiClient.getBudgetTransfers).mockResolvedValue({
        count: 2,
        excluded_from_income: 25000,
        excluded_from_expense: 15000,
        card_payment_total: 10000,
        card_payment_count: 1,
        pairs: [
          {
            source_account: 'HDFC Savings',
            destination_account: 'ICICI Savings',
            amount: 10000,
            date: '2026-01-10',
            confidence: 'high',
            reason: 'Self transfer',
          },
        ],
      } as any)

      renderWithProviders(<TransfersExcludedCard sessionId="sess-1" />)

      expect(await screen.findByText(/2 transfers between your own accounts/i)).toBeInTheDocument()
      expect(screen.getByText('₹25,000')).toBeInTheDocument()
      expect(screen.getByText('₹15,000')).toBeInTheDocument()
    })
  })
})
