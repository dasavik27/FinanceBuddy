import { Box, Grid, Paper, Typography, Skeleton, Chip } from '@mui/material'
import SavingsIcon from '@mui/icons-material/Savings'
import LockClockIcon from '@mui/icons-material/LockClock'
import { useTaxHarvest } from '../hooks/useData'
import { fmtInr } from '../../../shared/utils/fmt'

export default function TaxHarvestPanel() {
  const { data, isLoading } = useTaxHarvest()

  const harvest = data?.harvest
  const debtSummary = data?.debt_summary
  const elssLocked = data?.elss_locked_value ?? 0

  return (
    <Paper sx={{
      p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)', mb: 4,
      boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <SavingsIcon sx={{ color: '#4EDE93', fontSize: 24 }} />
        <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Tax Harvest Opportunities</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
        LTCG within your ₹1.25L annual exemption, plus loss-harvesting candidates — booked and reinvested same-day, this costs nothing but paperwork.
      </Typography>

      {isLoading ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} height={64} sx={{ borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.05)' }} />
          ))}
        </Box>
      ) : (
        <>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={4}>
              <StatBox label="Tax Saveable" value={fmtInr(harvest?.total_tax_saved, true)} color="#4EDE93" />
            </Grid>
            <Grid item xs={12} sm={4}>
              <StatBox label="Exemption Remaining" value={fmtInr(harvest?.remaining_exemption, true)} color="#6366F1" />
            </Grid>
            <Grid item xs={12} sm={4}>
              <StatBox label="ELSS Locked (3-yr)" value={fmtInr(elssLocked, true)} color="#F59E0B" />
            </Grid>
          </Grid>

          {harvest?.harvest_list?.length ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mb: 3 }}>
              {harvest.harvest_list.map((h: any, i: number) => {
                const isLoss = h.action?.toUpperCase().includes('LOSS')
                const color = isLoss ? '#FF516A' : '#4EDE93'
                return (
                  <Box key={i} sx={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, p: 2.5,
                    borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)',
                    borderLeft: `6px solid ${color}`,
                  }}>
                    <Box>
                      <Typography sx={{ fontSize: 14, fontWeight: 800, color: '#fff' }}>{h.fund}</Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>{h.action}</Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 15, fontWeight: 900, color }}>
                        {fmtInr(h.gain)}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>
                        tax saved {fmtInr(h.tax_saved, true)}
                      </Typography>
                    </Box>
                  </Box>
                )
              })}
            </Box>
          ) : (
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>No harvestable gains or losses detected right now.</Typography>
          )}

          {debtSummary && (debtSummary.slab_taxed_gain > 0 || debtSummary.ltcg_gain_pre_2023_units > 0) && (
            <Box sx={{
              display: 'flex', alignItems: 'flex-start', gap: 2, p: 2.5, borderRadius: '20px',
              bgcolor: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', mb: 2,
            }}>
              <LockClockIcon sx={{ color: '#F59E0B', fontSize: 20, mt: 0.3, flexShrink: 0 }} />
              <Box>
                <Typography sx={{ fontSize: 13, fontWeight: 800, color: '#F59E0B', mb: 0.5 }}>
                  Debt/Liquid Fund Gains: {fmtInr(debtSummary.slab_taxed_gain, true)} (est. tax {fmtInr(debtSummary.estimated_tax_at_slab, true)})
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>{debtSummary.note}</Typography>
              </Box>
            </Box>
          )}

          <Chip
            label={data?.disclaimer || 'Indicative estimate only — not tax advice.'}
            size="small"
            sx={{ height: 'auto', py: 1, fontSize: 11, fontWeight: 600, color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.03)', '& .MuiChip-label': { whiteSpace: 'normal', display: 'block' } }}
          />
        </>
      )}
    </Paper>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 20, fontWeight: 900, color }}>{value}</Typography>
      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>{label}</Typography>
    </Box>
  )
}
