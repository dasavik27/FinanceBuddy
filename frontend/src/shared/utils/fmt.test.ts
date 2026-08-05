import { describe, it, expect } from 'vitest'
import {
  fmtInr,
  fmtNum,
  fmtPct,
  gainColor,
  gainBg,
  verdictColor,
  verdictBg,
  verdictBorder,
} from './fmt'

describe('fmtInr', () => {
  it('formats a plain amount with Indian digit grouping', () => {
    expect(fmtInr(1234567)).toBe('₹12,34,567')
    expect(fmtInr(500)).toBe('₹500')
    expect(fmtInr(1234.56)).toBe('₹1,234.56')
    expect(fmtInr(12345678.9)).toBe('₹1,23,45,678.90')
  })

  it('formats a compact amount in Lakhs and Crores and standard', () => {
    expect(fmtInr(250000, true)).toBe('₹2.50 L')
    expect(fmtInr(15000000, true)).toBe('₹1.50 Cr')
    expect(fmtInr(5000, true)).toBe('₹5,000')
    expect(fmtInr(99999, true)).toBe('₹99,999')
  })

  it('formats negative amounts with a leading minus sign', () => {
    expect(fmtInr(-5000)).toBe('-₹5,000')
    expect(fmtInr(-250000, true)).toBe('-₹2.50 L')
    expect(fmtInr(-15000000, true)).toBe('-₹1.50 Cr')
    expect(fmtInr(-250)).toBe('-₹250')
  })

  it('formats null/undefined and NaN as ₹0', () => {
    expect(fmtInr(null)).toBe('₹0')
    expect(fmtInr(undefined)).toBe('₹0')
    expect(fmtInr(NaN)).toBe('₹0')
    expect(fmtInr(Infinity)).toBe('₹0')
    expect(fmtInr(-Infinity)).toBe('₹0')
  })
})

describe('fmtPct', () => {
  it('formats percentages with positive sign and custom decimals', () => {
    expect(fmtPct(12.345)).toBe('+12.35%')
    expect(fmtPct(-5.2)).toBe('-5.20%')
    expect(fmtPct(0)).toBe('0.00%')
    expect(fmtPct(12.3456, 3)).toBe('+12.346%')
  })

  it('guards null, undefined, NaN, and Infinity', () => {
    expect(fmtPct(null)).toBe('0.00%')
    expect(fmtPct(undefined)).toBe('0.00%')
    expect(fmtPct(NaN)).toBe('0.00%')
    expect(fmtPct(Infinity)).toBe('0.00%')
  })
})

describe('fmtNum', () => {
  it('formats numbers with specified decimals', () => {
    expect(fmtNum(123.456, 1)).toBe('123.5')
    expect(fmtNum(123.456, 2)).toBe('123.46')
    expect(fmtNum(123, 0)).toBe('123')
  })

  it('guards null, undefined, and non-finite numbers', () => {
    expect(fmtNum(null)).toBe('0')
    expect(fmtNum(undefined)).toBe('0')
    expect(fmtNum(NaN)).toBe('0')
    expect(fmtNum(Infinity)).toBe('0')
  })
})

describe('gainColor and gainBg', () => {
  it('returns emerald colors for positive/zero values and red for negative', () => {
    expect(gainColor(10)).toBe('#059669')
    expect(gainColor(0)).toBe('#059669')
    expect(gainColor(-1)).toBe('#DC2626')

    expect(gainBg(10)).toBe('#ECFDF5')
    expect(gainBg(0)).toBe('#ECFDF5')
    expect(gainBg(-1)).toBe('#FEF2F2')
  })
})

describe('verdict styling helpers', () => {
  it('verdictColor returns proper hex codes', () => {
    expect(verdictColor('Strong')).toBe('#059669')
    expect(verdictColor('Average')).toBe('#D97706')
    expect(verdictColor('Weak')).toBe('#DC2626')
    expect(verdictColor('Other')).toBe('#DC2626')
  })

  it('verdictBg returns proper background hex codes', () => {
    expect(verdictBg('Strong')).toBe('#ECFDF5')
    expect(verdictBg('Average')).toBe('#FFFBEB')
    expect(verdictBg('Poor')).toBe('#FEF2F2')
  })

  it('verdictBorder returns proper border hex codes', () => {
    expect(verdictBorder('Strong')).toBe('#A7F3D0')
    expect(verdictBorder('Average')).toBe('#FDE68A')
    expect(verdictBorder('Underperform')).toBe('#FECACA')
  })
})
