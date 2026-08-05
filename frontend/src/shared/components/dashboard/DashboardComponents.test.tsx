import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import DashboardHub from './DashboardHub'
import { SwitchSessionButton } from './SwitchSessionButton'
import { UploadHistoryList, type UploadHistoryEntry } from './UploadHistoryList'

describe('Dashboard Hub & Session Components', () => {
  describe('DashboardHub', () => {
    it('renders all 4 financial pillars and navigates on card click', async () => {
      renderWithProviders(<DashboardHub />)

      expect(screen.getByText('Select Your Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Mutual Funds')).toBeInTheDocument()
      expect(screen.getByText('Indian Stocks')).toBeInTheDocument()
      expect(screen.getByText('Tax Expert')).toBeInTheDocument()
      expect(screen.getByText('Budget Analyzer')).toBeInTheDocument()
    })
  })

  describe('UploadHistoryList', () => {
    const mockEntries: UploadHistoryEntry[] = [
      {
        session_id: 'sid-1',
        created_at: '2026-03-01T10:00:00Z',
        num_funds: 12,
        total_value: 450000,
      },
      {
        session_id: 'sid-2',
        created_at: '2026-01-01T10:00:00Z',
        num_funds: 8,
        total_value: 320000,
      },
    ]

    it('renders list of historical uploads and handles select & delete', async () => {
      const onSelect = vi.fn()
      const onDelete = vi.fn()

      renderWithProviders(
        <UploadHistoryList
          history={mockEntries}
          activeSessionId="sid-1"
          onSelect={onSelect}
          onDelete={onDelete}
          accent="emerald"
        />
      )

      expect(screen.getByText('Active')).toBeInTheDocument()
      expect(screen.getByText(/12 Holdings/i)).toBeInTheDocument()
      expect(screen.getByText(/8 Holdings/i)).toBeInTheDocument()

      await userEvent.click(screen.getByText(/8 Holdings/i))
      expect(onSelect).toHaveBeenCalledWith('sid-2')
    })
  })

  describe('SwitchSessionButton', () => {
    it('opens popover on click and loads history', async () => {
      const fetchHistory = vi.fn().mockResolvedValue([
        {
          session_id: 'sid-popover',
          created_at: '2026-02-15T00:00:00Z',
          num_funds: 15,
          total_value: 800000,
        },
      ])
      const onSelect = vi.fn()

      renderWithProviders(
        <SwitchSessionButton
          sessionId="sid-active"
          fetchHistory={fetchHistory}
          onSelect={onSelect}
          buttonLabel="Switch Portfolio"
          tooltip="Choose statement"
          popoverTitle="Saved Portfolios"
          itemLabel="holdings"
        />
      )

      const btn = screen.getByText('Switch Portfolio')
      await userEvent.click(btn)

      expect(fetchHistory).toHaveBeenCalled()
      expect(await screen.findByText('Saved Portfolios')).toBeInTheDocument()
      expect(await screen.findByText(/15 holdings/i)).toBeInTheDocument()
      expect(await screen.findByText('₹8,00,000')).toBeInTheDocument()
    })
  })
})
