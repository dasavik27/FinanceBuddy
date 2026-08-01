import { Box, Typography, Skeleton, alpha, Tooltip as MuiTooltip } from '@mui/material'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import type { SvgIconComponent } from '@mui/icons-material'
import { motion } from 'framer-motion'

interface MetricCardProps {
  label:    string
  value:    string | number
  sub?:     string
  accent?:  'success' | 'danger' | 'info' | 'warn' | 'none'
  loading?: boolean
  info?:    string
  /**
   * Optional leading icon, rendered in a tinted chip beside the label.
   *
   * Added so the equity dashboard could adopt this component rather than keep its own
   * near-identical StatCard, whose only real difference was the icon. Takes the accent
   * colour, so callers do not pass a raw hex and drift from the palette.
   */
  icon?:    SvgIconComponent
}

export function MetricCard({ label, value, sub, accent, loading, info, icon: Icon }: MetricCardProps) {
  const accentColor = (theme: any) => ({
    success: theme.palette.secondary.main,
    danger: theme.palette.error.main,
    info: theme.palette.primary.main,
    warn: '#EAB308',
    none: 'rgba(0,0,0,0)',
  }[accent ?? 'none'])

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
    >
      <Box
        sx={{
          p: '24px',
          borderRadius: '24px',
          background: 'rgba(19, 27, 46, 0.4)',
          backdropFilter: 'blur(40px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          boxShadow: 'inset 0 1px 1px rgba(255, 255, 255, 0.05)',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          position: 'relative',
          overflow: 'hidden',
          '&:hover': {
            transform: 'translateY(-4px)',
            borderColor: (theme) => alpha(accentColor(theme), 0.4),
            boxShadow: (theme) => `0 0 30px ${alpha(accentColor(theme), 0.15)}`,
            '& .accent-bar': {
              opacity: 1,
            }
          },
        }}
      >
        {/* Subtle Accent Glow Bar */}
        <Box
          className="accent-bar"
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '3px',
            background: (theme) => `linear-gradient(90deg, transparent, ${accentColor(theme)}, transparent)`,
            opacity: 0.3,
            transition: 'opacity 0.3s ease',
          }}
        />

        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
            {Icon && (
              <Box
                sx={{
                  width: 36, height: 36, borderRadius: '12px', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: (theme) => alpha(accentColor(theme) || '#94A3B8', 0.12),
                }}
              >
                <Icon sx={{ fontSize: 20, color: (theme) => accentColor(theme) || 'text.secondary' }} />
              </Box>
            )}
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 700, letterSpacing: '0.1em', display: 'block', m: 0 }}>
              {label}
            </Typography>
          </Box>
          {info && (
            <MuiTooltip title={info} placement="top" arrow sx={{ '& .MuiTooltip-tooltip': { bgcolor: '#0F172A', color: '#fff', fontSize: 12, p: 1.5, borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)' } }}>
              <InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary', opacity: 0.6, cursor: 'pointer', '&:hover': { opacity: 1, color: 'primary.main' } }} />
            </MuiTooltip>
          )}
        </Box>

        {loading ? (
          <Skeleton variant="text" width="80%" height={48} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
        ) : (
          <Typography
            className="num"
            sx={{
              fontSize: '2rem',
              fontWeight: 800,
              color: '#fff',
              letterSpacing: '-1px',
              lineHeight: 1.1,
              mb: sub ? 1 : 0,
            }}
          >
            {value}
          </Typography>
        )}

        {sub && !loading && (
          <Typography 
            variant="caption" 
            sx={{ 
              color: accent && accent !== 'none' ? (theme) => accentColor(theme) : 'text.secondary',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 0.5
            }}
          >
            {sub}
          </Typography>
        )}
      </Box>
    </motion.div>
  )
}
