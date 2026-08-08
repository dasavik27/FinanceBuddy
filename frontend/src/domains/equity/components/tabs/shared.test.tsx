import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import { renderWithProviders } from '../../../../test/utils'
import { EquityTabError, EquityTabSkeleton, IconPanel, CHART_COLORS, GLASS_PAPER, HEADER_CELL } from './shared'

describe('equity tab shared primitives', () => {
  describe('EquityTabError', () => {
    it('shows generic message for unknown errors', () => {
      renderWithProviders(<EquityTabError error={new Error('boom')} label="holdings" />)
      expect(screen.getByText('Could not load holdings. Please try again.')).toBeInTheDocument()
    })

    it('shows sign-in message for 401', () => {
      renderWithProviders(
        <EquityTabError error={{ response: { status: 401 } }} label="performance" />,
      )
      expect(screen.getByText('Your session has ended. Sign in again to continue.')).toBeInTheDocument()
    })

    it('shows re-upload guidance for 404 as info severity', () => {
      renderWithProviders(
        <EquityTabError error={{ response: { status: 404 } }} label="allocation" />,
      )
      expect(
        screen.getByText(
          'This portfolio is no longer loaded on the server. Upload your holdings again to continue.',
        ),
      ).toBeInTheDocument()
      expect(screen.getByRole('alert')).toHaveClass('MuiAlert-standardInfo')
    })

    it('shows retry message for 503', () => {
      renderWithProviders(
        <EquityTabError error={{ response: { status: 503 } }} label="insights" />,
      )
      expect(
        screen.getByText('Could not verify access to this portfolio. Please retry.'),
      ).toBeInTheDocument()
    })
  })

  describe('EquityTabSkeleton', () => {
    it('renders default skeleton rows', () => {
      const { container } = renderWithProviders(<EquityTabSkeleton />)
      expect(container.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThanOrEqual(6)
    })

    it('respects custom row count', () => {
      const { container } = renderWithProviders(<EquityTabSkeleton rows={3} />)
      // 1 text skeleton + 3 rectangular rows
      expect(container.querySelectorAll('.MuiSkeleton-root').length).toBe(4)
    })
  })

  describe('IconPanel', () => {
    it('renders title, children, and dense sizing', () => {
      renderWithProviders(
        <IconPanel title="Top Movers" icon={TrendingUpIcon} color="#6366F1" dense>
          <span>panel body</span>
        </IconPanel>,
      )
      expect(screen.getByText('Top Movers')).toBeInTheDocument()
      expect(screen.getByText('panel body')).toBeInTheDocument()
    })

    it('renders non-dense variant', () => {
      renderWithProviders(
        <IconPanel title="Sector Mix" icon={TrendingUpIcon} color="#10B981">
          <span>sector body</span>
        </IconPanel>,
      )
      expect(screen.getByText('Sector Mix')).toBeInTheDocument()
      expect(screen.getByText('sector body')).toBeInTheDocument()
    })
  })

  it('exports chart palette and style constants', () => {
    expect(CHART_COLORS.length).toBeGreaterThanOrEqual(8)
    expect(GLASS_PAPER).toBeTruthy()
    expect(HEADER_CELL).toBeTruthy()
  })
})
