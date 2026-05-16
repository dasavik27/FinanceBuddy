import { Box } from '@mui/material'

interface PeriodSelectorProps {
  options:   string[]
  value:     string
  onChange:  (v: string) => void
}

export function PeriodSelector({ options, value, onChange }: PeriodSelectorProps) {
  return (
    <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
      {options.map((o) => (
        <Box
          key={o}
          onClick={() => onChange(o)}
          sx={{
            px: 1.75, py: 0.6,
            borderRadius: 999,
            fontSize: '0.75rem', fontWeight: 600,
            cursor: 'pointer',
            border: `1.5px solid ${o === value ? '#0F172A' : '#E2E8F0'}`,
            background: o === value ? '#0F172A' : '#FFFFFF',
            color: o === value ? '#FFFFFF' : '#64748B',
            transition: 'all 120ms ease',
            '&:hover': o !== value ? { borderColor: '#BFDBFE', background: '#EFF6FF', color: '#1D4ED8' } : {},
          }}
        >
          {o}
        </Box>
      ))}
    </Box>
  )
}
