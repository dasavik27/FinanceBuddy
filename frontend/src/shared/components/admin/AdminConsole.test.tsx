import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import AdminConsole from './AdminConsole'
import { apiClient } from '../../api/client'
import { useAppStore } from '../../store/appStore'

vi.mock('../../api/client', () => ({
  apiClient: {
    getAccessRequests: vi.fn(),
    getAppUsers: vi.fn(),
    approveAccessRequest: vi.fn(),
    rejectAccessRequest: vi.fn(),
    inviteUser: vi.fn(),
    suspendUser: vi.fn(),
    updateAppUser: vi.fn(),
    deleteAppUser: vi.fn(),
    getMfSyncStatus: vi.fn(),
    searchMfSchemes: vi.fn(),
    getSyncedAmcs: vi.fn(),
    triggerMfSync: vi.fn(),
    purgeMfSnapshots: vi.fn(),
  },
}))

const mockRequests = {
  requests: [
    {
      id: 'req-1',
      email: 'newuser@test.com',
      name: 'New User',
      investor_type: 'retail',
      notes: '',
      status: 'pending' as const,
      created_at: '2026-01-01T00:00:00Z',
      reviewed_at: null,
    },
  ],
}

const mockUsers = {
  users: [
    {
      user_id: 'u-1',
      email: 'active@test.com',
      status: 'active' as const,
      role: 'user' as const,
      created_at: '2025-06-01T00:00:00Z',
      last_seen_at: '2026-01-15T00:00:00Z',
    },
  ],
}

const mockMfStatus = {
  total_schemes: 1200,
  latest_portfolio_month: '2026-01',
  recent_logs: [{ id: 'log-1', status: 'success', schemes_updated: 50, started_at: '2026-01-10T00:00:00Z' }],
}

describe('AdminConsole', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ userId: 'admin-1', role: 'admin', email: 'admin@test.com' })

    vi.mocked(apiClient.getAccessRequests).mockResolvedValue(mockRequests as any)
    vi.mocked(apiClient.getAppUsers).mockResolvedValue(mockUsers as any)
    vi.mocked(apiClient.getMfSyncStatus).mockResolvedValue(mockMfStatus as any)
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({ schemes: [], total: 0 } as any)
    vi.mocked(apiClient.getSyncedAmcs).mockResolvedValue({ amcs: [] } as any)
  })

  it('renders admin cockpit with access requests tab by default', async () => {
    renderWithProviders(<AdminConsole />)

    expect(screen.getByText('Admin Operations Cockpit')).toBeInTheDocument()
    expect(await screen.findByText('Invite User')).toBeInTheDocument()
    expect(await screen.findByText('newuser@test.com')).toBeInTheDocument()
  })

  it('switches to user accounts tab and lists users', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    await userEvent.click(screen.getByRole('tab', { name: /User Accounts/i }))

    expect(await screen.findByText('active@test.com')).toBeInTheDocument()
  })

  it('switches to MF scheme directory tab', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    await userEvent.click(screen.getByRole('tab', { name: /MF Scheme Directory/i }))

    expect(await screen.findByText(/Sync Top 10 AMCs|Sync full catalogue/i)).toBeInTheDocument()
  })

  it('approves a pending access request', async () => {
    vi.mocked(apiClient.approveAccessRequest).mockResolvedValue({ status: 'approved' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /^Invite$/i }))

    await waitFor(() => {
      expect(apiClient.approveAccessRequest).toHaveBeenCalledWith('req-1', { method: 'invite' })
    })
  })

  it('invites a user directly from the invite form', async () => {
    vi.mocked(apiClient.inviteUser).mockResolvedValue({ status: 'invited' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')

    await userEvent.type(screen.getByLabelText(/^Email$/i), 'invite@test.com', { delay: null })
    await userEvent.type(screen.getByLabelText(/^Name$/i), 'Invited User', { delay: null })
    const submitInvite = screen.getAllByRole('button', { name: /^Invite$/i })
      .find((btn) => btn.getAttribute('type') === 'submit')!
    await userEvent.click(submitInvite)

    await waitFor(() => {
      expect(apiClient.inviteUser).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'invite@test.com' })
      )
    }, { timeout: 30000 })
  }, 30000)
})
