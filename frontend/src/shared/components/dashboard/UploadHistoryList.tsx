import type { ReactNode } from 'react'
import { Box, Chip, IconButton, Stack, Typography } from '@mui/material'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import { motion } from 'framer-motion'

import { fmtInr } from '../../utils/fmt'

/**
 * The "your previous uploads" list, shared by every domain's upload panel.
 *
 * This existed twice, near-verbatim: MFUploadPanel and EquityUploadPanel each carried
 * their own copy of the same motion wrapper, the same stagger delay, the same
 * active/hover gradient logic and the same chip row. The differences were entirely
 * cosmetic or additive - a palette, the word "Funds" versus "Stocks", an optional delete
 * button, an optional broker badge - so they are props here rather than a second file.
 *
 * Each copy also had its own `fmtDate` and `fmtINR`, both built on a fresh
 * `Intl.NumberFormat` per call and neither null-guarded. Formatting now goes through
 * shared/utils/fmt, which returns a zero rather than "₹NaN" on a missing value.
 */

export interface UploadHistoryEntry {
  session_id: string
  created_at: string
  /** Item count. Named for the mutual-fund case historically; it is "holdings" generally. */
  num_funds?: number | null
  total_value?: number | null
  statement_period?: string | null
}

/** Named accents rather than raw hex, so a caller cannot drift from the palette. */
export type HistoryAccent = 'indigo' | 'emerald'

const ACCENTS: Record<HistoryAccent, {
  activeBg: string; activeBorder: string; hoverBg: string; hoverBorder: string
  chevron: string; chipBg: string; chipFg: string
}> = {
  indigo: {
    activeBg: 'linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(79,70,229,0.08) 100%)',
    activeBorder: 'rgba(99,102,241,0.5)',
    hoverBg: 'linear-gradient(135deg, rgba(99,102,241,0.1) 0%, rgba(79,70,229,0.05) 100%)',
    hoverBorder: 'rgba(99,102,241,0.35)',
    chevron: '#818CF8',
    chipBg: 'rgba(99,102,241,0.25)',
    chipFg: '#818CF8',
  },
  emerald: {
    activeBg: 'linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(5,150,105,0.08) 100%)',
    activeBorder: 'rgba(16,185,129,0.5)',
    hoverBg: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(5,150,105,0.05) 100%)',
    hoverBorder: 'rgba(16,185,129,0.35)',
    chevron: '#10B981',
    chipBg: 'rgba(16,185,129,0.25)',
    chipFg: '#34D399',
  },
}

const IDLE_BG = 'linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)'

function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(d)
}

export interface UploadHistoryListProps {
  history?: UploadHistoryEntry[] | null
  onSelect: (sessionId: string) => void
  activeSessionId?: string | null
  compact?: boolean
  accent?: HistoryAccent
  /** Plural noun for the item-count chip, e.g. "Funds" or "Stocks". */
  itemLabel?: string
  /** Shown when there is nothing to list. */
  emptyText?: string
  /** Omit to hide the delete affordance entirely. */
  onDelete?: (sessionId: string) => void
  /** Extra chips beside the date - a broker badge, a statement period, anything. */
  renderBadges?: (entry: UploadHistoryEntry) => ReactNode
  /** How many entries to show. */
  limit?: number
}

export function UploadHistoryList({
  history,
  onSelect,
  activeSessionId,
  compact,
  accent = 'indigo',
  itemLabel = 'Holdings',
  emptyText = 'No previous uploads found',
  onDelete,
  renderBadges,
  limit = 5,
}: UploadHistoryListProps) {
  const entries = history ?? []

  if (entries.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: compact ? 2 : 4 }}>
        <Typography sx={{ color: '#475569', fontSize: '0.85rem' }}>{emptyText}</Typography>
      </Box>
    )
  }

  const c = ACCENTS[accent]

  return (
    <Stack spacing={compact ? 1 : 1.5}>
      {entries.slice(0, limit).map((h, i) => {
        const isActive = h.session_id === activeSessionId
        return (
          <motion.div
            key={h.session_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <Box
              onClick={() => !isActive && onSelect(h.session_id)}
              sx={{
                display: 'flex', alignItems: 'center',
                p: compact ? 1.5 : 2,
                background: isActive ? c.activeBg : IDLE_BG,
                border: `1px solid ${isActive ? c.activeBorder : 'rgba(255,255,255,0.07)'}`,
                borderRadius: '16px',
                cursor: isActive ? 'default' : 'pointer',
                transition: 'all 0.25s ease',
                '&:hover': isActive ? {} : {
                  background: c.hoverBg,
                  borderColor: c.hoverBorder,
                  transform: 'translateY(-1px)',
                  '& .chevron': { color: c.chevron, transform: 'translateX(3px)' },
                  '& .delete-btn': { opacity: 1 },
                },
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
                  <Typography sx={{ color: '#CBD5E1', fontWeight: 700, fontSize: compact ? '0.78rem' : '0.88rem' }}>
                    {fmtDate(h.created_at)}
                  </Typography>
                  {isActive && (
                    <Chip
                      label="Active"
                      size="small"
                      sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, background: c.chipBg, color: c.chipFg, borderRadius: '6px' }}
                    />
                  )}
                  {renderBadges?.(h)}
                </Box>
                <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 1 }}>
                  <Chip
                    label={`${h.num_funds ?? 0} ${itemLabel}`}
                    size="small"
                    sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700, background: 'rgba(255,255,255,0.08)', color: '#E2E8F0', borderRadius: '6px' }}
                  />
                  <Chip
                    label={fmtInr(h.total_value)}
                    size="small"
                    sx={{ height: 20, fontSize: '0.7rem', fontWeight: 800, background: 'rgba(78,222,147,0.1)', color: '#4EDE93', borderRadius: '6px' }}
                  />
                </Box>
              </Box>

              {onDelete && (
                <IconButton
                  size="small"
                  className="delete-btn"
                  aria-label="Delete this upload"
                  onClick={(e) => { e.stopPropagation(); onDelete(h.session_id) }}
                  sx={{
                    opacity: { xs: 1, md: 0 },
                    transition: 'opacity 0.2s',
                    color: '#64748B',
                    '&:hover': { color: '#EF4444', background: 'rgba(239,68,68,0.1)' },
                    mr: 1,
                  }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              )}

              {!isActive && (
                <ChevronRightIcon className="chevron" sx={{ color: '#475569', fontSize: 18, transition: 'all 0.25s ease', flexShrink: 0 }} />
              )}
            </Box>
          </motion.div>
        )
      })}
    </Stack>
  )
}
