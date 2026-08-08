import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, within, fireEvent } from '@testing-library/react'
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
      notes: 'Looking for SIP tools',
      status: 'pending' as const,
      created_at: '2026-01-01T00:00:00Z',
      reviewed_at: null,
    },
    {
      id: 'req-2',
      email: 'approved@test.com',
      name: 'Approved User',
      investor_type: 'hni',
      notes: 'Wealth management',
      status: 'approved' as const,
      created_at: '2025-12-01T00:00:00Z',
      reviewed_at: '2025-12-02T00:00:00Z',
    },
    {
      id: 'req-3',
      email: 'advisor@test.com',
      name: 'Advisor Lead',
      investor_type: 'advisor',
      notes: '',
      status: 'pending' as const,
      created_at: null,
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
    {
      user_id: 'u-pending',
      email: 'pending@test.com',
      status: 'pending' as const,
      role: 'user' as const,
      created_at: '2026-01-01T00:00:00Z',
      last_seen_at: null,
    },
    {
      user_id: 'admin-1',
      email: 'admin@test.com',
      status: 'active' as const,
      role: 'admin' as const,
      created_at: '2025-01-01T00:00:00Z',
      last_seen_at: '2026-02-01T00:00:00Z',
    },
    {
      user_id: 'u-suspended',
      email: 'suspended@test.com',
      status: 'suspended' as const,
      role: 'user' as const,
      created_at: '2025-03-01T00:00:00Z',
      last_seen_at: '2025-08-01T00:00:00Z',
    },
  ],
}

const mockMfScheme = {
  isin: 'INF123456789',
  scheme_code: 'HDFC001',
  scheme_name: 'HDFC Flexi Cap Fund',
  amc: 'HDFC',
  category: 'Flexi Cap',
  aum_cr: 25000,
  aum_formatted: '₹25,000 Cr',
  expense_ratio: 1.05,
  risk_level: 'VERY HIGH',
  portfolio_date: '2026-01-31',
  sectors_count: 2,
  holdings_count: 2,
  sectors: [
    { sector: 'Financials', value: 28 },
    { sector: 'IT', value: 12 },
  ],
  holdings: [
    { name: 'HDFC Bank', pct: 8.5 },
    { name: 'Infosys', pct: 4.2 },
  ],
  source: 'amfi',
  updated_at: '2026-02-01T00:00:00Z',
}

const mockMfSchemeMild = {
  ...mockMfScheme,
  isin: 'INF987654321',
  scheme_name: 'SBI Large Cap Fund',
  amc: 'SBI',
  category: 'Large Cap',
  risk_level: 'MODERATE',
  expense_ratio: null,
  portfolio_date: null,
  aum_formatted: '₹10,000 Cr',
  holdings: [{ name: 'Reliance', pct: 7 }],
  sectors: [{ sector: 'Energy', value: 15 }],
}

const mockMfStatus = {
  total_schemes: 1200,
  latest_portfolio_month: '2026-01',
  recent_logs: [
    {
      id: 1,
      triggered_by: 'admin@test.com',
      status: 'completed' as const,
      schemes_updated: 50,
      portfolio_month: '2026-01',
      duration_seconds: 42,
      error_message: null,
      created_at: '2026-01-10T00:00:00Z',
    },
    {
      id: 2,
      triggered_by: 'system',
      status: 'failed' as const,
      schemes_updated: 0,
      portfolio_month: '2025-12',
      duration_seconds: 12,
      error_message: 'AMFI timeout',
      created_at: '2025-12-20T00:00:00Z',
    },
    {
      id: 3,
      triggered_by: 'admin@test.com',
      status: 'in_progress' as const,
      schemes_updated: 10,
      portfolio_month: '2026-02',
      duration_seconds: 5,
      error_message: null,
      created_at: null,
    },
  ],
}

const mockSyncedAmcs = {
  amcs: [
    { amc: 'HDFC', schemes_count: 120, total_aum_cr: 50000 },
    { amc: 'SBI', schemes_count: 90, total_aum_cr: 40000 },
  ],
}

async function goToUsersTab() {
  await screen.findByText('newuser@test.com')
  await userEvent.click(screen.getByRole('tab', { name: /User Accounts/i }))
  expect(await screen.findByText('active@test.com')).toBeInTheDocument()
}

async function goToMfTab() {
  await screen.findByText('newuser@test.com')
  await userEvent.click(screen.getByRole('tab', { name: /MF Scheme Directory/i }))
  expect(await screen.findByText('Ingestion scope')).toBeInTheDocument()
}

function setInputValue(element: HTMLElement, value: string) {
  fireEvent.change(element, { target: { value } })
}

describe('AdminConsole', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ userId: 'admin-1', role: 'admin', email: 'admin@test.com' })

    vi.mocked(apiClient.getAccessRequests).mockResolvedValue(mockRequests as any)
    vi.mocked(apiClient.getAppUsers).mockResolvedValue(mockUsers as any)
    vi.mocked(apiClient.getMfSyncStatus).mockResolvedValue(mockMfStatus as any)
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({
      schemes: [mockMfScheme, mockMfSchemeMild],
      total: 3,
    } as any)
    vi.mocked(apiClient.getSyncedAmcs).mockResolvedValue(mockSyncedAmcs as any)

    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // ── Access Requests ──────────────────────────────────────────────────────

  it('renders admin cockpit with access requests tab by default', async () => {
    renderWithProviders(<AdminConsole />)

    expect(screen.getByText('Admin Operations Cockpit')).toBeInTheDocument()
    expect(await screen.findByText('Invite User')).toBeInTheDocument()
    expect(await screen.findByText('newuser@test.com')).toBeInTheDocument()
    expect(screen.getByText('TOTAL REQUESTS')).toBeInTheDocument()
    expect(screen.getByText('Revoke Access')).toBeInTheDocument()
  })

  it('filters access requests by pending / approved / all tabs', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')
    expect(screen.getByText('approved@test.com')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /^Pending/i }))
    expect(screen.getByText('newuser@test.com')).toBeInTheDocument()
    expect(screen.queryByText('approved@test.com')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /^Approved/i }))
    expect(await screen.findByText('approved@test.com')).toBeInTheDocument()
    expect(screen.queryByText('newuser@test.com')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /^All/i }))
    expect(await screen.findByText('newuser@test.com')).toBeInTheDocument()
    expect(screen.getByText('approved@test.com')).toBeInTheDocument()
  })

  it('searches access requests and shows empty state when no match', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    setInputValue(screen.getByPlaceholderText(/Search leads/i), 'no-such-lead')
    expect(await screen.findByText('No access requests found')).toBeInTheDocument()
    expect(screen.getByText(/Try adjusting your search criteria/i)).toBeInTheDocument()
  })

  it('approves a pending access request and shows success snackbar', async () => {
    vi.mocked(apiClient.approveAccessRequest).mockResolvedValue({
      status: 'approved',
      message: 'Invite email sent to newuser@test.com!',
    } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /^Invite$/i }))

    await waitFor(() => {
      expect(apiClient.approveAccessRequest).toHaveBeenCalledWith('req-1', { method: 'invite' })
    })
    expect(await screen.findByText(/Invite email sent to newuser@test.com/i)).toBeInTheDocument()
  })

  it('shows error snackbar when approve fails', async () => {
    vi.mocked(apiClient.approveAccessRequest).mockRejectedValue({
      response: { data: { detail: 'Approve failed hard' } },
    })

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /^Invite$/i }))

    expect(await screen.findByText('Approve failed hard')).toBeInTheDocument()
  })

  it('rejects a pending request after confirm', async () => {
    vi.mocked(apiClient.rejectAccessRequest).mockResolvedValue({
      message: 'Request removed',
    } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    const rejectBtn = within(row).getByTestId('DeleteOutlineIcon').closest('button')!
    await userEvent.click(rejectBtn)

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled()
      expect(apiClient.rejectAccessRequest).toHaveBeenCalledWith('req-1')
    })
    expect(await screen.findByText(/Request removed|rejected/i)).toBeInTheDocument()
  })

  it('does not reject when confirm is cancelled', async () => {
    vi.mocked(confirm).mockReturnValue(false)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    await userEvent.click(within(row).getByTestId('DeleteOutlineIcon').closest('button')!)

    expect(apiClient.rejectAccessRequest).not.toHaveBeenCalled()
  })

  it('shows error when reject fails', async () => {
    vi.mocked(apiClient.rejectAccessRequest).mockRejectedValue(new Error('Reject boom'))

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    await userEvent.click(within(row).getByTestId('DeleteOutlineIcon').closest('button')!)

    expect(await screen.findByText('Reject boom')).toBeInTheDocument()
  })

  it('re-sends invite for an already approved request', async () => {
    vi.mocked(apiClient.approveAccessRequest).mockResolvedValue({ message: 'Re-sent' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('approved@test.com')

    const row = screen.getByText('approved@test.com').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /Re-send Invite/i }))

    await waitFor(() => {
      expect(apiClient.approveAccessRequest).toHaveBeenCalledWith('req-2', { method: 'invite' })
    })
  })

  it('copies applicant email and shows copied state', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    const row = screen.getByText('newuser@test.com').closest('tr')!
    fireEvent.click(within(row).getByTestId('ContentCopyIcon').closest('button')!)

    await waitFor(() => {
      expect(within(row).getByTestId('CheckIcon')).toBeInTheDocument()
    })
  })

  it('invites a user directly from the invite form', async () => {
    vi.mocked(apiClient.inviteUser).mockResolvedValue({ status: 'invited', message: 'Invite sent!' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')

    setInputValue(screen.getByLabelText(/^Email$/i), 'invite@test.com')
    setInputValue(screen.getByLabelText(/^Name$/i), 'Invited User')
    const submitInvite = screen.getAllByRole('button', { name: /^Invite$/i })
      .find((btn) => btn.getAttribute('type') === 'submit')!
    await userEvent.click(submitInvite)

    await waitFor(() => {
      expect(apiClient.inviteUser).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'invite@test.com', name: 'Invited User', method: 'invite' })
      )
    })
    expect(await screen.findByText('Invite sent!')).toBeInTheDocument()
  })

  it('shows error when invite is submitted without email', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')

    const submitInvite = screen.getAllByRole('button', { name: /^Invite$/i })
      .find((btn) => btn.getAttribute('type') === 'submit')!
    await userEvent.click(submitInvite)

    expect(await screen.findByText('Email is required to invite a user.')).toBeInTheDocument()
    expect(apiClient.inviteUser).not.toHaveBeenCalled()
  })

  it('shows error snackbar when invite API fails', async () => {
    vi.mocked(apiClient.inviteUser).mockRejectedValue({
      response: { data: { detail: 'Invite API down' } },
    })

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')

    setInputValue(screen.getByLabelText(/^Email$/i), 'fail@test.com')
    const submitInvite = screen.getAllByRole('button', { name: /^Invite$/i })
      .find((btn) => btn.getAttribute('type') === 'submit')!
    await userEvent.click(submitInvite)

    expect(await screen.findByText('Invite API down')).toBeInTheDocument()
  })

  it('suspends a user from the revoke form', async () => {
    vi.mocked(apiClient.suspendUser).mockResolvedValue({ message: 'User suspended.' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Revoke Access')

    setInputValue(screen.getByLabelText(/Email to suspend/i), 'active@test.com')
    await userEvent.click(screen.getByRole('button', { name: /Suspend Access/i }))

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled()
      expect(apiClient.suspendUser).toHaveBeenCalledWith('active@test.com')
    })
    expect(await screen.findByText(/User suspended/i)).toBeInTheDocument()
  })

  it('requires email and confirm before suspend', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('Revoke Access')

    await userEvent.click(screen.getByRole('button', { name: /Suspend Access/i }))
    expect(await screen.findByText('Email is required to suspend a user.')).toBeInTheDocument()

    setInputValue(screen.getByLabelText(/Email to suspend/i), 'x@test.com')
    vi.mocked(confirm).mockReturnValue(false)
    await userEvent.click(screen.getByRole('button', { name: /Suspend Access/i }))
    expect(apiClient.suspendUser).not.toHaveBeenCalled()
  })

  it('shows error when suspend API fails', async () => {
    vi.mocked(apiClient.suspendUser).mockRejectedValue(new Error('Suspend failed'))

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Revoke Access')

    setInputValue(screen.getByLabelText(/Email to suspend/i), 'active@test.com')
    await userEvent.click(screen.getByRole('button', { name: /Suspend Access/i }))

    expect(await screen.findByText('Suspend failed')).toBeInTheDocument()
  })

  it('shows access requests fetch error alert', async () => {
    vi.mocked(apiClient.getAccessRequests).mockRejectedValue({
      response: { data: { detail: 'Access list unavailable' } },
    })

    renderWithProviders(<AdminConsole />)
    expect(await screen.findByText('Access list unavailable')).toBeInTheDocument()
  })

  it('refreshes access requests from header button', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')
    vi.mocked(apiClient.getAccessRequests).mockClear()

    await userEvent.click(screen.getByRole('button', { name: /Refresh Data/i }))
    await waitFor(() => {
      expect(apiClient.getAccessRequests).toHaveBeenCalled()
    })
  })

  it('shows empty pending list when there are no requests', async () => {
    vi.mocked(apiClient.getAccessRequests).mockResolvedValue({ requests: [] } as any)

    renderWithProviders(<AdminConsole />)
    expect(await screen.findByText('No access requests found')).toBeInTheDocument()
    expect(screen.getByText(/Pending submissions will appear here/i)).toBeInTheDocument()
  })

  // ── User Accounts ────────────────────────────────────────────────────────

  it('switches to user accounts tab and lists users', async () => {
    renderWithProviders(<AdminConsole />)
    await goToUsersTab()
    expect(screen.getByText('TOTAL ACCOUNTS')).toBeInTheDocument()
    expect(screen.getByText('pending@test.com')).toBeInTheDocument()
    expect(screen.getByText('suspended@test.com')).toBeInTheDocument()
  })

  it('searches user accounts and shows empty state', async () => {
    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    setInputValue(
      screen.getByPlaceholderText(/Search accounts by email or user id/i),
      'zzz-no-match'
    )
    expect(await screen.findByText('No user accounts found')).toBeInTheDocument()
    expect(screen.getByText(/Try a different search term/i)).toBeInTheDocument()
  })

  it('updates role/status and saves account', async () => {
    vi.mocked(apiClient.updateAppUser).mockResolvedValue({ ok: true } as any)

    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('active@test.com').closest('tr')!
    const selects = within(row).getAllByRole('combobox') as HTMLSelectElement[]
    await userEvent.selectOptions(selects[0], 'suspended')
    await userEvent.selectOptions(selects[1], 'admin')

    const saveBtn = within(row).getByRole('button', { name: /^Save$/i })
    expect(saveBtn).not.toBeDisabled()
    await userEvent.click(saveBtn)

    await waitFor(() => {
      expect(apiClient.updateAppUser).toHaveBeenCalledWith('u-1', {
        status: 'suspended',
        role: 'admin',
      })
    })
    expect(await screen.findByText(/User account updated successfully/i)).toBeInTheDocument()
  })

  it('shows error when save account fails', async () => {
    vi.mocked(apiClient.updateAppUser).mockRejectedValue({
      response: { data: { detail: 'Update denied' } },
    })

    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('active@test.com').closest('tr')!
    const statusSelect = within(row).getAllByRole('combobox')[0] as HTMLSelectElement
    await userEvent.selectOptions(statusSelect, 'pending')
    await userEvent.click(within(row).getByRole('button', { name: /^Save$/i }))

    expect(await screen.findByText('Update denied')).toBeInTheDocument()
  })

  it('quick-activates a pending user', async () => {
    vi.mocked(apiClient.updateAppUser).mockResolvedValue({ ok: true } as any)

    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('pending@test.com').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /^Activate$/i }))

    await waitFor(() => {
      expect(apiClient.updateAppUser).toHaveBeenCalledWith('u-pending', { status: 'active' })
    })
    expect(await screen.findByText(/activated/i)).toBeInTheDocument()
  })

  it('shows error when activate fails', async () => {
    vi.mocked(apiClient.updateAppUser).mockRejectedValue(new Error('Activate failed'))

    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('pending@test.com').closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /^Activate$/i }))

    expect(await screen.findByText('Activate failed')).toBeInTheDocument()
  })

  it('opens delete confirm dialog and deletes user after email confirmation', async () => {
    vi.mocked(apiClient.deleteAppUser).mockResolvedValue({
      message: 'Deleted account for active@test.com.',
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('active@test.com').closest('tr')!
    await userEvent.click(within(row).getByTestId('DeleteOutlineIcon').closest('button')!)

    expect(await screen.findByText('Delete User Permanently')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('button', { name: /Delete Forever/i })).toBeDisabled()

    setInputValue(within(dialog).getByPlaceholderText('active@test.com'), 'active@test.com')
    await userEvent.click(within(dialog).getByRole('button', { name: /Delete Forever/i }))

    await waitFor(() => {
      expect(apiClient.deleteAppUser).toHaveBeenCalledWith('u-1')
    })
    expect(await screen.findByText(/Deleted account for active@test.com/i)).toBeInTheDocument()
  })

  it('cancels delete dialog without calling API', async () => {
    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('active@test.com').closest('tr')!
    await userEvent.click(within(row).getByTestId('DeleteOutlineIcon').closest('button')!)

    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /Cancel/i }))
    await waitFor(() => {
      expect(screen.queryByText('Delete User Permanently')).not.toBeInTheDocument()
    })
    expect(apiClient.deleteAppUser).not.toHaveBeenCalled()
  })

  it('shows error when delete fails', async () => {
    vi.mocked(apiClient.deleteAppUser).mockRejectedValue({
      response: { data: { detail: 'Delete blocked' } },
    })

    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('active@test.com').closest('tr')!
    await userEvent.click(within(row).getByTestId('DeleteOutlineIcon').closest('button')!)

    const dialog = await screen.findByRole('dialog')
    setInputValue(within(dialog).getByPlaceholderText('active@test.com'), 'active@test.com')
    await userEvent.click(within(dialog).getByRole('button', { name: /Delete Forever/i }))

    expect(await screen.findByText('Delete blocked')).toBeInTheDocument()
  })

  it('disables delete for the current admin user', async () => {
    renderWithProviders(<AdminConsole />)
    await goToUsersTab()

    const row = screen.getByText('admin@test.com').closest('tr')!
    expect(within(row).getByTestId('DeleteOutlineIcon').closest('button')).toBeDisabled()
  })

  it('shows accounts fetch error and refreshes on users tab', async () => {
    vi.mocked(apiClient.getAppUsers).mockRejectedValueOnce({
      response: { data: { detail: 'Accounts unavailable' } },
    })

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')
    await userEvent.click(screen.getByRole('tab', { name: /User Accounts/i }))
    expect(await screen.findByText('Accounts unavailable')).toBeInTheDocument()

    vi.mocked(apiClient.getAppUsers).mockResolvedValue(mockUsers as any)
    vi.mocked(apiClient.getAppUsers).mockClear()
    await userEvent.click(screen.getByRole('button', { name: /Refresh Data/i }))
    await waitFor(() => {
      expect(apiClient.getAppUsers).toHaveBeenCalled()
    })
  })

  it('shows empty accounts state without search', async () => {
    vi.mocked(apiClient.getAppUsers).mockResolvedValue({ users: [] } as any)

    renderWithProviders(<AdminConsole />)
    await userEvent.click(await screen.findByRole('tab', { name: /User Accounts/i }))
    expect(await screen.findByText('No user accounts found')).toBeInTheDocument()
    expect(screen.getByText(/Provisioned users will appear here/i)).toBeInTheDocument()
  })

  // ── MF Scheme Directory ──────────────────────────────────────────────────

  it('switches to MF scheme directory tab', async () => {
    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    expect(screen.getByText('Mutual Fund Scheme Directory')).toBeInTheDocument()
    expect(screen.getByText('1,200 schemes in DB')).toBeInTheDocument()
    expect(apiClient.getMfSyncStatus).toHaveBeenCalled()
    expect(apiClient.searchMfSchemes).toHaveBeenCalled()
    expect(apiClient.getSyncedAmcs).toHaveBeenCalled()
  })

  it('changes sync scope and triggers top5 / full catalogue sync', async () => {
    vi.mocked(apiClient.triggerMfSync).mockResolvedValue({
      message: 'Synced OK',
      schemes_updated: 100,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByText('Top 5 AMCs'))
    expect(screen.getByRole('button', { name: /Sync Top 5 AMCs/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Sync Top 5 AMCs/i }))

    await waitFor(() => {
      expect(apiClient.triggerMfSync).toHaveBeenCalledWith({ preset: 'top5' })
    })
    // After sync the panel moves to explore (snackbar text can race with refetch).
    expect(await screen.findByText('Scheme explorer')).toBeInTheDocument()
  })

  it('triggers full catalogue sync from all scope', async () => {
    vi.mocked(apiClient.triggerMfSync).mockResolvedValue({ schemes_updated: 999 } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByText('Full catalogue'))
    await userEvent.click(screen.getByRole('button', { name: /Sync full catalogue/i }))

    await waitFor(() => {
      expect(apiClient.triggerMfSync).toHaveBeenCalledWith({ preset: 'all' })
    })
    expect(await screen.findByText(/Successfully synced 999/i)).toBeInTheDocument()
  })

  it('supports custom AMC selection, add, clear, and sync', async () => {
    vi.mocked(apiClient.triggerMfSync).mockResolvedValue({
      message: 'Custom sync done',
      schemes_updated: 10,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByText('Choose AMCs'))
    expect(screen.getByText(/SELECT AMCS/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Clear/i }))
    await userEvent.click(screen.getByRole('button', { name: /Sync 0 selected/i }))
    expect(await screen.findByText(/Select at least one AMC before syncing/i)).toBeInTheDocument()

    setInputValue(screen.getByPlaceholderText(/Add AMC name/i), 'Navi')
    await userEvent.click(screen.getByRole('button', { name: /^Add$/i }))
    expect(screen.getByRole('button', { name: /Sync 1 selected AMC$/i })).toBeInTheDocument()

    // Duplicate add (case-insensitive) clears input without duplicating
    setInputValue(screen.getByPlaceholderText(/Add AMC name/i), 'navi')
    fireEvent.keyDown(screen.getByPlaceholderText(/Add AMC name/i), { key: 'Enter' })
    expect(screen.getByRole('button', { name: /Sync 1 selected AMC$/i })).toBeInTheDocument()

    // Toggle built-in HDFC chip on (after Clear, default selection is empty)
    await userEvent.click(screen.getByRole('button', { name: /Clear/i }))
    await userEvent.click(screen.getAllByRole('button', { name: /^HDFC$/i })[0])

    await userEvent.click(screen.getByRole('button', { name: /Sync 1 selected AMC$/i }))
    await waitFor(() => {
      expect(apiClient.triggerMfSync).toHaveBeenCalledWith({ amcs: ['HDFC'] })
    })
  }, 60000)

  it('selects all built-in AMCs in custom scope', async () => {
    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByText('Choose AMCs'))
    await userEvent.click(screen.getByRole('button', { name: /Select all/i }))
    expect(screen.getByRole('button', { name: /Sync \d+ selected AMCs/i })).toBeInTheDocument()
  })

  it('ignores empty AMC add via Enter', async () => {
    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByText('Choose AMCs'))

    fireEvent.keyDown(screen.getByPlaceholderText(/Add AMC name/i), { key: 'Enter' })
    expect(screen.getByText('Ingestion scope')).toBeInTheDocument()
  })

  it('shows error snackbar when MF sync fails', async () => {
    vi.mocked(apiClient.triggerMfSync).mockRejectedValue({
      response: { data: { detail: 'Sync unavailable' } },
    })

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByRole('button', { name: /Sync Top 10 AMCs/i }))

    expect(await screen.findByText('Sync unavailable')).toBeInTheDocument()
  })

  it('shows error when market data fails to load', async () => {
    vi.mocked(apiClient.getMfSyncStatus).mockRejectedValue({
      response: { data: { detail: 'Market data offline' } },
    })

    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')
    await userEvent.click(screen.getByRole('tab', { name: /MF Scheme Directory/i }))

    expect(await screen.findByText('Market data offline')).toBeInTheDocument()
  })

  it('refreshes MF data from header and status refresh icon', async () => {
    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    vi.mocked(apiClient.getMfSyncStatus).mockClear()

    await userEvent.click(screen.getByRole('button', { name: /Refresh Data/i }))
    await waitFor(() => {
      expect(apiClient.getMfSyncStatus).toHaveBeenCalled()
    })
  })

  it('purges a single AMC from the purge dialog', async () => {
    vi.mocked(apiClient.purgeMfSnapshots).mockResolvedValue({
      message: 'Deleted HDFC schemes',
      deleted_count: 120,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: /Purge AMC/i })).not.toBeDisabled()
    await userEvent.click(within(dialog).getByRole('button', { name: /Purge AMC/i }))

    await waitFor(() => {
      expect(apiClient.purgeMfSnapshots).toHaveBeenCalledWith({ amc: 'HDFC' })
    })
    expect(await screen.findByText(/Deleted HDFC schemes/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('purges all schemes after typing PURGE', async () => {
    vi.mocked(apiClient.purgeMfSnapshots).mockResolvedValue({
      message: 'Purged everything',
      deleted_count: 1200,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /Everything/i }))
    await userEvent.click(within(dialog).getByRole('button', { name: /Purge all/i }))
    expect(await screen.findByText(/Please type "PURGE" to confirm/i)).toBeInTheDocument()

    setInputValue(within(dialog).getByPlaceholderText('PURGE'), 'PURGE')
    await userEvent.click(within(dialog).getByRole('button', { name: /Purge all/i }))

    await waitFor(() => {
      expect(apiClient.purgeMfSnapshots).toHaveBeenCalledWith({ purge_all: true })
    })
    expect(await screen.findByText(/Purged everything/i)).toBeInTheDocument()
  })

  it('requires an AMC target when purging one AMC', async () => {
    vi.mocked(apiClient.getSyncedAmcs).mockResolvedValue({ amcs: [] } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/No AMCs in the database/i)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: /Purge AMC/i }))
    expect(await screen.findByText(/Please select an AMC to delete/i)).toBeInTheDocument()
  })

  it('cancels purge dialog and surfaces purge API errors', async () => {
    vi.mocked(apiClient.purgeMfSnapshots).mockRejectedValue({
      response: { data: { detail: 'Purge rejected' } },
    })

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /Cancel/i }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    const dialog2 = await screen.findByRole('dialog')
    expect(within(dialog2).getByRole('button', { name: /Purge AMC/i })).not.toBeDisabled()
    await userEvent.click(within(dialog2).getByRole('button', { name: /Purge AMC/i }))
    expect(await screen.findByText('Purge rejected')).toBeInTheDocument()
  })

  it('browses schemes: filters, load more, view/close factsheet', async () => {
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({
      schemes: [mockMfScheme],
      total: 5,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /2\. Browse schemes/i }))
    expect(await screen.findByText('Scheme explorer')).toBeInTheDocument()
    expect(await screen.findByText('HDFC Flexi Cap Fund')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^Large Cap$/i }))
    await waitFor(() => {
      expect(apiClient.searchMfSchemes).toHaveBeenCalledWith('', 50, 0, undefined, 'Large Cap')
    })

    await userEvent.click(screen.getByRole('button', { name: /^SBI$/i }))
    await waitFor(() => {
      expect(apiClient.searchMfSchemes).toHaveBeenCalledWith('', 50, 0, 'SBI', 'Large Cap')
    })

    fireEvent.change(screen.getByPlaceholderText(/Search name, ISIN, or AMC/i), {
      target: { value: 'Flexi' },
    })
    await waitFor(
      () => {
        expect(apiClient.searchMfSchemes).toHaveBeenCalledWith('Flexi', 50, 0, 'SBI', 'Large Cap')
      },
      { timeout: 2000 }
    )

    vi.mocked(apiClient.searchMfSchemes).mockResolvedValueOnce({
      schemes: [{ ...mockMfSchemeMild, isin: 'INFLOADMORE001' }],
      total: 5,
    } as any)
    await userEvent.click(screen.getByRole('button', { name: /Load more/i }))
    await waitFor(() => {
      expect(apiClient.searchMfSchemes).toHaveBeenCalledWith('Flexi', 50, 1, 'SBI', 'Large Cap')
    })

    await userEvent.click(screen.getAllByRole('button', { name: /^View$/i })[0])
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByText('Top holdings')).toBeInTheDocument()
    expect(within(sheet).getByText(/HDFC Bank/i)).toBeInTheDocument()
    await userEvent.click(within(sheet).getByRole('button', { name: /^Close$/i }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  }, 60000)

  it('shows empty explore state and returns to ingest', async () => {
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({ schemes: [], total: 0 } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /2\. Browse schemes/i }))
    expect(await screen.findByText('No schemes found')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Go to Ingest/i }))
    expect(await screen.findByText('Ingestion scope')).toBeInTheDocument()
  })

  it('expands sync history audit panel', async () => {
    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /Sync history/i }))
    expect(await screen.findByText('completed')).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
    expect(screen.getByText('in_progress')).toBeInTheDocument()
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('system')).toBeInTheDocument()
  })

  it('shows never-synced / empty history when no logs', async () => {
    vi.mocked(apiClient.getMfSyncStatus).mockResolvedValue({
      total_schemes: 0,
      latest_portfolio_month: '',
      recent_logs: [],
    } as any)
    vi.mocked(apiClient.getSyncedAmcs).mockResolvedValue({ amcs: [] } as any)
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({ schemes: [], total: 0 } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    expect(screen.getByText(/Never synced/i)).toBeInTheDocument()
    expect(screen.getByText(/No disclosure month/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Sync history/i }))
    expect(await screen.findByText(/No sync runs yet/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    expect(await screen.findByText(/No AMCs in the database/i)).toBeInTheDocument()
  })

  it('handles getSyncedAmcs failure gracefully during MF load', async () => {
    vi.mocked(apiClient.getSyncedAmcs).mockRejectedValue(new Error('amcs down'))

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    // Still renders directory after amcs catch fallback
    expect(screen.getByText('Mutual Fund Scheme Directory')).toBeInTheDocument()
  })

  it('supports scope selection via keyboard', async () => {
    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    const top5 = screen.getByText('Top 5 AMCs').closest('[role="button"]')!
    fireEvent.keyDown(top5, { key: 'Enter' })
    expect(screen.getByRole('button', { name: /Sync Top 5 AMCs/i })).toBeInTheDocument()

    const full = screen.getByText('Full catalogue').closest('[role="button"]')!
    fireEvent.keyDown(full, { key: ' ' })
    expect(screen.getByRole('button', { name: /Sync full catalogue/i })).toBeInTheDocument()
  })

  it('closes snackbar on Alert close', async () => {
    vi.mocked(apiClient.inviteUser).mockResolvedValue({ message: 'Snack me' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')
    setInputValue(screen.getByLabelText(/^Email$/i), 's@test.com')
    const submitInvite = screen.getAllByRole('button', { name: /^Invite$/i })
      .find((btn) => btn.getAttribute('type') === 'submit')!
    await userEvent.click(submitInvite)

    expect(await screen.findByText('Snack me')).toBeInTheDocument()
  })

  it('invites with name derived from email when name is blank', async () => {
    vi.mocked(apiClient.inviteUser).mockResolvedValue({ message: 'Named from email' } as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Invite User')
    setInputValue(screen.getByLabelText(/^Email$/i), 'onlyemail@test.com')
    const submitInvite = screen.getAllByRole('button', { name: /^Invite$/i })
      .find((btn) => btn.getAttribute('type') === 'submit')!
    await userEvent.click(submitInvite)

    await waitFor(() => {
      expect(apiClient.inviteUser).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'onlyemail@test.com', name: 'onlyemail' })
      )
    })
  })

  it('triggers default top10 sync and views mild-risk factsheet', async () => {
    vi.mocked(apiClient.triggerMfSync).mockResolvedValue({ schemes_updated: 12 } as any)
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({
      schemes: [mockMfSchemeMild],
      total: 1,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()

    await userEvent.click(screen.getByRole('button', { name: /Sync Top 10 AMCs/i }))
    await waitFor(() => {
      expect(apiClient.triggerMfSync).toHaveBeenCalledWith({ preset: 'top10' })
    })

    expect(await screen.findByText('Scheme explorer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^View$/i }))
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByText('Top holdings')).toBeInTheDocument()
    expect(within(sheet).getByText(/1\.\s*Reliance/)).toBeInTheDocument()
    expect(within(sheet).getByText('N/A')).toBeInTheDocument()
  }, 60000)

  it('handles MF search/filter API failures without crashing', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(apiClient.searchMfSchemes)
      .mockResolvedValueOnce({ schemes: [mockMfScheme], total: 2 } as any) // fetchMfData
      .mockRejectedValueOnce(new Error('filter down')) // handleSelectFilter
      .mockRejectedValueOnce(new Error('search down')) // loadMfSchemes via debounce

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByRole('button', { name: /2\. Browse schemes/i }))
    expect(await screen.findByText('HDFC Flexi Cap Fund')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^ELSS$/i }))
    await waitFor(() => {
      expect(errSpy).toHaveBeenCalled()
    })
    const afterFilter = errSpy.mock.calls.length

    fireEvent.change(screen.getByPlaceholderText(/Search name, ISIN, or AMC/i), {
      target: { value: 'x' },
    })
    await waitFor(
      () => {
        expect(errSpy.mock.calls.length).toBeGreaterThan(afterFilter)
      },
      { timeout: 2000 }
    )
    errSpy.mockRestore()
  })

  it('tolerates sparse API payloads and default purge/sync messages', async () => {
    vi.mocked(apiClient.getAccessRequests).mockResolvedValue({} as any)
    vi.mocked(apiClient.getAppUsers).mockResolvedValue({} as any)
    vi.mocked(apiClient.getMfSyncStatus).mockResolvedValue({
      total_schemes: 0,
      latest_portfolio_month: '',
      recent_logs: undefined,
    } as any)
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({} as any)
    vi.mocked(apiClient.getSyncedAmcs).mockResolvedValue({} as any)
    vi.mocked(apiClient.triggerMfSync).mockResolvedValue({ schemes_updated: 3 } as any)
    vi.mocked(apiClient.purgeMfSnapshots).mockResolvedValue({ deleted_count: 7 } as any)

    renderWithProviders(<AdminConsole />)
    expect(await screen.findByText('No access requests found')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: /User Accounts/i }))
    expect(await screen.findByText('No user accounts found')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /MF Scheme Directory/i }))
    expect(await screen.findByText('Ingestion scope')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Sync Top 10 AMCs/i }))
    expect(await screen.findByText(/Successfully synced 3/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /1\. Ingest/i }))
    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /Everything/i }))
    setInputValue(within(dialog).getByPlaceholderText('PURGE'), 'PURGE')
    await userEvent.click(within(dialog).getByRole('button', { name: /Purge all/i }))
    expect(await screen.findByText(/Deleted 7 schemes from database/i)).toBeInTheDocument()
  })

  it('renders accounts with missing email and last seen', async () => {
    vi.mocked(apiClient.getAppUsers).mockResolvedValue({
      users: [
        {
          user_id: 'u-no-email',
          email: null,
          status: 'active',
          role: 'user',
          created_at: null,
          last_seen_at: null,
        },
      ],
    } as any)

    renderWithProviders(<AdminConsole />)
    await userEvent.click(await screen.findByRole('tab', { name: /User Accounts/i }))
    expect(await screen.findByText('u-no-email')).toBeInTheDocument()
  })

  it('shows MF explore loading spinner then filtered empty-state copy', async () => {
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({ schemes: [], total: 0 } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByRole('button', { name: /2\. Browse schemes/i }))
    expect(await screen.findByText(/Ingest an AMC scope first/i)).toBeInTheDocument()

    let resolveFilter: (value: any) => void
    vi.mocked(apiClient.searchMfSchemes).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFilter = resolve
        }) as any
    )
    await userEvent.click(screen.getByRole('button', { name: /^Debt$/i }))
    expect(await screen.findByRole('progressbar')).toBeInTheDocument()
    resolveFilter!({ schemes: [], total: 0 })
    expect(await screen.findByText(/Try clearing filters or searching something else/i)).toBeInTheDocument()
  }, 60000)

  it('renders diverse investor profiles and fallback approve messages', async () => {
    vi.mocked(apiClient.getAccessRequests).mockResolvedValue({
      requests: [
        {
          id: 'r-tax',
          email: 'tax@test.com',
          name: 'Tax Pro',
          investor_type: 'tax_pro',
          notes: 'notes',
          status: 'pending',
          created_at: '2026-01-01T00:00:00Z',
          reviewed_at: null,
        },
        {
          id: 'r-corp',
          email: 'corp@test.com',
          name: 'Corp User',
          investor_type: 'corporate',
          notes: '',
          status: 'pending',
          created_at: null,
          reviewed_at: null,
        },
      ],
    } as any)
    vi.mocked(apiClient.approveAccessRequest).mockResolvedValue({ status: 'approved' } as any)
    vi.mocked(apiClient.rejectAccessRequest).mockResolvedValue({} as any)

    renderWithProviders(<AdminConsole />)
    expect(await screen.findByText('CA / Tax Expert')).toBeInTheDocument()
    expect(screen.getByText('Corporate')).toBeInTheDocument()

    const taxRow = screen.getByText('tax@test.com').closest('tr')!
    await userEvent.click(within(taxRow).getByRole('button', { name: /^Invite$/i }))
    expect(await screen.findByText(/Invite email sent to tax@test.com/i)).toBeInTheDocument()

    const corpRow = screen.getByText('corp@test.com').closest('tr')!
    await userEvent.click(within(corpRow).getByTestId('DeleteOutlineIcon').closest('button')!)
    expect(await screen.findByText(/rejected and deleted/i)).toBeInTheDocument()
  })

  it('shows scheme table fallbacks for missing category and TER', async () => {
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({
      schemes: [
        {
          ...mockMfScheme,
          scheme_name: 'Bare Scheme',
          category: '',
          expense_ratio: null,
          risk_level: 'LOW',
          holdings: [],
          sectors: [],
        },
      ],
      total: 1,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByRole('button', { name: /2\. Browse schemes/i }))
    expect(await screen.findByText('Bare Scheme')).toBeInTheDocument()
    expect(screen.getByText('Equity')).toBeInTheDocument()
    expect(screen.getByText(/TER N\/A/i)).toBeInTheDocument()
  })

  it('closes factsheet and purge dialogs via dismiss controls', async () => {
    vi.mocked(apiClient.searchMfSchemes).mockResolvedValue({
      schemes: [mockMfScheme],
      total: 1,
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    await userEvent.click(screen.getByRole('button', { name: /2\. Browse schemes/i }))
    await userEvent.click(await screen.findByRole('button', { name: /^View$/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    await userEvent.click(screen.getByRole('button', { name: /1\. Ingest/i }))
    await userEvent.click(screen.getByRole('button', { name: /Purge data/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('uses default snackbar copy for suspend/delete success', async () => {
    vi.mocked(apiClient.suspendUser).mockResolvedValue({} as any)
    vi.mocked(apiClient.deleteAppUser).mockResolvedValue({} as any)

    renderWithProviders(<AdminConsole />)
    await screen.findByText('Revoke Access')
    setInputValue(screen.getByLabelText(/Email to suspend/i), 'active@test.com')
    await userEvent.click(screen.getByRole('button', { name: /Suspend Access/i }))
    expect(await screen.findByText(/access suspended/i)).toBeInTheDocument()

    await goToUsersTab()
    const row = screen.getByText('active@test.com').closest('tr')!
    await userEvent.click(within(row).getByTestId('DeleteOutlineIcon').closest('button')!)
    const dialog = await screen.findByRole('dialog')
    setInputValue(within(dialog).getByPlaceholderText('active@test.com'), 'active@test.com')
    await userEvent.click(within(dialog).getByRole('button', { name: /Delete Forever/i }))
    expect(await screen.findByText(/Deleted account for active@test.com/i)).toBeInTheDocument()
  })

  it('shows loading spinners for access requests and user accounts', async () => {
    let resolveRequests: (value: any) => void
    let resolveUsers: (value: any) => void
    vi.mocked(apiClient.getAccessRequests).mockImplementation(
      () => new Promise((resolve) => { resolveRequests = resolve }) as any
    )
    vi.mocked(apiClient.getAppUsers).mockImplementation(
      () => new Promise((resolve) => { resolveUsers = resolve }) as any
    )

    renderWithProviders(<AdminConsole />)
    expect(await screen.findByText(/Loading submitted access requests/i)).toBeInTheDocument()
    resolveRequests!(mockRequests)
    expect(await screen.findByText('newuser@test.com')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /User Accounts/i }))
    // Still pending users promise from mount
    expect(screen.getByText(/Loading user accounts/i)).toBeInTheDocument()
    resolveUsers!(mockUsers)
    expect(await screen.findByText('active@test.com')).toBeInTheDocument()
  })

  it('styles last-sync chip for failed and in-progress latest runs', async () => {
    vi.mocked(apiClient.getMfSyncStatus).mockResolvedValue({
      total_schemes: 10,
      latest_portfolio_month: '2026-01',
      recent_logs: [
        {
          id: 9,
          triggered_by: 'ops',
          status: 'failed',
          schemes_updated: 0,
          portfolio_month: '2026-01',
          duration_seconds: 3,
          error_message: 'boom',
          created_at: '2026-02-01T00:00:00Z',
        },
      ],
    } as any)

    const { unmount } = renderWithProviders(<AdminConsole />)
    await goToMfTab()
    expect(screen.getByText(/Last sync: failed/i)).toBeInTheDocument()
    unmount()

    vi.mocked(apiClient.getMfSyncStatus).mockResolvedValue({
      total_schemes: 10,
      latest_portfolio_month: '2026-01',
      recent_logs: [
        {
          id: 10,
          triggered_by: 'ops',
          status: 'in_progress',
          schemes_updated: 1,
          portfolio_month: '2026-01',
          duration_seconds: 1,
          error_message: null,
          created_at: null,
        },
      ],
    } as any)

    renderWithProviders(<AdminConsole />)
    await goToMfTab()
    expect(screen.getByText(/Last sync: in_progress/i)).toBeInTheDocument()
  })

  it('covers refresh loading affordance on access tab', async () => {
    renderWithProviders(<AdminConsole />)
    await screen.findByText('newuser@test.com')

    let resolveRefresh: (value: any) => void
    vi.mocked(apiClient.getAccessRequests).mockImplementation(
      () => new Promise((resolve) => { resolveRefresh = resolve }) as any
    )
    await userEvent.click(screen.getByRole('button', { name: /Refresh Data/i }))
    // Refresh icon swaps to a progress indicator while refreshing
    expect(screen.getAllByRole('progressbar').length).toBeGreaterThan(0)
    resolveRefresh!(mockRequests)
    await waitFor(() => {
      expect(apiClient.getAccessRequests).toHaveBeenCalled()
    })
  })
})
