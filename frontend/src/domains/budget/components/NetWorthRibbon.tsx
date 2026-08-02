import React, { useMemo, useState } from 'react'
import { Box, Button, Card, Chip, Collapse, IconButton, Skeleton, Typography, alpha } from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'

import { budgetErrorDetail, useBudgetNetWorth } from '../hooks/useBudget'
import type { BudgetNetWorth } from '../types'

/**
 * Net worth across every domain, rendered as a tier-1 fintech hero card.
 *
 * All figures are humanized (e.g. "HDFC:savings:-" -> "HDFC Bank (Savings)"),
 * and domains receive dedicated color-coded badges and icons.
 */

const CARD_SX = {
  p: { xs: 2.5, md: 3 },
  mb: 3.5,
  borderRadius: '20px',
  background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.6) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  boxShadow: '0 12px 36px 0 rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
  backdropFilter: 'blur(16px)',
  color: '#e2e8f0',
} as const

const ERROR_CARD_SX = {
  ...CARD_SX,
  py: 2,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 2,
  flexWrap: 'wrap',
  background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(15, 23, 42, 0.8) 100%)',
  border: '1px solid rgba(239, 68, 68, 0.3)',
} as const

const LABEL_SX = {
  color: '#94a3b8',
  fontSize: '0.72rem',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: 0.8,
} as const

function money(value: number): string {
  const magnitude = Math.abs(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })
  return `${value < 0 ? '-' : ''}₹${magnitude}`
}

/** Formats raw backend labels like "HDFC:savings:-" or "mutual_funds" into friendly strings */
function formatAccountLabel(rawLabel: string, domain: string): { title: string; subtitle: string; icon: React.ReactNode } {
  if (domain === 'mutual_funds') {
    return {
      title: 'Mutual Funds',
      subtitle: 'Portfolio Folios',
      icon: <TrendingUpIcon sx={{ fontSize: 16, color: '#34d399' }} />,
    }
  }
  if (domain === 'equity') {
    return {
      title: 'Indian Stocks',
      subtitle: 'Demat Holdings',
      icon: <ShowChartIcon sx={{ fontSize: 16, color: '#a78bfa' }} />,
    }
  }

  // Handle bank tags like "HDFC:savings:-", "ICICI:credit:1234", "SBI:current:45"
  const parts = rawLabel.split(':')
  if (parts.length >= 2) {
    const bankName = parts[0].toUpperCase()
    const type = parts[1].charAt(0).toUpperCase() + parts[1].slice(1).toLowerCase()
    const last4 = parts[2] && parts[2] !== '-' && parts[2] !== 'unknown' ? ` ••${parts[2]}` : ''
    const isCredit = parts[1].toLowerCase() === 'credit'
    return {
      title: `${bankName} Bank`,
      subtitle: `${type} Account${last4}`,
      icon: isCredit ? (
        <CreditCardIcon sx={{ fontSize: 16, color: '#f87171' }} />
      ) : (
        <AccountBalanceIcon sx={{ fontSize: 16, color: '#38bdf8' }} />
      ),
    }
  }

  return {
    title: rawLabel.replace(/_/g, ' '),
    subtitle: domain.replace(/_/g, ' '),
    icon: <AccountBalanceWalletIcon sx={{ fontSize: 16, color: '#94a3b8' }} />,
  }
}

const DOMAIN_STYLES: Record<string, { label: string; color: string; bg: string; border: string }> = {
  budget: {
    label: 'Bank Account',
    color: '#38bdf8',
    bg: 'rgba(56, 189, 248, 0.12)',
    border: 'rgba(56, 189, 248, 0.25)',
  },
  mutual_funds: {
    label: 'Mutual Funds',
    color: '#34d399',
    bg: 'rgba(52, 211, 153, 0.12)',
    border: 'rgba(52, 211, 153, 0.25)',
  },
  equity: {
    label: 'Stocks',
    color: '#a78bfa',
    bg: 'rgba(167, 139, 250, 0.12)',
    border: 'rgba(167, 139, 250, 0.25)',
  },
}

interface BreakdownListProps {
  title: string
  items: BudgetNetWorth['breakdown']
  negative: boolean
}

function BreakdownList({ title, items, negative }: BreakdownListProps) {
  if (items.length === 0) return null

  return (
    <Box sx={{ flex: '1 1 320px', minWidth: 280 }}>
      <Typography sx={{ ...LABEL_SX, mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <span>{title}</span>
        <Chip
          label={items.length}
          size="small"
          sx={{
            height: 18,
            fontSize: '0.65rem',
            fontWeight: 800,
            bgcolor: 'rgba(255, 255, 255, 0.08)',
            color: '#cbd5e1',
          }}
        />
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.2 }}>
        {items.map((item) => {
          const { title: itemTitle, subtitle, icon } = formatAccountLabel(item.label, item.domain)
          const domainStyle = DOMAIN_STYLES[item.domain] || {
            label: item.domain,
            color: '#94a3b8',
            bg: 'rgba(148, 163, 184, 0.12)',
            border: 'rgba(148, 163, 184, 0.2)',
          }

          return (
            <Box
              key={`${item.domain}-${item.label}`}
              sx={{
                p: 1.5,
                borderRadius: '12px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1.5,
                transition: 'all 0.2s ease',
                '&:hover': {
                  background: 'rgba(255, 255, 255, 0.06)',
                  borderColor: 'rgba(255, 255, 255, 0.12)',
                  transform: 'translateY(-1px)',
                },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
                <Box
                  sx={{
                    p: 1,
                    borderRadius: '10px',
                    bgcolor: domainStyle.bg,
                    border: `1px solid ${domainStyle.border}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  {icon}
                </Box>
                <Box sx={{ minWidth: 0 }}>
                  <Typography
                    sx={{
                      color: '#f8fafc',
                      fontSize: '0.88rem',
                      fontWeight: 700,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {itemTitle}
                  </Typography>
                  <Typography
                    sx={{
                      color: '#94a3b8',
                      fontSize: '0.75rem',
                      fontWeight: 500,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {subtitle}
                  </Typography>
                </Box>
              </Box>

              <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                <Typography
                  sx={{
                    fontSize: '0.92rem',
                    fontWeight: 800,
                    color: negative ? '#f87171' : '#34d399',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {money(negative ? -Math.abs(item.value) : item.value)}
                </Typography>
                <Chip
                  size="small"
                  label={domainStyle.label}
                  sx={{
                    height: 16,
                    fontSize: '0.6rem',
                    fontWeight: 700,
                    bgcolor: domainStyle.bg,
                    color: domainStyle.color,
                    border: `1px solid ${domainStyle.border}`,
                    mt: 0.3,
                  }}
                />
              </Box>
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}

const MemoBreakdownList = React.memo(BreakdownList)

interface NetWorthRibbonProps {
  sessionId: string
}

function NetWorthRibbon({ sessionId }: NetWorthRibbonProps) {
  const { data, isPending, isError, error, refetch } = useBudgetNetWorth(sessionId)
  const [showBreakdown, setShowBreakdown] = useState(true)

  const breakdown = data?.breakdown
  const { assets: assetItems, liabilities: liabilityItems } = useMemo(() => {
    const grouped: { assets: BudgetNetWorth['breakdown']; liabilities: BudgetNetWorth['breakdown'] } = {
      assets: [],
      liabilities: [],
    }
    for (const item of breakdown ?? []) {
      if (item.kind === 'liability') grouped.liabilities.push(item)
      else grouped.assets.push(item)
    }
    return grouped
  }, [breakdown])

  if (isPending) {
    return (
      <Skeleton
        variant="rounded"
        height={180}
        sx={{ mb: 3.5, borderRadius: '20px', bgcolor: 'rgba(148,163,184,0.08)' }}
      />
    )
  }

  if (isError || !data) {
    return (
      <Card sx={ERROR_CARD_SX}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <WarningAmberIcon sx={{ color: '#f87171', fontSize: 22 }} />
          <Typography sx={{ color: '#fca5a5', fontSize: '0.88rem', fontWeight: 600 }}>
            Net worth unavailable — {budgetErrorDetail(error, 'could not be calculated.')}
          </Typography>
        </Box>
        <Button
          size="small"
          variant="outlined"
          onClick={() => refetch()}
          sx={{
            color: '#fca5a5',
            borderColor: 'rgba(239, 68, 68, 0.4)',
            textTransform: 'none',
            fontWeight: 700,
            '&:hover': { borderColor: '#ef4444', bgcolor: 'rgba(239, 68, 68, 0.1)' },
          }}
        >
          Retry
        </Button>
      </Card>
    )
  }

  const assetTotal = Math.abs(data.assets)
  const liabilityTotal = Math.abs(data.liabilities)
  const barTotal = assetTotal + liabilityTotal
  const assetPct = barTotal > 0 ? (assetTotal / barTotal) * 100 : 100

  const missing = data.unavailable_domains ?? []

  return (
    <Card sx={CARD_SX}>
      {/* Top Main Section */}
      <Box
        sx={{
          display: 'flex',
          alignItems: { xs: 'flex-start', md: 'center' },
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 3,
        }}
      >
        {/* Left Hero Figure */}
        <Box>
          <Typography sx={LABEL_SX}>Total Net Worth</Typography>
          <Typography
            sx={{
              fontWeight: 800,
              fontSize: { xs: '2rem', md: '2.4rem' },
              lineHeight: 1.15,
              mt: 0.5,
              background: data.net_worth >= 0
                ? 'linear-gradient(135deg, #34d399 0%, #10b981 100%)'
                : 'linear-gradient(135deg, #f87171 0%, #ef4444 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              letterSpacing: '-0.02em',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {money(data.net_worth)}
          </Typography>
        </Box>

        {/* Right Sub-metrics Pill Grid */}
        <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
          <Box
            sx={{
              p: 1.5,
              px: 2,
              borderRadius: '14px',
              bgcolor: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.2)',
              minWidth: 120,
            }}
          >
            <Typography sx={{ ...LABEL_SX, color: '#38bdf8', fontSize: '0.68rem' }}>Liquid Cash</Typography>
            <Typography sx={{ fontWeight: 800, fontSize: '1.08rem', color: '#f8fafc', mt: 0.2 }}>
              {money(data.cash)}
            </Typography>
          </Box>

          <Box
            sx={{
              p: 1.5,
              px: 2,
              borderRadius: '14px',
              bgcolor: 'rgba(167, 139, 250, 0.08)',
              border: '1px solid rgba(167, 139, 250, 0.2)',
              minWidth: 130,
            }}
          >
            <Typography sx={{ ...LABEL_SX, color: '#a78bfa', fontSize: '0.68rem' }}>Investments</Typography>
            <Typography sx={{ fontWeight: 800, fontSize: '1.08rem', color: '#f8fafc', mt: 0.2 }}>
              {money(data.investments)}
            </Typography>
          </Box>

          <Box
            sx={{
              p: 1.5,
              px: 2,
              borderRadius: '14px',
              bgcolor: data.card_debt > 0 ? 'rgba(239, 68, 68, 0.08)' : 'rgba(255, 255, 255, 0.04)',
              border: data.card_debt > 0 ? '1px solid rgba(239, 68, 68, 0.25)' : '1px solid rgba(255, 255, 255, 0.08)',
              minWidth: 120,
            }}
          >
            <Typography sx={{ ...LABEL_SX, color: data.card_debt > 0 ? '#f87171' : '#94a3b8', fontSize: '0.68rem' }}>
              Card Debt
            </Typography>
            <Typography
              sx={{
                fontWeight: 800,
                fontSize: '1.08rem',
                color: data.card_debt > 0 ? '#f87171' : '#e2e8f0',
                mt: 0.2,
              }}
            >
              {money(-Math.abs(data.card_debt))}
            </Typography>
          </Box>
        </Box>
      </Box>

      {/* Asset / Liability Gradient Track Bar */}
      {barTotal > 0 && (
        <Box sx={{ mt: 2.8 }}>
          <Box
            sx={{
              display: 'flex',
              height: 7,
              borderRadius: '6px',
              overflow: 'hidden',
              bgcolor: 'rgba(255, 255, 255, 0.06)',
            }}
          >
            <Box
              sx={{
                width: `${assetPct}%`,
                background: 'linear-gradient(90deg, #10b981 0%, #34d399 100%)',
                transition: 'width 0.6s ease',
              }}
              title={`Assets: ${money(assetTotal)}`}
            />
            {liabilityTotal > 0 && (
              <Box
                sx={{
                  width: `${100 - assetPct}%`,
                  background: 'linear-gradient(90deg, #f87171 0%, #ef4444 100%)',
                  transition: 'width 0.6s ease',
                }}
                title={`Liabilities: ${money(liabilityTotal)}`}
              />
            )}
          </Box>

          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.8, alignItems: 'center' }}>
            <Typography sx={{ color: '#34d399', fontSize: '0.78rem', fontWeight: 700 }}>
              Assets {money(assetTotal)}
            </Typography>
            <Typography sx={{ color: liabilityTotal > 0 ? '#f87171' : '#94a3b8', fontSize: '0.78rem', fontWeight: 700 }}>
              Liabilities {money(liabilityTotal)}
            </Typography>
          </Box>
        </Box>
      )}

      {/* Toggleable Breakdown Header */}
      {(assetItems.length > 0 || liabilityItems.length > 0) && (
        <Box sx={{ mt: 2.5, pt: 2, borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: showBreakdown ? 2 : 0 }}>
            <Typography sx={{ color: '#94a3b8', fontSize: '0.8rem', fontWeight: 600 }}>
              Holdings Breakdown ({assetItems.length + liabilityItems.length} accounts & assets)
            </Typography>
            <Button
              size="small"
              onClick={() => setShowBreakdown((prev) => !prev)}
              endIcon={showBreakdown ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
              sx={{
                color: '#38bdf8',
                textTransform: 'none',
                fontSize: '0.78rem',
                fontWeight: 700,
                p: 0.5,
                '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.08)' },
              }}
            >
              {showBreakdown ? 'Hide details' : 'Show details'}
            </Button>
          </Box>

          <Collapse in={showBreakdown}>
            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', mt: 1 }}>
              <MemoBreakdownList title="Asset Accounts & Holdings" items={assetItems} negative={false} />
              {liabilityItems.length > 0 && (
                <MemoBreakdownList title="Liabilities & Outstandings" items={liabilityItems} negative />
              )}
            </Box>
          </Collapse>
        </Box>
      )}

      {/* Unavailable Domains Warning */}
      {missing.length > 0 && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.2,
            mt: 2.5,
            px: 2,
            py: 1.2,
            borderRadius: '12px',
            fontSize: '0.8rem',
            color: '#fcd34d',
            bgcolor: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
          }}
        >
          <WarningAmberIcon sx={{ fontSize: 18, color: '#fcd34d', flexShrink: 0 }} />
          <span>
            Excludes {missing.join(', ').replace(/_/g, ' ')} — data could not be loaded.
          </span>
        </Box>
      )}
    </Card>
  )
}

export default React.memo(NetWorthRibbon)

