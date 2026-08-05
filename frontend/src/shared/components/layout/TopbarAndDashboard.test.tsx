import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import { Topbar } from './Topbar'
import Dashboard from './Dashboard'
import { useAppStore } from '../../store/appStore'
import { apiClient } from '../../api/client'

vi.mock('../../api/client', () => ({
  apiClient: {
    syncEquity: vi.fn().mockResolvedValue({}),
    syncPortfolio: vi.fn().mockResolvedValue({}),
  },
}))

// Stub every lazy-loaded domain so the Dashboard router tests work in jsdom
vi.mock('../../../domains/mutual-funds/components/MutualFundsDashboard', () => ({
  default: () => <div>MF Dashboard</div>,
}))
vi.mock('../../../domains/equity/components/IndianStocksDashboard', () => ({
  default: () => <div>Equity Dashboard</div>,
}))
vi.mock('../../../domains/tax-expert/components/TaxExpertDashboard', () => ({
  default: () => <div>Tax Dashboard</div>,
}))
vi.mock('../../../domains/budget/components/BudgetDashboard', () => ({
  default: () => <div>Budget Dashboard</div>,
}))
vi.mock('../dashboard/AccountsDashboard', () => ({
  default: () => <div>Accounts Dashboard</div>,
}))
vi.mock('../dashboard/DashboardHub', () => ({
  default: () => <div>Dashboard Hub</div>,
}))
vi.mock('../admin/AdminConsole', () => ({
  default: () => <div>Admin Console</div>,
}))
vi.mock('../ProfilePage', () => ({
  default: () => <div>Profile Page</div>,
}))

function setUser(overrides = {}) {
  act(() => {
    useAppStore.getState().setIdentity({
      userId: 'u-1',
      email: 'test@test.com',
      displayName: 'Test User',
      pan: 'ABCDE1234F',
      status: 'active',
      role: 'user',
      ...overrides,
    })
  })
}

describe('Topbar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setUser()
  })

  it('renders avatar initials from displayName ("Test User" → "TE")', () => {
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />)
    // initials appear twice: avatar chip + menu header
    const all = screen.getAllByText('TE')
    expect(all.length).toBeGreaterThan(0)
  })

  it('shows WarningAmberIcon chip when isPartial is true', () => {
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={true} />)
    expect(screen.getByTestId('WarningAmberIcon')).toBeInTheDocument()
  })

  it('does NOT show WarningAmberIcon when isPartial is false', () => {
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />)
    expect(screen.queryByTestId('WarningAmberIcon')).not.toBeInTheDocument()
  })

  it('calls onMenuClick when the hamburger IconButton is clicked', async () => {
    const onMenuClick = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Topbar onMenuClick={onMenuClick} isPartial={false} />)
    // The hamburger is the first button in the toolbar
    const btns = screen.getAllByRole('button')
    await user.click(btns[0])
    expect(onMenuClick).toHaveBeenCalled()
  })

  it('opens profile menu showing Profile and Sign Out items', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />)
    // The avatar Box is not a button, it's a clickable Box — find via text
    const accountLabel = screen.getByText('Test User')
    await user.click(accountLabel)
    expect(await screen.findByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('Sign Out')).toBeInTheDocument()
    expect(screen.getByText('Data vault')).toBeInTheDocument()
  })

  it('shows Admin Console menu item for admin role', async () => {
    setUser({ role: 'admin', displayName: 'Admin User' })
    const user = userEvent.setup()
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />)
    const accountLabel = screen.getByText('Admin User')
    await user.click(accountLabel)
    expect(await screen.findByText('Admin Console')).toBeInTheDocument()
  })

  it('does NOT show Admin Console menu item for user role', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />)
    const accountLabel = screen.getByText('Test User')
    await user.click(accountLabel)
    await screen.findByText('Profile')
    expect(screen.queryByText('Admin Console')).not.toBeInTheDocument()
  })

  it('falls back to email initials when no displayName', () => {
    act(() => {
      useAppStore.setState({ userId: 'u-2', email: 'hello@test.com', displayName: null, pan: null })
    })
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />)
    expect(screen.getAllByText('HE').length).toBeGreaterThan(0)
  })

  it('renders sync/refresh widget on /equity route', () => {
    act(() => {
      useAppStore.setState({ equitySessionId: 'eq-1' })
    })
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />, {
      initialEntries: ['/equity/holdings'],
    })
    expect(screen.getByText('LIVE EQUITY PRICES')).toBeInTheDocument()
    expect(screen.getByTestId('SyncIcon')).toBeInTheDocument()
  })

  it('renders sync/refresh widget on /mutual-funds route', () => {
    act(() => {
      useAppStore.setState({ mfSessionId: 'mf-1' })
    })
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />, {
      initialEntries: ['/mutual-funds/holdings'],
    })
    expect(screen.getByText('AMFI NAV STATUS')).toBeInTheDocument()
  })

  it('does not render sync widget on non-equity/MF routes', () => {
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />, {
      initialEntries: ['/dashboard'],
    })
    expect(screen.queryByTestId('SyncIcon')).not.toBeInTheDocument()
  })

  it('getSyncedText: less than 1 minute shows "Synced at HH:MM"', () => {
    act(() => {
      useAppStore.setState({ lastSynced: Date.now() - 30000, equitySessionId: 'eq-1' })
    })
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />, {
      initialEntries: ['/equity'],
    })
    expect(screen.getByText(/Synced at/)).toBeInTheDocument()
  })

  it('getSyncedText: more than 1 hour shows Nh ago', () => {
    act(() => {
      useAppStore.setState({ lastSynced: Date.now() - 2 * 60 * 60 * 1000, equitySessionId: 'eq-1' })
    })
    renderWithProviders(<Topbar onMenuClick={vi.fn()} isPartial={false} />, {
      initialEntries: ['/equity'],
    })
    expect(screen.getByText(/2h ago/)).toBeInTheDocument()
  })
})

describe('layout/Dashboard routing', () => {
  beforeEach(() => {
    act(() => {
      useAppStore.getState().clearIdentity()
    })
  })

  it('renders DashboardHub at /dashboard', async () => {
    renderWithProviders(<Dashboard />, { initialEntries: ['/dashboard'] })
    expect(await screen.findByText('Dashboard Hub')).toBeInTheDocument()
  })

  it('redirects unknown path to /dashboard', async () => {
    renderWithProviders(<Dashboard />, { initialEntries: ['/unknown-xyz'] })
    expect(await screen.findByText('Dashboard Hub')).toBeInTheDocument()
  })

  it('renders MutualFundsDashboard at /mutual-funds', async () => {
    renderWithProviders(<Dashboard />, { initialEntries: ['/mutual-funds'] })
    expect(await screen.findByText('MF Dashboard')).toBeInTheDocument()
  })

  it('AdminOnly redirects non-admin to /dashboard', async () => {
    act(() => {
      useAppStore.getState().setIdentity({ userId: 'u-user', role: 'user' })
    })
    renderWithProviders(<Dashboard />, { initialEntries: ['/admin'] })
    expect(await screen.findByText('Dashboard Hub')).toBeInTheDocument()
  })

  it('AdminOnly renders AdminConsole for admin role', async () => {
    act(() => {
      useAppStore.getState().setIdentity({ userId: 'u-admin', role: 'admin' })
    })
    renderWithProviders(<Dashboard />, { initialEntries: ['/admin'] })
    expect(await screen.findByText('Admin Console')).toBeInTheDocument()
  })

  it('legacy /dashboard/mutual-funds redirects to /mutual-funds', async () => {
    renderWithProviders(<Dashboard />, { initialEntries: ['/dashboard/mutual-funds'] })
    expect(await screen.findByText('MF Dashboard')).toBeInTheDocument()
  })

  it('legacy flat /holdings redirects to /mutual-funds/holdings', async () => {
    renderWithProviders(<Dashboard />, { initialEntries: ['/holdings'] })
    expect(await screen.findByText('MF Dashboard')).toBeInTheDocument()
  })
})
