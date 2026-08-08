import { describe, it, expect, vi } from 'vitest'
import {
  invalidateMutualFundQueries,
  invalidateEquityQueries,
  invalidateTaxQueries,
  invalidateModuleQueries,
} from './invalidateSessionQueries'

function mockQc() {
  return {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
  } as any
}

describe('invalidateSessionQueries', () => {
  it('invalidates mutual fund root keys via predicate', async () => {
    const qc = mockQc()
    await invalidateMutualFundQueries(qc)
    expect(qc.invalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ predicate: expect.any(Function) }),
    )
    const pred = qc.invalidateQueries.mock.calls[0][0].predicate
    expect(pred({ queryKey: ['holdings', 'sid'] })).toBe(true)
    expect(pred({ queryKey: ['insights', 'sid'] })).toBe(true)
    expect(pred({ queryKey: ['equity', 'holdings'] })).toBe(false)
  })

  it('invalidates equity namespace', async () => {
    const qc = mockQc()
    await invalidateEquityQueries(qc)
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['equity'] })
  })

  it('invalidates tax-expert dashboard keys', async () => {
    const qc = mockQc()
    await invalidateTaxQueries(qc)
    const keys = qc.invalidateQueries.mock.calls.map((c: any[]) => c[0].queryKey[0])
    expect(keys).toContain('tax-expert-summary')
    expect(keys).toContain('tax-expert-income')
    expect(keys).not.toContain('tax-summary')
  })

  it('routes module names to the right invalidator', async () => {
    const qc = mockQc()
    await invalidateModuleQueries(qc, 'indian_stocks')
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['equity'] })
    qc.invalidateQueries.mockClear()
    await invalidateModuleQueries(qc, 'budget')
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['budget'] })
  })
})
