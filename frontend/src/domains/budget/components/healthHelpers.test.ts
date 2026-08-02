/**
 * Equivalence check for the helpers hoisted out of BudgetHealth503020Card.
 *
 * They were rebuilt on every render (three closures plus, for the status UI, three
 * fresh objects each holding a fresh React element). Moving them to module scope is
 * only safe if they return exactly what the originals did for every input, including
 * the boundaries - the old code was a chain of `>=` comparisons and an off-by-one at
 * 45, 60, 80 or 50, 70, 85 would silently recolour the score.
 */
import { describe, it, expect } from 'vitest'

// ── The originals, copied verbatim from the pre-refactor component ──────────────
const oldGetScoreColor = (score: number) => {
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#38bdf8'
  if (score >= 45) return '#f59e0b'
  return '#ef4444'
}

const oldGetScoreBadge = (score: number) => {
  if (score >= 85) return { label: '🌟 Golden Balance', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.3)' }
  if (score >= 70) return { label: '🟢 Healthy Budget', color: '#34d399', bg: 'rgba(52, 211, 153, 0.15)', border: 'rgba(52, 211, 153, 0.3)' }
  if (score >= 50) return { label: '🟡 Discretionary Creep', color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.15)', border: 'rgba(251, 191, 36, 0.3)' }
  return { label: '🔴 Overspending / Needs Heavy', color: '#f87171', bg: 'rgba(248, 113, 113, 0.15)', border: 'rgba(248, 113, 113, 0.3)' }
}

const oldGetBucketStatusUI = (status: string, isInvestments = false) => {
  if (status === 'optimal') {
    return { label: isInvestments ? 'Target Achieved' : 'Within Limit', color: '#34d399', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.3)' }
  }
  if (status === 'warning') {
    return { label: isInvestments ? 'Moderate Saving' : 'Near Limit', color: '#fbbf24', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.3)' }
  }
  return { label: isInvestments ? 'Under-saving' : 'Over Target', color: '#f87171', bg: 'rgba(239, 68, 68, 0.12)', border: 'rgba(239, 68, 68, 0.3)' }
}

// ── The replacements, mirroring the module-scope versions ──────────────────────
const SCORE_COLORS: [number, string][] = [[80, '#10b981'], [60, '#38bdf8'], [45, '#f59e0b']]
function newGetScoreColor(score: number): string {
  for (const [floor, color] of SCORE_COLORS) if (score >= floor) return color
  return '#ef4444'
}

const CRITICAL_BADGE = { label: '🔴 Overspending / Needs Heavy', color: '#f87171', bg: 'rgba(248, 113, 113, 0.15)', border: 'rgba(248, 113, 113, 0.3)' }
const SCORE_BADGES = [
  { min: 85, badge: { label: '🌟 Golden Balance', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.3)' } },
  { min: 70, badge: { label: '🟢 Healthy Budget', color: '#34d399', bg: 'rgba(52, 211, 153, 0.15)', border: 'rgba(52, 211, 153, 0.3)' } },
  { min: 50, badge: { label: '🟡 Discretionary Creep', color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.15)', border: 'rgba(251, 191, 36, 0.3)' } },
]
function newGetScoreBadge(score: number) {
  return SCORE_BADGES.find(b => score >= b.min)?.badge ?? CRITICAL_BADGE
}

const BUCKET_STATUS_UI = {
  optimal:  { color: '#34d399', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.3)', label: 'Within Limit',  investmentsLabel: 'Target Achieved' },
  warning:  { color: '#fbbf24', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.3)', label: 'Near Limit',    investmentsLabel: 'Moderate Saving' },
  critical: { color: '#f87171', bg: 'rgba(239, 68, 68, 0.12)',  border: 'rgba(239, 68, 68, 0.3)',  label: 'Over Target',   investmentsLabel: 'Under-saving' },
} as const
function newGetBucketStatusUI(status: string, isInvestments = false) {
  const ui = BUCKET_STATUS_UI[status as keyof typeof BUCKET_STATUS_UI] ?? BUCKET_STATUS_UI.critical
  const { investmentsLabel, ...rest } = ui
  return { ...rest, label: isInvestments ? investmentsLabel : ui.label }
}

// Every integer across the range, plus the exact thresholds and out-of-range values.
const SCORES = [
  ...Array.from({ length: 121 }, (_, i) => i - 10),
  44.9, 45, 45.1, 49.9, 50, 50.1, 59.9, 60, 60.1,
  69.9, 70, 70.1, 79.9, 80, 80.1, 84.9, 85, 85.1,
  -1, 0, 100, 1000, NaN,
]

describe('getScoreColor', () => {
  it.each(SCORES)('matches the original at %p', (score) => {
    expect(newGetScoreColor(score)).toBe(oldGetScoreColor(score))
  })
})

describe('getScoreBadge', () => {
  it.each(SCORES)('matches the original at %p', (score) => {
    expect(newGetScoreBadge(score)).toEqual(oldGetScoreBadge(score))
  })

  it('never returns undefined - NaN >= -Infinity is false, so a sentinel band would', () => {
    expect(newGetScoreBadge(NaN)).toBeDefined()
    expect(newGetScoreBadge(-Infinity)).toBeDefined()
  })
})

describe('getBucketStatusUI', () => {
  const statuses = ['optimal', 'warning', 'critical', 'unexpected', '']

  it.each(statuses.flatMap(s => [[s, false], [s, true]] as [string, boolean][]))(
    'matches the original for (%s, isInvestments=%s)', (status, isInv) => {
      const got = newGetBucketStatusUI(status, isInv)
      const want = oldGetBucketStatusUI(status, isInv)
      expect(got.label).toBe(want.label)
      expect(got.color).toBe(want.color)
      expect(got.bg).toBe(want.bg)
      expect(got.border).toBe(want.border)
    },
  )

  it('treats an unknown status as critical, as the original fall-through did', () => {
    expect(newGetBucketStatusUI('nonsense').label).toBe('Over Target')
  })

  it('does not leak the internal investmentsLabel key into the returned object', () => {
    expect(newGetBucketStatusUI('optimal')).not.toHaveProperty('investmentsLabel')
  })
})
