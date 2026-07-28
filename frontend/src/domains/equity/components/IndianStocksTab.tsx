import { Box, Typography, Paper, Alert } from '@mui/material'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { SectionHeader } from '../ui'

export default function IndianStocksTab() {
  return (
    <Box sx={{ pb: 6 }}>
      <SectionHeader 
        title="Indian Stocks" 
        subtitle="Equity portfolio analysis and tracking" 
      />

      <Paper className="glass" sx={{ p: 5, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center', mt: 4 }}>
        <Box sx={{ display: 'inline-flex', p: 3, borderRadius: '50%', background: 'rgba(99, 102, 241, 0.1)', mb: 3 }}>
          <InfoOutlinedIcon sx={{ fontSize: 48, color: 'primary.main' }} />
        </Box>
        <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff', mb: 2 }}>
          Coming Soon
        </Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 600, mx: 'auto', lineHeight: 1.6 }}>
          We are currently integrating direct equity data feeds. Soon you will be able to track your Indian stocks, perform deep fundamental analysis, and see real-time performance metrics right here in Finance Buddy.
        </Typography>
      </Paper>
    </Box>
  )
}
