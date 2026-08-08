import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders, resetAppStore } from '../../../test/utils'
import { useAppStore } from '../../../shared/store/appStore'
import IndianStocksDashboard from './IndianStocksDashboard'

vi.mock('./EquityDashboard', () => ({
  default: ({ hasSession }: { hasSession: boolean }) => (
    <div data-testid="equity-dashboard">{hasSession ? 'with-session' : 'no-session'}</div>
  ),
}))

vi.mock('./EquityUploadPanel', () => ({
  default: () => <div data-testid="equity-upload">upload</div>,
}))

describe('IndianStocksDashboard', () => {
  beforeEach(() => {
    resetAppStore()
    vi.clearAllMocks()
  })

  it('sets active module to indian_stocks and renders dashboard without session', () => {
    renderWithProviders(<IndianStocksDashboard />)
    expect(screen.getByTestId('equity-dashboard')).toHaveTextContent('no-session')
    expect(useAppStore.getState().activeModule).toBe('indian_stocks')
  })

  it('passes hasSession when equity session exists', () => {
    useAppStore.setState({ equitySessionId: 'eq-1' })
    renderWithProviders(<IndianStocksDashboard />)
    expect(screen.getByTestId('equity-dashboard')).toHaveTextContent('with-session')
  })
})
