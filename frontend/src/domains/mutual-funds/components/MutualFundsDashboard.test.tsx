import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders } from '../../../test/utils'
import MutualFundsDashboard from './MutualFundsDashboard'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getHistory: vi.fn().mockResolvedValue({ history: [] }),
  },
}))

// Avoid lazy-loading real tab trees (slow / flaky under jsdom)
vi.mock('./OverviewTab', () => ({ default: () => <div>Overview stub</div> }))
vi.mock('./HoldingsTab', () => ({ default: () => <div>Holdings stub</div> }))
vi.mock('./PerformanceTab', () => ({ default: () => <div>Performance stub</div> }))
vi.mock('./CompareTab', () => ({ default: () => <div>Compare stub</div> }))
vi.mock('./InsightsTab', () => ({ default: () => <div>Insights stub</div> }))
vi.mock('./JourneyTab', () => ({ default: () => <div>Journey stub</div> }))
vi.mock('../../../shared/components/dashboard/UploadHistory', () => ({
  default: () => <div>History stub</div>,
}))
vi.mock('./MFUploadPanel', () => ({
  default: () => <div>Upload CAS PDF</div>,
}))

function renderDashboard(initialEntries: string[]) {
  return renderWithProviders(
    <Routes>
      <Route path="/mutual-funds/*" element={<MutualFundsDashboard />} />
    </Routes>,
    { initialEntries },
  )
}

describe('MutualFundsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders MFUploadPanel when no session is active', () => {
    useAppStore.setState({ mfSessionId: null, activeModule: 'mutual_funds' })
    renderDashboard(['/mutual-funds/overview'])

    expect(screen.getByText(/Upload CAS PDF/i)).toBeInTheDocument()
  })

  it('renders tabs navigation when session is active', async () => {
    useAppStore.setState({ mfSessionId: 'sid-mf-123', activeModule: 'mutual_funds' })
    renderDashboard(['/mutual-funds/overview'])

    expect(screen.getByText('MUTUAL FUNDS')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Holdings' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Performance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Compare' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Wealth Journey' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Insights & Rebalance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Statement History' })).toBeInTheDocument()
    expect(await screen.findByText('Overview stub')).toBeInTheDocument()
  })

  it('navigates between tabs via handleTabChange', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'sid-mf-123', activeModule: 'mutual_funds' })
    renderDashboard(['/mutual-funds/overview'])

    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')

    await user.click(screen.getByRole('tab', { name: 'Holdings' }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Holdings' })).toHaveAttribute('aria-selected', 'true')
    })
    expect(await screen.findByText('Holdings stub')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Performance' }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Performance' })).toHaveAttribute('aria-selected', 'true')
    })
    expect(await screen.findByText('Performance stub')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Wealth Journey' }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Wealth Journey' })).toHaveAttribute('aria-selected', 'true')
    })

    expect(useAppStore.getState().activeModule).toBe('mutual_funds')
  })

  it('defaults unknown tab path to overview', () => {
    useAppStore.setState({ mfSessionId: 'sid-mf-123', activeModule: 'mutual_funds' })
    renderDashboard(['/mutual-funds/not-a-real-tab'])

    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
  })

  it('navigates through compare, insights, and history tabs', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'sid-mf-123', activeModule: 'mutual_funds' })
    renderDashboard(['/mutual-funds/overview'])

    await user.click(screen.getByRole('tab', { name: 'Compare' }))
    expect(await screen.findByText('Compare stub')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Insights & Rebalance' }))
    expect(await screen.findByText('Insights stub')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Statement History' }))
    expect(await screen.findByText('History stub')).toBeInTheDocument()
  })

  it('redirects index route to overview', async () => {
    useAppStore.setState({ mfSessionId: 'sid-mf-123', activeModule: 'mutual_funds' })
    renderDashboard(['/mutual-funds'])
    expect(await screen.findByText('Overview stub')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
  })
})