import { fmtInr } from '../../../api/fmt'
import React from 'react'
import { Box, Typography, Paper, Stack, alpha } from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import SavingsIcon from '@mui/icons-material/Savings'
import ShieldIcon from '@mui/icons-material/Shield'

interface FindingsProps {
  flags?: {
    zero_cost?: any[];
    missing_trades?: any[];
    cost_mismatch?: any[];
  }
}

export default function TaxAuditorFindings({ flags }: FindingsProps) {
  if (!flags) return null
  
  const hasZeroCost = flags.zero_cost && flags.zero_cost.length > 0
  const hasMismatch = flags.cost_mismatch && flags.cost_mismatch.length > 0

  if (!hasZeroCost && !hasMismatch) return null

  return (
    <Box sx={{ mb: 5 }}>
      <Paper className="glass" sx={{ 
        p: 3, 
        borderRadius: '24px', 
        border: '1px solid rgba(234, 179, 8, 0.3)',
        background: `linear-gradient(135deg, ${alpha('#EAB308', 0.05)} 0%, ${alpha('#EAB308', 0.02)} 100%)`,
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <Box sx={{ p: 1, borderRadius: '12px', bgcolor: alpha('#EAB308', 0.1), display: 'flex' }}>
            <ShieldIcon sx={{ color: '#EAB308', fontSize: 24 }} />
          </Box>
          <Box>
            <Typography variant="overline" sx={{ color: '#EAB308', fontWeight: 900, letterSpacing: '0.15em' }}>
              TAX AUDITOR FINDINGS
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
              We cross-referenced your AIS with your Broker P&L and found discrepancies.
            </Typography>
          </Box>
        </Box>

        <Stack spacing={2}>
          {hasZeroCost && (
            <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: alpha('#EF4444', 0.08), border: `1px solid ${alpha('#EF4444', 0.2)}` }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                <ErrorOutlineIcon sx={{ color: '#EF4444', fontSize: 20 }} />
                <Typography variant="body1" sx={{ color: '#EF4444', fontWeight: 800 }}>Missing Cost Basis (Zero Cost Warning)</Typography>
              </Box>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 500 }}>
                The government's AIS reported a purchase cost of ₹0 for these assets, meaning you would pay tax on the entire sale value. We recommend overriding this with your actual broker cost.
              </Typography>
              <Stack spacing={1}>
                {flags.zero_cost?.map((flag, i) => (
                  <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, bgcolor: 'rgba(0,0,0,0.2)', borderRadius: '12px' }}>
                    <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700 }}>{flag.security}</Typography>
                    <Typography variant="body2" sx={{ color: '#EF4444', fontWeight: 800 }}>{flag.suggestion}</Typography>
                  </Box>
                ))}
              </Stack>
            </Box>
          )}



          {hasMismatch && (
            <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: alpha('#3B82F6', 0.08), border: `1px solid ${alpha('#3B82F6', 0.2)}` }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                <SavingsIcon sx={{ color: '#3B82F6', fontSize: 20 }} />
                <Typography variant="body1" sx={{ color: '#3B82F6', fontWeight: 800 }}>Grandfathering / Cost Mismatch</Typography>
              </Box>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 500 }}>
                We found a large difference between your AIS cost and your Broker cost. If these were bought before Jan 31, 2018, you can use the FMV indexation to lower your taxes.
              </Typography>
              <Stack spacing={1}>
                {flags.cost_mismatch?.map((flag, i) => (
                  <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, bgcolor: 'rgba(0,0,0,0.2)', borderRadius: '12px' }}>
                    <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700 }}>{flag.security}</Typography>
                    <Typography variant="caption" sx={{ color: '#3B82F6', fontWeight: 700 }}>
                      AIS Cost: {fmtInr(flag.ais_cost)} vs Broker Cost: {fmtInr(flag.broker_cost)}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Box>
          )}

        </Stack>
      </Paper>
    </Box>
  )
}
