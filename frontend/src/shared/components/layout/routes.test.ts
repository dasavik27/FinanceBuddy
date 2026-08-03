/**
 * Guards the URL structure.
 *
 * Domains moved from /dashboard/<domain> to /<domain>. Two things about that are
 * easy to get wrong and impossible to notice without signing in:
 *
 *   1. The hub lives at /dashboard while legacy links are /dashboard/<domain>, so the
 *      static "dashboard" route and the "dashboard/*" catch-all overlap. If the
 *      wildcard ever outranks the static path, visiting the hub silently redirects to
 *      "/" instead of rendering.
 *   2. The legacy redirect has to preserve the sub-path, query and hash, or a shared
 *      deep link degrades to a bare domain landing page.
 *
 * These are asserted against react-router's own matcher rather than a hand-rolled
 * copy of its ranking rules.
 */
import { describe, it, expect } from 'vitest'
import { matchRoutes } from 'react-router-dom'

// Mirrors the `path` values in Dashboard.tsx. Element rendering needs a DOM and MUI;
// the ranking behaviour under test is pure and does not.
const ROUTES = [
  { path: 'dashboard' },
  { path: 'mutual-funds/*' },
  { path: 'equity/*' },
  { path: 'tax-expert/*' },
  { path: 'budget/*' },
  { path: 'accounts' },
  { path: 'admin' },
  { path: 'dashboard/*' },
  { path: 'holdings' },
  { path: 'performance' },
  { path: 'compare' },
  { path: 'insights' },
  { path: 'rebalance' },
  { path: 'tax' },
  { path: 'journey' },
  { path: 'account' },
  { path: '*' },
]

const matched = (pathname: string) => {
  const m = matchRoutes(ROUTES, pathname)
  return m?.[m.length - 1]?.route.path
}

/** The redirect performed by LegacyDashboardRedirect in Dashboard.tsx. */
const stripDashboard = (pathname: string, search = '', hash = '') =>
  `${pathname.replace(/^\/dashboard/, '') || '/'}${search}${hash}`

describe('top-level domain routes', () => {
  it.each([
    ['/equity', 'equity/*'],
    ['/equity/analyzer', 'equity/*'],
    ['/mutual-funds', 'mutual-funds/*'],
    ['/mutual-funds/holdings', 'mutual-funds/*'],
    ['/tax-expert', 'tax-expert/*'],
    ['/budget', 'budget/*'],
    ['/budget/anything/deep', 'budget/*'],
    ['/accounts', 'accounts'],
    ['/admin', 'admin'],
  ])('%s resolves to %s', (pathname, expected) => {
    expect(matched(pathname)).toBe(expected)
  })
})

describe('the hub', () => {
  it('/dashboard hits the static hub route, not the legacy wildcard', () => {
    // The regression this exists to catch: if "dashboard/*" won, the hub would
    // redirect to "/" and be unreachable from the sidebar.
    expect(matched('/dashboard')).toBe('dashboard')
  })

  it('an unknown path falls back to the hub, not to a domain', () => {
    expect(matched('/no-such-page')).toBe('*')
  })
})

describe('legacy /dashboard/<domain> links', () => {
  it('still match a route rather than 404', () => {
    expect(matched('/dashboard/equity')).toBe('dashboard/*')
    expect(matched('/dashboard/mutual-funds/holdings')).toBe('dashboard/*')
  })

  it.each([
    ['/dashboard/equity', '/equity'],
    ['/dashboard/mutual-funds/holdings', '/mutual-funds/holdings'],
    ['/dashboard/accounts', '/accounts'],
    ['/dashboard/budget', '/budget'],
  ])('%s rewrites to %s', (from, to) => {
    expect(stripDashboard(from)).toBe(to)
  })

  it('preserves query and hash on a deep link', () => {
    expect(stripDashboard('/dashboard/budget', '?tab=2', '#txns')).toBe('/budget?tab=2#txns')
  })

  it('never produces an empty path', () => {
    expect(stripDashboard('/dashboard')).toBe('/')
  })
})

describe('legacy flat mutual-fund tab links', () => {
  it.each(['holdings', 'performance', 'compare', 'insights', 'journey'])(
    '/%s is still routed', (tab) => {
      expect(matched(`/${tab}`)).toBe(tab)
    },
  )
})
