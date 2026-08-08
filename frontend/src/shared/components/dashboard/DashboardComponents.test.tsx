import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import DashboardHub from './DashboardHub'
import { SwitchSessionButton } from './SwitchSessionButton'
import { UploadHistoryList, type UploadHistoryEntry } from './UploadHistoryList'
import { Route, Routes } from 'react-router-dom'

describe('Dashboard Hub & Session Components', () => {
  describe('DashboardHub', () => {
    it('renders all 4 financial pillars and navigates on card click', async () => {
      renderWithProviders(
        <Routes>
          <Route path="/" element={<DashboardHub />} />
          <Route path="/mutual-funds" element={<div>MF Route</div>} />
          <Route path="/equity" element={<div>EQ Route</div>} />
          <Route path="/tax-expert" element={<div>Tax Route</div>} />
          <Route path="/budget" element={<div>Budget Route</div>} />
        </Routes>
      )

      expect(screen.getByText('Select Your Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Mutual Funds')).toBeInTheDocument()
      expect(screen.getByText('Indian Stocks')).toBeInTheDocument()
      expect(screen.getByText('Tax Expert')).toBeInTheDocument()
      expect(screen.getByText('Budget Analyzer')).toBeInTheDocument()

      await userEvent.click(screen.getByText('Mutual Funds'))
      expect(await screen.findByText('MF Route')).toBeInTheDocument()
    })

    it('navigates to equity when Indian Stocks card is clicked', async () => {
      renderWithProviders(
        <Routes>
          <Route path="/" element={<DashboardHub />} />
          <Route path="/equity" element={<div>EQ Route</div>} />
        </Routes>
      )
      await userEvent.click(screen.getByText('Indian Stocks'))
      expect(await screen.findByText('EQ Route')).toBeInTheDocument()
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

      const deleteBtns = screen.getAllByRole('button').filter((b) =>
        b.querySelector('[data-testid="DeleteOutlineIcon"]')
      )
      await userEvent.click(deleteBtns[0])
      expect(onDelete).toHaveBeenCalled()
    })

    it('renders empty state and invalid dates safely', () => {
      renderWithProviders(
        <UploadHistoryList
          history={[{ session_id: 'x', created_at: 'not-a-date', num_funds: null, total_value: null }]}
          activeSessionId={null}
          onSelect={vi.fn()}
          accent="indigo"
          emptyText="Nothing here"
        />
      )
      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('shows emptyText when history is empty', () => {
      renderWithProviders(
        <UploadHistoryList
          history={[]}
          onSelect={vi.fn()}
          emptyText="Nothing here"
        />
      )
      expect(screen.getByText('Nothing here')).toBeInTheDocument()
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

    it('selects a session, closes popover, supports delete and footer close', async () => {
      const fetchHistory = vi.fn().mockResolvedValue([
        {
          session_id: 'sid-a',
          created_at: '2026-02-15T00:00:00Z',
          num_funds: 4,
          total_value: 100000,
        },
        {
          session_id: 'sid-b',
          created_at: '2026-01-15T00:00:00Z',
          num_funds: 2,
          total_value: 50000,
        },
      ])
      const onSelect = vi.fn()
      const onDelete = vi.fn()

      renderWithProviders(
        <SwitchSessionButton
          sessionId="sid-a"
          fetchHistory={fetchHistory}
          onSelect={onSelect}
          onDelete={onDelete}
          accent="emerald"
          buttonLabel="Switch"
          tooltip="Pick"
          popoverTitle="History"
          itemLabel="funds"
          emptyText="None"
          footerTitle="Upload more"
          renderFooter={(close) => (
            <button type="button" onClick={close}>Close footer</button>
          )}
        />
      )

      await userEvent.click(screen.getByText('Switch'))
      expect(await screen.findByText('History')).toBeInTheDocument()
      expect(screen.getByText('Upload more')).toBeInTheDocument()

      await userEvent.click(screen.getByText(/2 funds/i))
      expect(onSelect).toHaveBeenCalledWith('sid-b')

      await userEvent.click(screen.getByText('Switch'))
      await screen.findByText('History')
      const deleteBtns = screen.getAllByRole('button').filter((b) =>
        b.querySelector('[data-testid="DeleteOutlineIcon"], [data-testid="DeleteIcon"]')
      )
      if (deleteBtns.length) {
        await userEvent.click(deleteBtns[0])
        expect(onDelete).toHaveBeenCalled()
      }

      await userEvent.click(screen.getByText('Switch'))
      await screen.findByText('Close footer')
      await userEvent.click(screen.getByText('Close footer'))
      await waitFor(() => {
        expect(screen.queryByText('History')).not.toBeInTheDocument()
      })
    })

    it('closes popover via header X button', async () => {
      const fetchHistory = vi.fn().mockResolvedValue([])
      renderWithProviders(
        <SwitchSessionButton
          sessionId={null}
          fetchHistory={fetchHistory}
          onSelect={vi.fn()}
          buttonLabel="Open"
          tooltip="tip"
          popoverTitle="Sessions"
          itemLabel="items"
        />
      )
      await userEvent.click(screen.getByText('Open'))
      expect(await screen.findByText('Sessions')).toBeInTheDocument()
      await userEvent.click(screen.getByTestId('CloseIcon'))
      await waitFor(() => {
        expect(screen.queryByText('Sessions')).not.toBeInTheDocument()
      })
    })
  })
})
