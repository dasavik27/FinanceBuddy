import React from 'react'
import { Box, Paper, Typography, TableContainer } from '@mui/material'

export function EmptyState({ message }: { message: string }) {
  return (
    <Box sx={{ p: 6, textAlign: 'center', color: 'text.secondary' }}>
      <Typography variant="body1">{message}</Typography>
    </Box>
  )
}

export function GlassTableContainer({ children }: { children: React.ReactNode }) {
  return (
    <TableContainer component={Paper} sx={{ 
      borderRadius: '24px', 
      bgcolor: 'rgba(255, 255, 255, 0.02)', 
      border: '1px solid rgba(255, 255, 255, 0.06)',
      overflow: 'hidden',
      boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.3)'
    }}>
      {children}
    </TableContainer>
  )
}

export function GlassHeader({ label, icon: Icon }: { label: string, icon?: React.ElementType }) {
  return (
    <Box sx={{ 
      px: 3, py: 2.5, 
      borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
      bgcolor: 'rgba(0, 0, 0, 0.2)',
      display: 'flex', alignItems: 'center', gap: 1.5 
    }}>
      {Icon && <Icon sx={{ color: 'primary.main', fontSize: 20 }} />}
      <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em', fontSize: 12 }}>
        {label}
      </Typography>
    </Box>
  )
}
