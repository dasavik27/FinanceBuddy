/**
 * Guards the category donut against the long tail.
 *
 * The chart was fed every category. With rules-based categorisation 20-40 is normal,
 * and at that size `paddingAngle={3}` per slice spends 60-120 of the available 360
 * degrees on gaps (past ~40 slices the padding exceeds the whole circle and Recharts
 * draws overlapping arcs), while a 10-colour palette wraps so slice 11 is the same
 * colour as slice 1.
 *
 * Mirrors the `donutData` memo and the list's colour rule in BudgetDashboard.tsx.
 */
import { describe, it, expect } from 'vitest'

const CATEGORY_COLORS = [
  '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#3b82f6', '#f97316',
]
const DONUT_SLICES = CATEGORY_COLORS.length
const OTHER_COLOR = '#64748b'

type Cat = { category: string; amount: number; isOther?: boolean }

/** Array.prototype.at is above this project's lib target. */
const last = <T,>(a: T[]): T => a[a.length - 1]

function donutData(processed: Cat[]): Cat[] {
  if (processed.length <= DONUT_SLICES) return processed
  const head = processed.slice(0, DONUT_SLICES - 1)
  const tail = processed.slice(DONUT_SLICES - 1)
  return [
    ...head,
    {
      category: `Other (${tail.length})`,
      amount: tail.reduce((s, c) => s + (c.amount || 0), 0),
      isOther: true,
    },
  ]
}

const sliceColor = (entry: Cat, i: number) =>
  entry.isOther ? OTHER_COLOR : CATEGORY_COLORS[i % CATEGORY_COLORS.length]

const paddingAngle = (n: number) => (n > 6 ? 1 : 3)

const cats = (n: number): Cat[] =>
  Array.from({ length: n }, (_, i) => ({ category: `Cat ${i}`, amount: (n - i) * 100 }))

describe('donut slice capping', () => {
  it.each([0, 1, 5, 10])('passes %i categories through untouched', (n) => {
    expect(donutData(cats(n))).toHaveLength(n)
  })

  it.each([11, 25, 40, 120])('caps %i categories at the palette size', (n) => {
    expect(donutData(cats(n))).toHaveLength(DONUT_SLICES)
  })

  it('preserves the total when merging the tail', () => {
    const input = cats(37)
    const total = input.reduce((s, c) => s + c.amount, 0)
    expect(donutData(input).reduce((s, c) => s + c.amount, 0)).toBe(total)
  })

  it('names the tail with its count', () => {
    // 37 categories: 9 head slices + a tail of 28.
    expect(last(donutData(cats(37))).category).toBe('Other (28)')
  })

  it('keeps the tail last so it does not displace a real category', () => {
    const out = donutData(cats(20))
    expect(out.slice(0, -1).every((c) => !c.isOther)).toBe(true)
    expect(last(out).isOther).toBe(true)
  })
})

describe('slice colours', () => {
  it.each([10, 11, 40, 200])('never repeats a colour at %i categories', (n) => {
    const out = donutData(cats(n))
    const colors = out.map(sliceColor)
    expect(new Set(colors).size).toBe(colors.length)
  })

  it('gives the merged tail the neutral colour, not a category colour', () => {
    const out = donutData(cats(30))
    expect(sliceColor(last(out), out.length - 1)).toBe(OTHER_COLOR)
    expect(CATEGORY_COLORS).not.toContain(OTHER_COLOR)
  })
})

describe('padding angle', () => {
  it.each([1, 5, 10, 40, 200])('never consumes the full circle at %i categories', (n) => {
    const slices = donutData(cats(n)).length
    expect(slices * paddingAngle(slices)).toBeLessThan(90)
  })
})

describe('ranked list colours match the donut', () => {
  const listColor = (total: number, idx: number) => {
    const inDonut = total <= DONUT_SLICES || idx < DONUT_SLICES - 1
    return inDonut ? CATEGORY_COLORS[idx % CATEGORY_COLORS.length] : OTHER_COLOR
  }

  it('row colour equals its slice colour for every charted category', () => {
    const total = 30
    const out = donutData(cats(total))
    for (let i = 0; i < DONUT_SLICES - 1; i++) {
      expect(listColor(total, i)).toBe(sliceColor(out[i], i))
    }
  })

  it('rows in the merged tail take the Other colour', () => {
    expect(listColor(30, 9)).toBe(OTHER_COLOR)
    expect(listColor(30, 29)).toBe(OTHER_COLOR)
  })

  it('short lists still colour every row distinctly', () => {
    const colors = Array.from({ length: 8 }, (_, i) => listColor(8, i))
    expect(new Set(colors).size).toBe(8)
  })
})
