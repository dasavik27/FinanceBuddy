import type { ReactNode } from 'react'
import { Alert, Box, Paper, Skeleton, Typography } from '@mui/material'
import type { SxProps } from '@mui/material'
import type { SvgIconComponent } from '@mui/icons-material'

/**
 * Primitives shared by the equity tabs.
 *
 * The glass-Paper `sx` literal was repeated verbatim in about twelve places, and the
 * header-cell style in six. Beyond the duplication, an inline object literal has a new
 * identity on every render, so emotion re-serialises it every time - which on a table
 * is once per header cell per render. Hoisting to a module constant makes the identity
 * stable.
 */

export const GLASS_PAPER: SxProps = {
  borderRadius: '24px',
  background: 'rgba(15,23,42,0.6)',
  border: '1px solid rgba(255,255,255,0.06)',
}

export const HEADER_CELL: SxProps = {
  background: 'rgba(15,23,42,0.9)',
  color: '#94A3B8',
  fontWeight: 700,
}

/**
 * Card with an icon-chip header.
 *
 * Lives here rather than being a third copy: InsightsTab's InsightCard and PLTab's
 * TopMovers were the same header block with different bodies. MetricCard in
 * shared/components/ui covers the *metric* shape (one big number); this covers the
 * "titled panel with arbitrary content" shape, which MetricCard cannot express.
 */
export function IconPanel({
  title, icon: Icon, color, children, dense,
}: {
  title: string
  icon: SvgIconComponent
  color: string
  children: ReactNode
  dense?: boolean
}) {
  const size = dense ? 36 : 40
  return (
    <Paper className="glass" sx={{ ...GLASS_PAPER, p: dense ? 3 : 4, height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Box
          sx={{
            width: size, height: size, borderRadius: dense ? '10px' : '12px',
            background: `${color}15`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Icon sx={{ color, fontSize: dense ? 20 : 24 }} />
        </Box>
        <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: dense ? '1.1rem' : '1.2rem' }}>
          {title}
        </Typography>
      </Box>
      {children}
    </Paper>
  )
}

/** Categorical palette for the allocation charts, in one place rather than two. */
export const CHART_COLORS = [
  '#6366F1', '#8B5CF6', '#EC4899', '#F59E0B', '#10B981',
  '#06B6D4', '#F43F5E', '#84CC16', '#A855F7', '#14B8A6',
] as const

/**
 * Shape-matched loading state.
 *
 * Every tab used a bare centered CircularProgress, which on a refetch blanked content
 * that was already on screen. A skeleton at least keeps the layout stable.
 */
export function EquityTabSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <Paper className="glass" sx={{ ...GLASS_PAPER, p: 3 }}>
      <Skeleton variant="text" width={180} height={28} sx={{ bgcolor: 'rgba(255,255,255,0.06)' }} />
      <Box sx={{ mt: 2 }}>
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton
            key={i}
            variant="rectangular"
            height={40}
            sx={{ mb: 1, borderRadius: '8px', bgcolor: 'rgba(255,255,255,0.04)' }}
          />
        ))}
      </Box>
    </Paper>
  )
}

/**
 * Error state that distinguishes the cases the user can act on.
 *
 * The tabs previously did `.catch(console.error)` and then either rendered `null` - a
 * silently blank tab - or a fixed "Failed to load X" with no retry and no distinction
 * between "signed out", "not your session" and "the server broke". A 404 here is
 * expected rather than exceptional: equity sessions live in a bounded in-process LRU,
 * so one can simply be gone.
 */
export function EquityTabError({ error, label }: { error: unknown; label: string }) {
  const status = (error as { response?: { status?: number } } | null)?.response?.status

  let message = `Could not load ${label}. Please try again.`
  if (status === 401) message = 'Your session has ended. Sign in again to continue.'
  else if (status === 404) {
    message =
      'This portfolio is no longer loaded on the server. Upload your holdings again to continue.'
  } else if (status === 503) message = `Could not verify access to this portfolio. Please retry.`

  return (
    <Alert severity={status === 404 ? 'info' : 'error'} sx={{ borderRadius: '16px' }}>
      <Typography sx={{ fontWeight: 600 }}>{message}</Typography>
    </Alert>
  )
}
