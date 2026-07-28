import { Box, Paper, Typography, Skeleton, Chip } from '@mui/material'
import LayersIcon from '@mui/icons-material/Layers'
import { useMandateOverlap } from '../hooks/useData'
import { fmtInr } from '../../../shared/utils/fmt'

const SEVERITY_COLOR: Record<string, string> = {
  high: '#FF516A',
  moderate: '#F59E0B',
  low: '#6366F1',
}

export default function MandateOverlapPanel() {
  const { data, isLoading } = useMandateOverlap()
  const groups = data?.groups ?? []

  return (
    <Paper sx={{
      p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)', mb: 4,
      boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <LayersIcon sx={{ color: '#F59E0B', fontSize: 24 }} />
        <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Mandate Overlap</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
        Funds sharing the same category and cap-type mandate — worth checking for stock-level redundancy.
      </Typography>

      {isLoading ? (
        <Skeleton height={100} sx={{ borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.05)', mb: 2 }} />
      ) : groups.length ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mb: 3 }}>
          {groups.map((g: any, i: number) => {
            const color = SEVERITY_COLOR[g.severity] ?? '#6366F1'
            return (
              <Box key={i} sx={{
                p: 2.5, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)',
                border: '1px solid rgba(255,255,255,0.05)', borderLeft: `6px solid ${color}`,
              }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography sx={{ fontSize: 14, fontWeight: 800, color: '#fff' }}>
                    {g.category}{g.cap_type ? ` · ${g.cap_type}` : ''} ({g.fund_count} funds{g.same_amc ? ', same AMC' : ''})
                  </Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 15, fontWeight: 900, color }}>
                    {g.combined_weight_pct}%
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {g.funds.map((f: any, j: number) => (
                    <Chip
                      key={j}
                      label={`${f.fund} (${fmtInr(f.value, true)})`}
                      size="small"
                      sx={{ fontSize: 11, fontWeight: 600, bgcolor: 'rgba(255,255,255,0.05)', color: 'text.secondary' }}
                    />
                  ))}
                </Box>
              </Box>
            )
          })}
        </Box>
      ) : (
        <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>No category/cap-type overlap detected — your holdings span distinct mandates.</Typography>
      )}

      <Chip
        label={data?.disclaimer || 'Category/cap-type proxy only — not true stock-level overlap.'}
        size="small"
        sx={{ height: 'auto', py: 1, fontSize: 11, fontWeight: 600, color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.03)', '& .MuiChip-label': { whiteSpace: 'normal', display: 'block' } }}
      />
    </Paper>
  )
}
