import { useState } from 'react'
import { Box, Paper, Typography, TextField, Skeleton } from '@mui/material'
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch'
import { useSipProjection } from '../hooks/useData'
import { fmtInr } from '../../../shared/utils/fmt'

const inputSx = {
  '& .MuiOutlinedInput-root': {
    borderRadius: '14px', bgcolor: 'rgba(0,0,0,0.3)', color: '#fff',
    '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' },
  },
  '& .MuiInputLabel-root': { color: 'text.secondary' },
}

export default function GoalProjectorPanel() {
  const [years, setYears] = useState(10)
  const [annualReturn, setAnnualReturn] = useState(12)
  const [stepupPct, setStepupPct] = useState(10)
  const [monthlySip, setMonthlySip] = useState(0) // 0 = use portfolio's own run-rate

  const { data, isLoading, isFetching } = useSipProjection({
    years, annual_return: annualReturn, stepup_pct: stepupPct, monthly_sip: monthlySip,
  })

  return (
    <Paper sx={{
      p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)', mb: 4,
      boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <RocketLaunchIcon sx={{ color: '#6366F1', fontSize: 24 }} />
        <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Future Wealth Projector</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
        Model where your current SIPs land — or override the inputs to plan a brand-new goal.
      </Typography>

      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        <TextField
          label="Monthly SIP (₹, 0 = use current run-rate)" type="number" size="small" sx={{ ...inputSx, minWidth: 220 }}
          value={monthlySip || ''} placeholder={data?.assumed_monthly_sip ? String(data.assumed_monthly_sip) : ''}
          onChange={(e) => setMonthlySip(Number(e.target.value) || 0)}
        />
        <TextField
          label="Years" type="number" size="small" sx={{ ...inputSx, width: 110 }}
          value={years} onChange={(e) => setYears(Math.max(1, Math.min(40, Number(e.target.value) || 1)))}
        />
        <TextField
          label="Expected Return % p.a." type="number" size="small" sx={{ ...inputSx, width: 170 }}
          value={annualReturn} onChange={(e) => setAnnualReturn(Number(e.target.value) || 0)}
        />
        <TextField
          label="Annual Step-Up %" type="number" size="small" sx={{ ...inputSx, width: 150 }}
          value={stepupPct} onChange={(e) => setStepupPct(Number(e.target.value) || 0)}
        />
      </Box>

      {isLoading ? (
        <Skeleton height={100} sx={{ borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.05)' }} />
      ) : (
        <Box sx={{
          display: 'flex', flexWrap: 'wrap', gap: 3, p: 3, borderRadius: '24px',
          bgcolor: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)', opacity: isFetching ? 0.6 : 1,
        }}>
          <Stat label={`Projected Value in ${years}Y`} value={fmtInr(data?.final_value, true)} color="#4EDE93" />
          <Stat label="Total Invested" value={fmtInr(data?.total_invested, true)} color="#fff" />
          <Stat label="Wealth Gain" value={fmtInr(data?.wealth_gain, true)} color="#6366F1" />
          <Stat label="Wealth Multiple" value={`${data?.wealth_multiple ?? 0}x`} color="#F59E0B" />
        </Box>
      )}

      <Typography variant="caption" sx={{ color: 'text.secondary', mt: 2, display: 'block' }}>
        Assumes a starting monthly SIP of {fmtInr(data?.assumed_monthly_sip)} and your current corpus of {fmtInr(data?.assumed_existing_corpus, true)} as the base. Projections are illustrative, not guaranteed.
      </Typography>
    </Paper>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <Box>
      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 22, fontWeight: 900, color }}>{value}</Typography>
      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>{label}</Typography>
    </Box>
  )
}
