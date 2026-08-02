import React, { useEffect, useState } from 'react'
import { Box, Typography, Chip, Button } from '@mui/material'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import StarIcon from '@mui/icons-material/Star'
import ActivityIcon from '@mui/icons-material/Timeline'
import { apiClient } from '../../../shared/api/client'
import type { MarketIndex, StockSearchResult } from '../types'
import { useStockAnalyzerStore } from '../hooks/useStockAnalyzerStore'
import { fmtInr } from '../../../shared/utils/fmt'

interface MarketIndicesRibbonProps {
  onSelectStock: (stock: StockSearchResult) => void
}

export const MarketIndicesRibbon: React.FC<MarketIndicesRibbonProps> = ({ onSelectStock }) => {
  const [indices, setIndices] = useState<MarketIndex[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const { watchlist, selectedStock } = useStockAnalyzerStore()

  useEffect(() => {
    let isMounted = true
    const fetchIndices = async () => {
      try {
        const res = await apiClient.getMarketIndices()
        if (isMounted && res.indices && res.indices.length > 0) {
          setIndices(res.indices)
        }
      } catch {
        // Fallback standard levels if offline
        if (isMounted) {
          setIndices([
            { symbol: 'NIFTY 50', name: 'NIFTY 50', price: 24835.8, change: 152.4, p_change: 0.62 },
            { symbol: 'SENSEX', name: 'BSE SENSEX', price: 81455.4, change: 480.2, p_change: 0.59 },
            { symbol: 'BANK NIFTY', name: 'NIFTY BANK', price: 51220.15, change: -85.6, p_change: -0.17 },
            { symbol: 'NIFTY IT', name: 'NIFTY IT', price: 41890.3, change: 320.1, p_change: 0.77 },
          ])
        }
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    fetchIndices()
    const interval = setInterval(fetchIndices, 60000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  return (
    <Box sx={{ mb: 3 }}>
      {/* Top Market Indices Ribbon */}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, gap: 1.5, mb: 2 }}>
        {(loading && indices.length === 0
          ? [1, 2, 3, 4].map((n) => ({
              symbol: `INDEX_${n}`,
              name: 'Loading...',
              price: 0,
              change: 0,
              p_change: 0,
            }))
          : indices
        ).map((idx, i) => {
          const isUp = idx.change >= 0
          return (
            <Box
              key={idx.symbol || i}
              sx={{
                p: 1.75,
                bgcolor: 'rgba(15,23,42,0.65)',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '14px',
                backdropFilter: 'blur(10px)',
                transition: 'all 0.2s ease',
                '&:hover': {
                  borderColor: 'rgba(255,255,255,0.12)',
                  bgcolor: 'rgba(15,23,42,0.85)',
                },
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                <Typography sx={{ color: '#94A3B8', fontSize: '0.74rem', fontWeight: 700, letterSpacing: '0.04em' }}>
                  {idx.symbol}
                </Typography>
                <ActivityIcon sx={{ color: '#64748B', fontSize: '0.9rem' }} />
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mt: 0.5 }}>
                <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '0.98rem', fontFamily: 'monospace' }}>
                  {idx.price > 0
                    ? idx.price.toLocaleString('en-IN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })
                    : '—'}
                </Typography>
                <Typography
                  sx={{
                    color: isUp ? '#10B981' : '#EF4444',
                    fontWeight: 700,
                    fontSize: '0.75rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.2,
                  }}
                >
                  {isUp ? <TrendingUpIcon sx={{ fontSize: '0.8rem' }} /> : <TrendingDownIcon sx={{ fontSize: '0.8rem' }} />}
                  {isUp ? '+' : ''}
                  {idx.p_change.toFixed(2)}%
                </Typography>
              </Box>
            </Box>
          )
        })}
      </Box>

      {/* Watchlist Quick Pills */}
      {watchlist && watchlist.length > 0 && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, overflowX: 'auto', pb: 0.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: '#94A3B8', fontSize: '0.75rem', fontWeight: 600, flexShrink: 0, pl: 0.5 }}>
            <StarIcon sx={{ color: '#F59E0B', fontSize: '0.95rem' }} />
            <span>Watchlist:</span>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
            {watchlist.map((sym: string) => {
              const isSelected = selectedStock?.symbol === sym
              return (
                <Button
                  key={sym}
                  size="small"
                  onClick={() =>
                    onSelectStock({
                      symbol: sym,
                      name: sym,
                    })
                  }
                  sx={{
                    px: 1.5,
                    py: 0.3,
                    borderRadius: '8px',
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: isSelected ? '#fff' : '#94A3B8',
                    bgcolor: isSelected ? 'rgba(16,185,129,0.25)' : 'rgba(255,255,255,0.04)',
                    border: isSelected ? '1px solid #10B981' : '1px solid rgba(255,255,255,0.06)',
                    '&:hover': {
                      bgcolor: 'rgba(255,255,255,0.08)',
                      color: '#fff',
                      borderColor: 'rgba(16,185,129,0.5)',
                    },
                  }}
                >
                  {sym}
                </Button>
              )
            })}
          </Box>
        </Box>
      )}
    </Box>
  )
}
