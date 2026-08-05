import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import React from 'react'

import { MetricCard } from './MetricCard'
import { InlineEdit } from './InlineEdit'
import { ErrorBoundary } from './ErrorBoundary'
import { EmptyState, GlassTableContainer, GlassHeader } from './States'
import {
  TabFallback,
  ScoreRing,
  ProgressRow,
  LoadingGrid,
  PremiumPulseLoader,
  TabLoader,
  OverlayLoader,
} from './Loaders'
import { InfoTooltip } from './InfoTooltip'
import { SectionHeader } from './SectionHeader'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'

describe('Shared UI Components', () => {
  describe('MetricCard', () => {
    it('renders label, value, subtext, and info tooltip', () => {
      renderWithProviders(
        <MetricCard
          label="Total Value"
          value="₹1,50,000"
          sub="+12.5% this month"
          accent="success"
          info="Current market value"
          icon={TrendingUpIcon}
        />
      )

      expect(screen.getByText('Total Value')).toBeInTheDocument()
      expect(screen.getByText('₹1,50,000')).toBeInTheDocument()
      expect(screen.getByText('+12.5% this month')).toBeInTheDocument()
    })

    it('renders skeleton loading state', () => {
      const { container } = renderWithProviders(
        <MetricCard label="AUM" value="₹10 Cr" loading={true} />
      )
      expect(screen.getByText('AUM')).toBeInTheDocument()
      expect(screen.queryByText('₹10 Cr')).not.toBeInTheDocument()
      expect(container.querySelector('.MuiSkeleton-root')).toBeInTheDocument()
    })
  })

  describe('InlineEdit', () => {
    it('switches between display mode and edit mode, triggering onSave on Enter or Blur', async () => {
      const onSave = vi.fn()
      renderWithProviders(<InlineEdit value="Initial Name" onSave={onSave} />)

      const display = screen.getByText('Initial Name')
      expect(display).toBeInTheDocument()

      // Click to edit
      await userEvent.click(display)
      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()

      // Type new text and press enter
      await userEvent.clear(input)
      await userEvent.type(input, 'Updated Name{enter}')

      expect(onSave).toHaveBeenCalledWith('Updated Name')
    })

    it('cancels edit on Escape key without saving', async () => {
      const onSave = vi.fn()
      renderWithProviders(<InlineEdit value="Keep Me" onSave={onSave} />)

      await userEvent.click(screen.getByText('Keep Me'))
      const input = screen.getByRole('textbox')
      await userEvent.type(input, ' Change')
      fireEvent.keyDown(input, { key: 'Escape' })

      expect(onSave).not.toHaveBeenCalled()
      expect(screen.getByText('Keep Me')).toBeInTheDocument()
    })

    it('handles numeric inline edit values', async () => {
      const onSave = vi.fn()
      renderWithProviders(<InlineEdit value={100} type="number" onSave={onSave} />)

      await userEvent.click(screen.getByText('100'))
      const input = screen.getByRole('spinbutton')
      await userEvent.clear(input)
      await userEvent.type(input, '250{enter}')

      expect(onSave).toHaveBeenCalledWith(250)
    })
  })

  describe('ErrorBoundary', () => {
    const ProblematicComponent = () => {
      throw new Error('Test Explosion')
    }

    it('catches render error and displays error card with reset button', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      renderWithProviders(
        <ErrorBoundary fallbackMessage="Custom error occurred">
          <ProblematicComponent />
        </ErrorBoundary>
      )

      expect(screen.getByText('Component Rendering Exception')).toBeInTheDocument()
      expect(screen.getByText('Custom error occurred')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /RESET MODULE/i })).toBeInTheDocument()

      consoleSpy.mockRestore()
    })
  })

  describe('States and Glass Containers', () => {
    it('renders EmptyState, GlassTableContainer, and GlassHeader', () => {
      renderWithProviders(
        <div>
          <EmptyState message="No records found" />
          <GlassTableContainer>
            <GlassHeader label="PORTFOLIO HOLDINGS" icon={TrendingUpIcon} />
          </GlassTableContainer>
        </div>
      )

      expect(screen.getByText('No records found')).toBeInTheDocument()
      expect(screen.getByText('PORTFOLIO HOLDINGS')).toBeInTheDocument()
    })
  })

  describe('Loaders and Score Rings', () => {
    it('renders ScoreRing, ProgressRow, LoadingGrid, and Loaders', () => {
      renderWithProviders(
        <div>
          <ScoreRing score={85} />
          <ProgressRow label="Diversification" actual={8} max={10} />
          <LoadingGrid cols={2} rows={2} />
          <PremiumPulseLoader />
          <TabLoader message="Loading institutional feed..." />
          <OverlayLoader message="Syncing..." />
          <TabFallback />
        </div>
      )

      expect(screen.getByText('85')).toBeInTheDocument()
      expect(screen.getByText('Diversification')).toBeInTheDocument()
      expect(screen.getByText('8/10')).toBeInTheDocument()
      expect(screen.getByText(/Loading institutional feed.../)).toBeInTheDocument()
      expect(screen.getByText(/Syncing.../)).toBeInTheDocument()
    })
  })

  describe('InfoTooltip and SectionHeader', () => {
    it('renders InfoTooltip icon and SectionHeader with title and action', () => {
      renderWithProviders(
        <div>
          <InfoTooltip title="More details" />
          <SectionHeader
            title="Portfolio Overview"
            subtitle="Analyze your asset distribution"
            action={<button>Export</button>}
          />
        </div>
      )

      expect(screen.getByText('Portfolio Overview')).toBeInTheDocument()
      expect(screen.getByText('Analyze your asset distribution')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()
    })
  })
})
