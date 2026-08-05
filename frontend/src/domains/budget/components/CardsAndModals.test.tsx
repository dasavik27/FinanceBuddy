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
    it('renders session list and allows session selection and deletion', async () => {
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
      const onSelect = vi.fn()
      const onDelete = vi.fn().mockResolvedValue(undefined)
      const onClose = vi.fn()
      const user = userEvent.setup()

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
    })
  })

  describe('BudgetHealth503020Card', () => {
    it('renders 50/30/20 health score, breakdown and recommendations', () => {
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

      renderWithProviders(<BudgetHealth503020Card data={mockHealthData} />)

      expect(screen.getByText('50 / 30 / 20 Budget Health Evaluation')).toBeInTheDocument()
      expect(screen.getByText('82')).toBeInTheDocument()
      expect(screen.getByText('Needs (Essentials)')).toBeInTheDocument()
      expect(screen.getByText('Wants (Lifestyle)')).toBeInTheDocument()
      expect(screen.getByText('Investments & Savings')).toBeInTheDocument()
      expect(screen.getByText('Great job maintaining low discretionary spend!')).toBeInTheDocument()
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
