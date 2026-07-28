import { Box, Typography, Stack } from '@mui/material'

interface SectionHeaderProps {
  title: string
  subtitle?: string
  action?: React.ReactNode
}

export function SectionHeader({ title, subtitle, action }: SectionHeaderProps) {
  return (
    <Box sx={{ mb: 6, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <Box sx={{ width: 4, height: 24, borderRadius: 2, bgcolor: 'primary.main', boxShadow: (theme) => `0 0 10px ${theme.palette.primary.main}` }} />
          <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff', letterSpacing: '-0.02em' }}>
            {title}
          </Typography>
        </Box>
        {subtitle && (
          <Typography variant="body1" sx={{ color: 'text.secondary', fontWeight: 500, ml: 3 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {action && (
        <Stack direction="row" spacing={2} alignItems="center">
          <Box>{action}</Box>
        </Stack>
      )}
    </Box>
  )
}
