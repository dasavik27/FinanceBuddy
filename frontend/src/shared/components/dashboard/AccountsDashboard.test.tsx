import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import AccountsDashboard from './AccountsDashboard'
import { apiClient } from '../../api/client'
import { useAppStore } from '../../store/appStore'

vi.mock('../../api/client', () => ({
  apiClient: {
    getAccountsSummary: vi.fn(),
    purgeAccount: vi.fn(),
    clearSystemCaches: vi.fn(),
    exportAccount: vi.fn(),
  },
}))

const mockSummary = {
  accounts: [
    {
      pan: 'ABCDE1234F',
      sessions: [
        { module: 'mutual_funds' },
        { module: 'equity' },
        { module: 'budget' },
      ],
    },
  ],
}

describe('AccountsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ userId: 'u-acct', pan: 'ABCDE1234F', email: 'user@test.com' })
    vi.mocked(apiClient.getAccountsSummary).mockResolvedValue(mockSummary as any)
    vi.mocked(apiClient.exportAccount).mockResolvedValue({ pan: 'ABCDE1234F', sessions: [] } as any)
    vi.mocked(apiClient.clearSystemCaches).mockResolvedValue({ status: 'ok' } as any)
    vi.mocked(apiClient.purgeAccount).mockResolvedValue({ status: 'purged' } as any)
  })

  it('renders account settings with active modules', async () => {
    renderWithProviders(<AccountsDashboard />)

    expect(await screen.findByText('Account Settings', undefined, { timeout: 30000 })).toBeInTheDocument()
    expect(screen.getByText('ABCDE1234F')).toBeInTheDocument()
    expect(screen.getByText('Mutual Funds')).toBeInTheDocument()
    expect(screen.getByText('Indian Stocks')).toBeInTheDocument()
    expect(screen.getByText('Budget Analyzer')).toBeInTheDocument()
  }, 30000)

  it('shows empty state when no accounts exist', async () => {
    vi.mocked(apiClient.getAccountsSummary).mockResolvedValue({ accounts: [] } as any)

    renderWithProviders(<AccountsDashboard />)

    expect(await screen.findByText('No Active Accounts Found')).toBeInTheDocument()
  })

  it('exports account data as JSON download', async () => {
    // jsdom has no URL.createObjectURL — stub like TaxExpertDashboard export test
    const createObjectURL = vi.fn(() => 'blob:mock-export')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderWithProviders(<AccountsDashboard />)
    await screen.findByText('Account Settings')

    await userEvent.click(screen.getByRole('button', { name: /Export Account Data/i }))

    await waitFor(() => {
      expect(apiClient.exportAccount).toHaveBeenCalled()
      expect(createObjectURL).toHaveBeenCalled()
      expect(clickSpy).toHaveBeenCalled()
    })

    clickSpy.mockRestore()
    vi.unstubAllGlobals()
  })

  it('clears system caches on button click', async () => {
    renderWithProviders(<AccountsDashboard />)
    await screen.findByText('Account Settings')

    await userEvent.click(screen.getByRole('button', { name: /Clear All Caches/i }))

    await waitFor(() => {
      expect(apiClient.clearSystemCaches).toHaveBeenCalled()
    })
  })

  it('opens purge confirmation dialog', async () => {
    renderWithProviders(<AccountsDashboard />)
    await screen.findByText('ABCDE1234F')

    const deleteButtons = screen.getAllByRole('button').filter((btn) =>
      btn.querySelector('[data-testid="DeleteIcon"]')
    )
    await userEvent.click(deleteButtons[0])

    expect(await screen.findByText(/Purge Account Data/i)).toBeInTheDocument()
  })

  it('confirms purge and cancels purge dialog', async () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    useAppStore.setState({ logout })
    renderWithProviders(<AccountsDashboard />)
    await screen.findByText('ABCDE1234F')

    const deleteButtons = screen.getAllByRole('button').filter((btn) =>
      btn.querySelector('[data-testid="DeleteIcon"]')
    )
    await userEvent.click(deleteButtons[0])
    expect(await screen.findByText(/Purge Account Data/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Cancel/i }))
    await waitFor(() => {
      expect(screen.queryByText(/Purge Account Data/i)).not.toBeInTheDocument()
    })

    await userEvent.click(deleteButtons[0])
    await userEvent.click(await screen.findByRole('button', { name: /Delete Permanently/i }))
    await waitFor(() => {
      expect(apiClient.purgeAccount).toHaveBeenCalled()
    })
  })

  it('navigates when an active module row is clicked', async () => {
    renderWithProviders(
      <>
        <AccountsDashboard />
      </>
    )
    await screen.findByText('Mutual Funds')
    await userEvent.click(screen.getByText('Mutual Funds'))
  })

  it('renders unknown modules without a navigation path', async () => {
    vi.mocked(apiClient.getAccountsSummary).mockResolvedValue({
      accounts: [
        {
          pan: 'ABCDE1234F',
          sessions: [{ module: 'custom_module' }, { module: 'mutual_funds' }],
        },
      ],
    } as any)
    renderWithProviders(<AccountsDashboard />)
    expect(await screen.findByText('custom_module')).toBeInTheDocument()
    expect(screen.getByText(/2 SESSIONS/i)).toBeInTheDocument()
  })

  it('shows singular SESSION label for one session', async () => {
    vi.mocked(apiClient.getAccountsSummary).mockResolvedValue({
      accounts: [{ pan: 'ABCDE1234F', sessions: [{ module: 'equity' }] }],
    } as any)
    renderWithProviders(<AccountsDashboard />)
    expect(await screen.findByText(/1 SESSION$/i)).toBeInTheDocument()
    expect(screen.getByText(/1 session$/i)).toBeInTheDocument()
  })

  it('surfaces export and cache errors via snackbar', async () => {
    vi.mocked(apiClient.exportAccount).mockRejectedValueOnce({
      response: { data: { detail: 'Export denied' } },
    })
    vi.mocked(apiClient.clearSystemCaches).mockRejectedValueOnce({
      response: { data: { detail: 'Cache clear failed' } },
    })

    renderWithProviders(<AccountsDashboard />)
    await screen.findByText('Account Settings')

    await userEvent.click(screen.getByRole('button', { name: /Export Account Data/i }))
    expect(await screen.findByText('Export denied')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Clear All Caches/i }))
    expect(await screen.findByText('Cache clear failed')).toBeInTheDocument()
  })

  it('closes snackbar on Alert dismiss', async () => {
    renderWithProviders(<AccountsDashboard />)
    await screen.findByText('Account Settings')
    await userEvent.click(screen.getByRole('button', { name: /Clear All Caches/i }))
    expect(await screen.findByText(/cleared successfully/i)).toBeInTheDocument()
  })
})
