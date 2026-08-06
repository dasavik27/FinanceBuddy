import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import React from 'react'

import * as UI from './index'
import {
  MetricCard,
  InlineEdit,
  ErrorBoundary,
  EmptyState,
  GlassTableContainer,
  GlassHeader,
  TabFallback,
  ScoreRing,
  ProgressRow,
  LoadingGrid,
  PremiumPulseLoader,
  TabLoader,
  OverlayLoader,
  InfoTooltip,
  SectionHeader,
  PeriodSelector,
} from './index'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'

describe('Shared UI Components', () => {
  it('exports all components from index.ts', () => {
    expect(UI.MetricCard).toBeDefined()
    expect(UI.PlanBadge).toBeDefined()
    expect(UI.ScoreRing).toBeDefined()
    expect(UI.PeriodSelector).toBeDefined()
  })

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

    it('renders different accents and subtext styles', () => {
      renderWithProviders(
        <div>
          <MetricCard label="Danger" value="10" sub="Low" accent="danger" />
          <MetricCard label="Warn" value="20" sub="Med" accent="warn" />
          <MetricCard label="Info" value="30" sub="High" accent="info" />
          <MetricCard label="None" value="40" sub="Neutral" accent="none" />
          <MetricCard label="NoSub" value="50" />
        </div>
      )
      expect(screen.getByText('Danger')).toBeInTheDocument()
      expect(screen.getByText('Warn')).toBeInTheDocument()
      expect(screen.getByText('Info')).toBeInTheDocument()
      expect(screen.getByText('None')).toBeInTheDocument()
      expect(screen.getByText('NoSub')).toBeInTheDocument()
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
    const ProblematicComponent = ({ shouldThrow }: { shouldThrow: boolean }) => {
      if (shouldThrow) {
        throw new Error('Test Explosion')
      }
      return <div>Normal Content</div>
    }

    it('catches render error and displays error card with reset button', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      renderWithProviders(
        <ErrorBoundary fallbackMessage="Custom error occurred">
          <ProblematicComponent shouldThrow={true} />
        </ErrorBoundary>
      )

      expect(screen.getByText('Component Rendering Exception')).toBeInTheDocument()
      expect(screen.getByText('Custom error occurred')).toBeInTheDocument()
      const resetBtn = screen.getByRole('button', { name: /RESET MODULE/i })
      expect(resetBtn).toBeInTheDocument()

      // Trigger reset
      await userEvent.click(resetBtn)

      consoleSpy.mockRestore()
    })

    it('displays default error message when fallbackMessage is omitted', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      renderWithProviders(
        <ErrorBoundary>
          <ProblematicComponent shouldThrow={true} />
        </ErrorBoundary>
      )

      expect(screen.getByText('Test Explosion')).toBeInTheDocument()
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
    it('renders ScoreRing with high, medium, and low scores', () => {
      renderWithProviders(
        <div>
          <ScoreRing score={85} />
          <ScoreRing score={55} />
          <ScoreRing score={20} />
        </div>
      )
      expect(screen.getByText('85')).toBeInTheDocument()
      expect(screen.getByText('55')).toBeInTheDocument()
      expect(screen.getByText('20')).toBeInTheDocument()
    })

    it('renders ProgressRow with various percentages and max=0', () => {
      renderWithProviders(
        <div>
          <ProgressRow label="High" actual={9} max={10} />
          <ProgressRow label="Medium" actual={5} max={10} />
          <ProgressRow label="Low" actual={2} max={10} />
          <ProgressRow label="ZeroMax" actual={0} max={0} />
        </div>
      )
      expect(screen.getByText('High')).toBeInTheDocument()
      expect(screen.getByText('Medium')).toBeInTheDocument()
      expect(screen.getByText('Low')).toBeInTheDocument()
      expect(screen.getByText('ZeroMax')).toBeInTheDocument()
    })

    it('renders LoadingGrid, PremiumPulseLoader, TabLoader, and OverlayLoader', () => {
      renderWithProviders(
        <div>
          <LoadingGrid cols={2} rows={2} />
          <PremiumPulseLoader />
          <TabLoader message="Loading institutional feed..." />
          <OverlayLoader message="Syncing..." />
          <TabFallback />
        </div>
      )

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

  describe('PeriodSelector', () => {
    it('renders options, highlights selected value, and calls onChange on click', async () => {
      const onChange = vi.fn()
      renderWithProviders(
        <PeriodSelector
          options={['1M', '3M', '6M', '1Y', 'ALL']}
          value="1Y"
          onChange={onChange}
        />
      )

      expect(screen.getByText('1M')).toBeInTheDocument()
      expect(screen.getByText('1Y')).toBeInTheDocument()

      await userEvent.click(screen.getByText('3M'))
      expect(onChange).toHaveBeenCalledWith('3M')
    })
  })
})
