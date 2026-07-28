import { Box, Grid, Paper, Typography, Skeleton, Chip } from '@mui/material'
import TimelineIcon from '@mui/icons-material/Timeline'
import { useXirrByFy, useSipAttribution } from '../hooks/useData'
import { fmtInr, fmtPct } from '../../../shared/utils/fmt'

export default function YearlyProgressPanel() {
  const { data: fyData, isLoading: fyLoading } = useXirrByFy()
  const { data: sipData, isLoading: sipLoading } = useSipAttribution()

  const fySeries = fyData?.fy_series ?? []

  return (
    <Paper sx={{
      p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)', mb: 4,
      boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <TimelineIcon sx={{ color: '#6366F1', fontSize: 24 }} />
        <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Year-over-Year Progress</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
        Cumulative XIRR sampled at each financial-year end, and how much of your current value came from SIPs vs lumpsum investments.
      </Typography>

      {fyLoading ? (
        <Skeleton height={80} sx={{ borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.05)', mb: 3 }} />
      ) : fySeries.length ? (
        <Box sx={{ display: 'flex', gap: 1.5, mb: 3, overflowX: 'auto', pb: 1 }}>
          {fySeries.map((fy: any, i: number) => (
            <Box key={i} sx={{
              minWidth: 110, p: 2, borderRadius: '16px', textAlign: 'center', flexShrink: 0,
              bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)',
              ...(fy.is_partial_fy ? { borderColor: 'rgba(99,102,241,0.4)' } : {}),
            }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, display: 'block' }}>{fy.fy}</Typography>
              <Typography sx={{
                fontFamily: '"DM Mono",monospace', fontSize: 17, fontWeight: 900,
                color: fy.cumulative_xirr >= 0 ? '#4EDE93' : '#FF516A',
              }}>
                {fmtPct(fy.cumulative_xirr)}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10 }}>{fmtInr(fy.cumulative_value, true)}</Typography>
            </Box>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>Not enough transaction history to compute yearly progress yet.</Typography>
      )}

      {sipLoading ? (
        <Skeleton height={64} sx={{ borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.05)' }} />
      ) : sipData?.sip_share_pct != null ? (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={6}>
              <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 18, fontWeight: 900, color: '#6366F1' }}>
                  {fmtInr(sipData.sip_current_value, true)}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>
                  SIP-sourced ({sipData.sip_share_pct}%)
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6}>
              <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 18, fontWeight: 900, color: '#F59E0B' }}>
                  {fmtInr(sipData.lumpsum_current_value, true)}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>
                  Lumpsum-sourced ({(100 - sipData.sip_share_pct).toFixed(1)}%)
                </Typography>
              </Box>
            </Grid>
          </Grid>
          <Chip
            label={sipData.note}
            size="small"
            sx={{ height: 'auto', py: 1, fontSize: 11, fontWeight: 600, color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.03)', '& .MuiChip-label': { whiteSpace: 'normal', display: 'block' } }}
          />
        </>
      ) : null}
    </Paper>
  )
}
