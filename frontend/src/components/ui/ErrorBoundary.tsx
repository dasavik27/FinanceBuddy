import React, { Component, ErrorInfo, ReactNode } from 'react'
import { Box, Paper, Typography, Button, alpha } from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import RefreshIcon from '@mui/icons-material/Refresh'

interface Props {
  children?: ReactNode
  fallbackMessage?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Finance Buddy UI Component Error:', error, errorInfo)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  public render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ p: 4, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
          <Paper 
            className="glass" 
            sx={{ 
              p: 5, 
              borderRadius: '32px', 
              maxWidth: 500, 
              textAlign: 'center',
              border: `1px solid ${alpha('#FF516A', 0.2)}`,
              background: `linear-gradient(135deg, ${alpha('#FF516A', 0.05)} 0%, ${alpha('#0B1326', 0.8)} 100%)`
            }}
          >
            <Box sx={{ width: 64, height: 64, borderRadius: '24px', bgcolor: alpha('#FF516A', 0.1), color: '#FF516A', display: 'flex', alignItems: 'center', justifyContent: 'center', mx: 'auto', mb: 3 }}>
              <WarningAmberIcon sx={{ fontSize: 36 }} />
            </Box>
            
            <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff', mb: 1 }}>
              Component Rendering Exception
            </Typography>
            
            <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 500, mb: 4 }}>
              {this.props.fallbackMessage || this.state.error?.message || 'An unexpected error occurred while rendering this module.'}
            </Typography>

            <Button
              variant="contained"
              startIcon={<RefreshIcon />}
              onClick={this.handleReset}
              sx={{
                borderRadius: '16px',
                py: 1.5,
                px: 4,
                fontWeight: 800,
                bgcolor: '#FF516A',
                '&:hover': { bgcolor: alpha('#FF516A', 0.8) }
              }}
            >
              RESET MODULE
            </Button>
          </Paper>
        </Box>
      )
    }

    return this.props.children
  }
}
