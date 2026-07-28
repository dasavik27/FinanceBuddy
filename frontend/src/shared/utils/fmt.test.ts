import { describe, it, expect } from 'vitest'
import { fmtInr } from './fmt'

describe('fmtInr', () => {
  it('formats a plain amount with Indian digit grouping', () => {
    expect(fmtInr(1234567)).toBe('₹12,34,567')
  })

  it('formats a compact amount in Lakhs', () => {
    expect(fmtInr(250000, true)).toBe('₹2.50 L')
  })

  it('formats a compact amount in Crores', () => {
    expect(fmtInr(15000000, true)).toBe('₹1.50 Cr')
  })

  it('formats negative amounts with a leading minus sign', () => {
    expect(fmtInr(-5000)).toBe('-₹5,000')
  })

  it('formats null/undefined as ₹0', () => {
    expect(fmtInr(null)).toBe('₹0')
    expect(fmtInr(undefined)).toBe('₹0')
  })
})
