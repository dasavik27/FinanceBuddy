import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import { VerdictChip, CategoryBadge, PlanBadge, RiskPill } from './Badges'

describe('Badges components', () => {
  describe('VerdictChip', () => {
    it('renders verdict text and score', () => {
      renderWithProviders(<VerdictChip verdict="Strong" score={9.2} />)
      expect(screen.getByText(/Strong/)).toBeInTheDocument()
      expect(screen.getByText('9.2')).toBeInTheDocument()
    })

    it('renders with tooltip reason when provided', () => {
      renderWithProviders(<VerdictChip verdict="Average" reason="High expense ratio" />)
      expect(screen.getByText(/Average/)).toBeInTheDocument()
    })

    it('renders Weak verdict with proper icon', () => {
      renderWithProviders(<VerdictChip verdict="Weak" />)
      expect(screen.getByText(/🔴 Weak/)).toBeInTheDocument()
    })
  })

  describe('CategoryBadge', () => {
    it('renders known category and fallback category', () => {
      const { rerender } = renderWithProviders(<CategoryBadge category="Equity" />)
      expect(screen.getByText('Equity')).toBeInTheDocument()

      rerender(<CategoryBadge category="CustomFundType" />)
      expect(screen.getByText('CustomFundType')).toBeInTheDocument()
    })
  })

  describe('PlanBadge', () => {
    it('renders Direct and Regular badges', () => {
      const { rerender } = renderWithProviders(<PlanBadge plan="Direct" />)
      expect(screen.getByText('Direct')).toBeInTheDocument()

      rerender(<PlanBadge plan="Regular" />)
      expect(screen.getByText('Regular')).toBeInTheDocument()
    })
  })

  describe('RiskPill', () => {
    it('renders low risk, moderate, and high risk labels', () => {
      const { rerender } = renderWithProviders(<RiskPill label="Low" />)
      expect(screen.getByText('Risk: Low')).toBeInTheDocument()

      rerender(<RiskPill label="Moderate" />)
      expect(screen.getByText('Risk: Moderate')).toBeInTheDocument()

      rerender(<RiskPill label="Very High" />)
      expect(screen.getByText('Risk: Very High')).toBeInTheDocument()
    })
  })
})
