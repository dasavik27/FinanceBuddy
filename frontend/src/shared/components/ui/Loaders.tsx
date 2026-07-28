import { Box, Typography, Skeleton } from '@mui/material'

export function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const pct  = Math.min(100, Math.max(0, score))
  const color = pct >= 70 ? '#4EDE93' : pct >= 40 ? '#F59E0B' : '#FF516A'
  const r = (size / 2) - 8
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - pct / 100)
  return (
    <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', filter: 'drop-shadow(0 0 12px rgba(78, 222, 147, 0.2))' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={8} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={8}
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 600ms cubic-bezier(0,0,0,1)' }}
        />
      </svg>
      <Box sx={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: size * 0.28, fontWeight: 800, color: '#fff', lineHeight: 1 }}>
          {score}
        </Typography>
        <Typography sx={{ fontSize: 9, color: '#94A3B8', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          /100
        </Typography>
      </Box>
    </Box>
  )
}

export function ProgressRow({ label, actual, max }: { label: string; actual: number; max: number }) {
  const pct   = max > 0 ? (actual / max) * 100 : 0
  const color = pct >= 70 ? '#4EDE93' : pct >= 40 ? '#F59E0B' : '#FF516A'
  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.75 }}>
        <Typography variant="body2" fontWeight={700} sx={{ color: 'rgba(255,255,255,0.9)' }}>{label}</Typography>
        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '0.75rem', fontWeight: 700, color: '#94A3B8' }}>
          {actual}/{max}
        </Typography>
      </Box>
      <Box sx={{ width: '100%', height: 6, bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 999, overflow: 'hidden' }}>
        <Box sx={{ width: `${pct}%`, height: '100%', bgcolor: color, borderRadius: 999, transition: 'width 0.5s ease' }} />
      </Box>
    </Box>
  )
}

export function LoadingGrid({ cols = 4, rows = 1 }: { cols?: number; rows?: number }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 2, mb: 3 }}>
      {Array.from({ length: cols * rows }).map((_, i) => (
        <Skeleton key={i} variant="rectangular" height={100} sx={{ borderRadius: 2 }} />
      ))}
    </Box>
  )
}

export function PremiumPulseLoader({ size = 48 }: { size?: number }) {
  return (
    <Box sx={{ position: 'relative', width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Box sx={{
        position: 'absolute', inset: 0, borderRadius: '50%',
        border: '3px solid rgba(99, 102, 241, 0.1)',
        borderTopColor: '#6366F1',
        animation: 'spin 1.2s cubic-bezier(0.55, 0.055, 0.675, 0.19) infinite',
        boxShadow: '0 0 20px rgba(99, 102, 241, 0.4)'
      }} />
      <Box sx={{
        position: 'absolute', inset: 6, borderRadius: '50%',
        border: '3px solid rgba(78, 222, 147, 0.1)',
        borderBottomColor: '#4EDE93',
        animation: 'spin 1.8s linear infinite reverse',
        boxShadow: '0 0 15px rgba(78, 222, 147, 0.4)'
      }} />
      <Box sx={{
        width: size * 0.35, height: size * 0.35, borderRadius: '50%',
        background: 'linear-gradient(135deg, #6366F1, #38BDF8)',
        boxShadow: '0 0 12px #38BDF8',
        animation: 'pulse 1.5s ease-in-out infinite'
      }} />
      <style>{`
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes pulse { 0% { transform: scale(0.85); opacity: 0.7; } 50% { transform: scale(1.15); opacity: 1; } 100% { transform: scale(0.85); opacity: 0.7; } }
      `}</style>
    </Box>
  )
}

export function TabLoader({ message = "Retrieving institutional data feed..." }: { message?: string }) {
  return (
    <Box sx={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: '400px', width: '100%', gap: 3, p: 4
    }}>
      <PremiumPulseLoader size={64} />
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.1em', textTransform: 'uppercase', mb: 0.75 }}>
          AUDIT ENGINE ACTIVE
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 600, color: '#94A3B8', letterSpacing: '0.02em', maxWidth: 360, mx: 'auto' }}>
          {message}
        </Typography>
      </Box>
    </Box>
  )
}

export function OverlayLoader({ message = "Synchronizing market data..." }: { message?: string }) {
  return (
    <Box sx={{
      position: 'absolute', inset: 0, zIndex: 50,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2,
      bgcolor: 'rgba(15, 23, 42, 0.75)', backdropFilter: 'blur(12px)', borderRadius: 'inherit'
    }}>
      <PremiumPulseLoader size={48} />
      <Typography variant="caption" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
        {message}
      </Typography>
    </Box>
  )
}
