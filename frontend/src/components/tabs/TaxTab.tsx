import { Box, Grid, Paper, Typography, Alert, Skeleton, Table, TableHead, TableRow, TableCell, TableBody, TableContainer } from '@mui/material'
import { useTax } from '../../hooks/useData'
import { SectionHeader, MetricCard } from '../ui'
import { fmtInr } from '../../api/fmt'

export default function TaxTab() {
  const { data, isLoading, error } = useTax()

  return (
    <Box>
      <SectionHeader title="Tax Liability Estimator" subtitle="Estimates based on current holdings. Not financial/tax advice — consult a CA." />
      {error && <Alert severity="error" sx={{ mb: 2 }}>Failed to load tax data.</Alert>}

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'ELSS Holdings',       value: fmtInr(data?.elss_value),    sub: `${data?.elss_count ?? 0} ELSS funds · ${fmtInr(data?.elss_invested)} invested`,                         accent: 'info' as const },
          { label: 'Equity Gains',         value: fmtInr(data?.equity_gain),   sub: 'Total unrealised equity gains',                                                                         accent: (data?.equity_gain ?? 0) >= 0 ? 'success' as const : 'danger' as const },
          { label: 'Est. Equity LTCG Tax', value: fmtInr(data?.ltcg_equity),   sub: '12.5% on gains above ₹1.25L · if redeemed today',                                                     accent: 'warn' as const },
          { label: 'Est. Debt STCG Tax',   value: fmtInr(data?.stcg_debt),     sub: 'At 30% slab rate · debt/hybrid gains',                                                                 accent: 'danger' as const },
        ].map((card) => (
          <Grid item xs={12} sm={6} md={3} key={card.label}>
            <MetricCard {...card} loading={isLoading} />
          </Grid>
        ))}
      </Grid>

      {/* ELSS lock-in table */}
      {!isLoading && (data?.elss_lockin?.length ?? 0) > 0 && (
        <Paper elevation={1} sx={{ borderRadius: 3, overflow: 'hidden', mb: 3 }}>
          <Box sx={{ p: 2.5, borderBottom: '1px solid #F1F5F9' }}>
            <Typography variant="h6">ELSS Lock-in Tracker</Typography>
            <Typography variant="body2" color="text.secondary">3-year lock-in from each investment date</Typography>
          </Box>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Fund</TableCell>
                  <TableCell align="right">Earliest Investment</TableCell>
                  <TableCell align="right">Lock-in Ends</TableCell>
                  <TableCell align="right">Status</TableCell>
                  <TableCell align="right">Value</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data?.elss_lockin?.map((row: any, i: number) => {
                  const unlocked = row['Status'] === 'Unlocked'
                  return (
                    <TableRow key={i} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={600} sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {row['Fund']}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12 }}>
                          {row['Earliest Investment']}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12 }}>
                          {row['Lock-in Ends']}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Box sx={{
                          display: 'inline-block', px: 1.25, py: 0.3, borderRadius: 999,
                          fontSize: 11, fontWeight: 700,
                          background: unlocked ? '#ECFDF5' : '#FEF3C7',
                          color:      unlocked ? '#059669' : '#D97706',
                        }}>
                          {row['Status']}
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 600 }}>
                          {fmtInr(row['Market Value'], true)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      <Alert severity="warning" sx={{ borderRadius: 2 }}>
        ⚠ Tax figures above are <strong>illustrative estimates</strong>. Holding periods, grandfathering clauses, and debt taxation post-April 2023 may differ. Consult a SEBI-registered financial advisor and CA for personalised advice.
      </Alert>
    </Box>
  )
}
