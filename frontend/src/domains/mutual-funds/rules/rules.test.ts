import { describe, it, expect } from 'vitest'
import { getTaxProfile, INDIAN_TAX_SLABS } from './fundTaxRules'
import { calculateDrawdown, getHealthSignal, CATEGORY_INSIGHTS, COLORS } from './tabCommon'

describe('Mutual Funds Rules & Calculations', () => {
  describe('fundTaxRules', () => {
    it('returns ELSS tax profile with lock-in characteristics', () => {
      const profile = getTaxProfile('Quant ELSS Tax Saver Fund')
      expect(profile.stcgRate).toBe(0)
      expect(profile.ltcgRate).toBe(INDIAN_TAX_SLABS.equity_ltcg)
      expect(profile.stcgVal).toContain('Lock-in')
      expect(profile.note).toContain('80C')
    })

    it('returns Debt slab tax profile for debt/liquid/gilt funds', () => {
      const debtProfile = getTaxProfile('ICICI Prudential Liquid Fund')
      expect(debtProfile.stcgRate).toBe(INDIAN_TAX_SLABS.debt_proxy_slab)
      expect(debtProfile.ltcgRate).toBe(INDIAN_TAX_SLABS.debt_proxy_slab)
      expect(debtProfile.stcgVal).toBe('Slab Rate')
      expect(debtProfile.note).toContain('Post Apr 2023')

      const giltProfile = getTaxProfile('SBI Gilt Fund')
      expect(giltProfile.stcgVal).toBe('Slab Rate')
    })

    it('returns Equity tax profile for regular equity/flexi funds', () => {
      const equityProfile = getTaxProfile('Parag Parikh Flexi Cap Fund')
      expect(equityProfile.stcgRate).toBe(INDIAN_TAX_SLABS.equity_stcg)
      expect(equityProfile.ltcgRate).toBe(INDIAN_TAX_SLABS.equity_ltcg)
      expect(equityProfile.stcgLabel).toBe('STCG (<1Y)')
      expect(equityProfile.ltcgLabel).toBe('LTCG (>1Y)')
    })
  })

  describe('tabCommon', () => {
    it('calculates drawdown series correctly from peak', () => {
      expect(calculateDrawdown([])).toEqual([])
      expect(calculateDrawdown(null as any)).toEqual([])

      const prices = [100, 120, 90, 150, 135]
      const drawdowns = calculateDrawdown(prices)

      expect(drawdowns[0]).toBe(0) // Peak is 100
      expect(drawdowns[1]).toBe(0) // New peak 120
      expect(drawdowns[2]).toBeCloseTo(((90 / 120) - 1) * 100) // -25%
      expect(drawdowns[3]).toBe(0) // New peak 150
      expect(drawdowns[4]).toBeCloseTo(((135 / 150) - 1) * 100) // -10%

      // peak === 0 branch
      expect(calculateDrawdown([0, 0, -10])[0]).toBe(0)
    })

    it('returns health signals based on gain thresholds', () => {
      expect(getHealthSignal(20).label).toBe('STRONG')
      expect(getHealthSignal(10).label).toBe('WATCH')
      expect(getHealthSignal(2).label).toBe('NEUTRAL')
      expect(getHealthSignal(-5).label).toBe('REVIEW')
    })

    it('has category insights and color palette defined', () => {
      expect(COLORS.length).toBeGreaterThanOrEqual(5)
      expect(CATEGORY_INSIGHTS['Large Cap'].timeline).toBe('3 - 5 Years')
      expect(CATEGORY_INSIGHTS['Small Cap'].focus).toBe('High Alpha Compounding')
    })
  })
})
