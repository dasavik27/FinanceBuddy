import type { ReactNode } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { Box, Button, Divider, IconButton, Popover, Tooltip, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import HistoryIcon from '@mui/icons-material/History'
import ShieldIcon from '@mui/icons-material/Shield'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'

import { UploadHistoryList } from './UploadHistoryList'
import type { HistoryAccent, UploadHistoryEntry } from './UploadHistoryList'

/**
 * "Switch portfolio" button and its popover, shared by every domain's dashboard.
 *
 * MFUploadPanel and EquityUploadPanel each carried their own copy: the same anchorEl
 * state machine, the same `useEffect(() => { if (open) fetchHistory() }, [open, fetchHistory])`,
 * the same 360px Popover with the same blur/shadow/radius, the same header row and the
 * same trust caption. What genuinely differed was the palette, four strings, and what
 * goes below the divider - MF embeds a mini dropzone, equity offers a connect button.
 * Those are props; the shell is not duplicated any more.
 */

const ACCENT_HEX: Record<HistoryAccent, { base: string; hover: string; soft: string }> = {
  indigo:  { base: '#6366F1', hover: '#818CF8', soft: '99,102,241' },
  emerald: { base: '#10B981', hover: '#34D399', soft: '16,185,129' },
}

export interface SwitchSessionButtonProps {
  /** Currently loaded session, marked "Active" in the list. */
  sessionId: string | null
  /** Fetches this domain's upload history. Called when the popover opens. */
  fetchHistory: () => Promise<UploadHistoryEntry[]>
  /** Called with the chosen session id; the popover closes itself afterwards. */
  onSelect: (sessionId: string) => void
  onDelete?: (sessionId: string) => void

  accent?: HistoryAccent
  buttonLabel: string
  tooltip: string
  popoverTitle: string
  itemLabel: string
  emptyText?: string
  renderBadges?: (entry: UploadHistoryEntry) => ReactNode

  /** Content below the divider. Receives a closer so it can dismiss the popover. */
  footerTitle?: string
  renderFooter?: (close: () => void) => ReactNode
}

export function SwitchSessionButton({
  sessionId, fetchHistory, onSelect, onDelete,
  accent = 'indigo', buttonLabel, tooltip, popoverTitle, itemLabel, emptyText,
  renderBadges, footerTitle, renderFooter,
}: SwitchSessionButtonProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [history, setHistory] = useState<UploadHistoryEntry[]>([])
  const open = Boolean(anchorEl)
  const c = ACCENT_HEX[accent]

  const close = useCallback(() => setAnchorEl(null), [])

  const load = useCallback(() => {
    let cancelled = false
    fetchHistory()
      .then((rows) => { if (!cancelled) setHistory(rows ?? []) })
      .catch(console.error)
    return () => { cancelled = true }
  }, [fetchHistory])

  useEffect(() => {
    if (!open) return
    // Returns a cancel closure, so a popover closed mid-flight does not set state on an
    // unmounted tree. Neither original copy did this.
    return load()
  }, [open, load])

  const handleSelect = (sid: string) => {
    onSelect(sid)
    close()
  }

  const handleDelete = onDelete
    ? (sid: string) => {
        onDelete(sid)
        setHistory((rows) => rows.filter((r) => r.session_id !== sid))
      }
    : undefined

  return (
    <>
      <Tooltip title={tooltip} placement="bottom">
        <Button
          variant="outlined"
          size="small"
          startIcon={<SwapHorizIcon sx={{ fontSize: 16 }} />}
          onClick={(e) => setAnchorEl(e.currentTarget)}
          sx={{
            borderColor: `rgba(${c.soft},0.35)`,
            color: '#94A3B8',
            textTransform: 'none',
            fontWeight: 700,
            fontSize: '0.82rem',
            borderRadius: '10px',
            px: 1.5,
            '&:hover': { borderColor: c.base, color: c.hover, background: `rgba(${c.soft},0.08)` },
          }}
        >
          {buttonLabel}
        </Button>
      </Tooltip>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={close}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{
          sx: {
            mt: 1, width: 360, borderRadius: '20px',
            background: 'rgba(15,23,42,0.97)',
            border: `1px solid rgba(${c.soft},0.2)`,
            boxShadow: `0 24px 60px rgba(0,0,0,0.6), 0 0 40px rgba(${c.soft},0.1)`,
            backdropFilter: 'blur(20px)',
            overflow: 'hidden',
          },
        }}
      >
        <Box sx={{ px: 2.5, pt: 2.5, pb: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <HistoryIcon sx={{ color: c.base, fontSize: 18 }} />
            <Typography sx={{ fontWeight: 800, fontSize: '0.9rem', color: '#F8FAFC' }}>
              {popoverTitle}
            </Typography>
          </Box>
          <IconButton size="small" onClick={close} sx={{ color: '#475569', '&:hover': { color: '#94A3B8' } }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ px: 2.5, pb: 1.5 }}>
          <UploadHistoryList
            history={history}
            onSelect={handleSelect}
            activeSessionId={sessionId}
            onDelete={handleDelete}
            accent={accent}
            itemLabel={itemLabel}
            emptyText={emptyText}
            renderBadges={renderBadges}
            compact
          />
        </Box>

        {renderFooter && (
          <>
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.06)', mx: 2.5 }} />
            <Box sx={{ px: 2.5, pt: 2, pb: 2.5 }}>
              {footerTitle && (
                <Typography sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase', mb: 1.5 }}>
                  {footerTitle}
                </Typography>
              )}
              {renderFooter(close)}
            </Box>
          </>
        )}

        <Box sx={{ px: 2.5, pb: 2, textAlign: 'center' }}>
          <Typography variant="caption" sx={{ color: '#334155', fontSize: '0.68rem' }}>
            <ShieldIcon sx={{ fontSize: 10, verticalAlign: 'middle', mr: 0.5, color: '#4EDE93' }} />
            Processed on your backend only
          </Typography>
        </Box>
      </Popover>
    </>
  )
}
