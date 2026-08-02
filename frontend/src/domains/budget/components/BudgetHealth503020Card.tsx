import React, { useState } from 'react'
import { 
  Box, Typography, Card, Grid, Chip, LinearProgress, 
  Button, IconButton, Tooltip, Collapse, Divider, Stack 
} from '@mui/material'
import ShieldIcon from '@mui/icons-material/Shield'
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import SportsEsportsIcon from '@mui/icons-material/SportsEsports'

interface CategoryItem {
  name: string
  amount: number
}

interface BucketData {
  amount: number
  percentage: number
  target_pct: number
  target_amount: number
  status: 'optimal' | 'warning' | 'critical'
  categories: CategoryItem[]
  direct_investments?: number
  surplus_savings?: number
}

interface Budget503020Data {
  health_score: number
  base_amount: number
  base_type: 'income' | 'expense'
  needs: BucketData
  wants: BucketData
  investments: BucketData
  transfers_amount: number
  recommendations: string[]
}

interface BudgetHealth503020CardProps {
  data?: Budget503020Data
  onCategoryClick?: (categoryName: string) => void
}

/*
 * The three helpers below were defined inside the component, so every render rebuilt
 * three closures and - for getBucketStatusUI - three fresh object literals each
 * containing a fresh React element. They are pure functions of a number or a string
 * with no access to props or state, and this component re-renders on every filter
 * change, so none of that allocation bought anything.
 *
 * The status objects are frozen constants rather than built per call: there are
 * exactly six possible results (three statuses x is-investments), so they can all
 * exist once.
 */

const SCORE_COLORS: [number, string][] = [
  [80, '#10b981'],
  [60, '#38bdf8'],
  [45, '#f59e0b'],
]

function getScoreColor(score: number): string {
  for (const [floor, color] of SCORE_COLORS) if (score >= floor) return color
  return '#ef4444'
}

interface ScoreBadge { label: string; color: string; bg: string; border: string }

/* The threshold is kept beside the badge rather than inside it: the returned object is
 * spread into styles, and a stray `min` key riding along is the kind of thing that
 * ends up on a DOM node. */
const CRITICAL_BADGE: ScoreBadge = {
  label: '🔴 Overspending / Needs Heavy', color: '#f87171', bg: 'rgba(248, 113, 113, 0.15)', border: 'rgba(248, 113, 113, 0.3)',
}

const SCORE_BADGES: { min: number; badge: ScoreBadge }[] = [
  { min: 85, badge: { label: '🌟 Golden Balance',      color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.3)' } },
  { min: 70, badge: { label: '🟢 Healthy Budget',      color: '#34d399', bg: 'rgba(52, 211, 153, 0.15)', border: 'rgba(52, 211, 153, 0.3)' } },
  { min: 50, badge: { label: '🟡 Discretionary Creep', color: '#fbbf24', bg: 'rgba(251, 191, 36, 0.15)', border: 'rgba(251, 191, 36, 0.3)' } },
]

/* `?? CRITICAL_BADGE` rather than a -Infinity sentinel band: `NaN >= -Infinity` is
 * false, so a sentinel makes find() return undefined for NaN where the original
 * if/else chain fell through to critical - and the caller reads badge.label
 * unguarded. */
function getScoreBadge(score: number): ScoreBadge {
  return SCORE_BADGES.find(b => score >= b.min)?.badge ?? CRITICAL_BADGE
}

// Built once. The icon elements in particular were previously re-created on every
// render of every bucket.
const OPTIMAL_ICON  = <CheckCircleIcon style={{ fontSize: 13, color: '#34d399' }} />
const WARNING_ICON  = <WarningAmberIcon style={{ fontSize: 13, color: '#fbbf24' }} />
const CRITICAL_ICON = <ErrorOutlineIcon style={{ fontSize: 13, color: '#f87171' }} />

const BUCKET_STATUS_UI = {
  optimal:  { icon: OPTIMAL_ICON,  color: '#34d399', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.3)',
              label: 'Within Limit',    investmentsLabel: 'Target Achieved' },
  warning:  { icon: WARNING_ICON,  color: '#fbbf24', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.3)',
              label: 'Near Limit',      investmentsLabel: 'Moderate Saving' },
  critical: { icon: CRITICAL_ICON, color: '#f87171', bg: 'rgba(239, 68, 68, 0.12)',  border: 'rgba(239, 68, 68, 0.3)',
              label: 'Over Target',     investmentsLabel: 'Under-saving' },
} as const

function getBucketStatusUI(status: string, isInvestments = false) {
  const ui = BUCKET_STATUS_UI[status as keyof typeof BUCKET_STATUS_UI] ?? BUCKET_STATUS_UI.critical
  // investmentsLabel is destructured out, not spread through: the result is read for
  // its label/colour/bg/border, and an extra key riding along is how internal naming
  // leaks into a DOM attribute later.
  const { investmentsLabel, ...rest } = ui
  return { ...rest, label: isInvestments ? investmentsLabel : ui.label }
}

function BudgetHealth503020Card({ data, onCategoryClick }: BudgetHealth503020CardProps) {
  const [showExplanation, setShowExplanation] = useState(false)

  if (!data) return null

  const { health_score, base_amount, base_type, needs, wants, investments, recommendations } = data

  const badge = getScoreBadge(health_score)
  const scoreColor = getScoreColor(health_score)

  const needsUI = getBucketStatusUI(needs.status)
  const wantsUI = getBucketStatusUI(wants.status)
  const invUI = getBucketStatusUI(investments.status, true)

  return (
    <Card sx={{ 
      p: { xs: 2.5, md: 3 }, 
      mb: 4, 
      background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.6) 100%)', 
      border: '1px solid rgba(255, 255, 255, 0.08)', 
      borderRadius: '20px',
      boxShadow: '0 12px 36px 0 rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
      backdropFilter: 'blur(16px)'
    }}>
      {/* Top Header Row */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2.5, flexWrap: 'wrap', gap: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box sx={{ p: 1.2, borderRadius: '14px', background: 'rgba(99, 102, 241, 0.15)', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#818cf8', display: 'flex', alignItems: 'center' }}>
            <EmojiEventsIcon fontSize="medium" />
          </Box>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Typography variant="h6" sx={{ fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.01em' }}>
                50 / 30 / 20 Budget Health Evaluation
              </Typography>
              <Chip 
                label={badge.label} 
                size="small" 
                sx={{ backgroundColor: badge.bg, color: badge.color, border: `1px solid ${badge.border}`, fontWeight: 800, fontSize: '0.74rem' }} 
              />
            </Box>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 500, mt: 0.2, display: 'block' }}>
              Benchmarked against {base_type === 'income' ? `Total Net Inflow (₹${base_amount.toLocaleString('en-IN')})` : `Total Outflow Spends (₹${base_amount.toLocaleString('en-IN')})`}
            </Typography>
          </Box>
        </Box>

        {/* Health Score Pill & Info Action */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, ml: { xs: 0, sm: 'auto' } }}>
          <Box sx={{ 
            px: 2, py: 0.8, 
            background: 'rgba(255, 255, 255, 0.04)', 
            border: `1px solid ${scoreColor}40`, 
            borderRadius: '14px', 
            textAlign: 'right',
            display: 'flex',
            alignItems: 'center',
            gap: 1.2
          }}>
            <Box>
              <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', fontSize: '0.66rem', fontWeight: 700, letterSpacing: 0.5 }}>HEALTH SCORE</Typography>
              <Typography variant="h5" sx={{ fontWeight: 800, color: scoreColor, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
                {health_score}<span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>/100</span>
              </Typography>
            </Box>
          </Box>

          <IconButton 
            size="small" 
            onClick={() => setShowExplanation(!showExplanation)}
            title="What is the 50/30/20 Rule?"
            sx={{ 
              color: '#94a3b8', 
              backgroundColor: 'rgba(255, 255, 255, 0.04)', 
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '12px',
              p: 0.9,
              '&:hover': { color: '#fff', backgroundColor: 'rgba(255, 255, 255, 0.1)', borderColor: 'rgba(255, 255, 255, 0.15)' } 
            }}
          >
            <InfoOutlinedIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      {/* Explanation Banner (Collapsible) */}
      <Collapse in={showExplanation}>
        <Box sx={{ p: 2, mb: 2.5, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)', borderRadius: 2.5 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#a5b4fc', mb: 0.5 }}>
            💡 What is the 50 / 30 / 20 Financial Rule?
          </Typography>
          <Typography variant="body2" sx={{ color: '#cbd5e1', fontSize: '0.82rem', lineHeight: 1.5 }}>
            A gold-standard personal finance framework: allocate up to <strong>50% for Needs</strong> (Rent, Utilities, EMIs, Groceries, Medical), up to <strong>30% for Wants</strong> (Dining, Entertainment, Shopping, Travel), and at least <strong>20% for Investments & Savings</strong> (SIPs, Mutual Funds, Stocks, Emergency Fund).
          </Typography>
        </Box>
      </Collapse>

      {/* 3 Core Evaluation Bucket Cards */}
      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        
        {/* 1. 🛡️ NEEDS (50% TARGET) */}
        <Grid item xs={12} md={4}>
          <Box sx={{ 
            p: 2.5, 
            height: '100%',
            background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.05) 0%, rgba(15, 23, 42, 0.6) 100%)', 
            border: '1px solid',
            borderColor: needs.status === 'optimal' ? 'rgba(56, 189, 248, 0.3)' : needsUI.border, 
            borderRadius: '16px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            transition: 'all 0.25s ease',
            '&:hover': {
              transform: 'translateY(-3px)',
              borderColor: 'rgba(56, 189, 248, 0.5)',
              boxShadow: '0 12px 28px rgba(56, 189, 248, 0.12)'
            }
          }}>
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ p: 0.6, borderRadius: '8px', bgcolor: 'rgba(56, 189, 248, 0.15)', display: 'flex' }}>
                    <ShieldIcon sx={{ color: '#38bdf8', fontSize: 18 }} />
                  </Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#f8fafc', fontSize: '0.88rem' }}>
                    Needs (Essentials)
                  </Typography>
                </Box>
                <Chip 
                  label={needsUI.label} 
                  icon={needsUI.icon} 
                  size="small" 
                  sx={{ backgroundColor: needsUI.bg, color: needsUI.color, border: `1px solid ${needsUI.border}`, fontWeight: 800, fontSize: '0.7rem', height: 24 }} 
                />
              </Box>

              {/* Amount & Target Numbers */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mt: 1.5, mb: 0.5 }}>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#38bdf8', fontVariantNumeric: 'tabular-nums' }}>
                  {needs.percentage.toFixed(1)}%
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 800, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>
                  ₹{needs.amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </Typography>
              </Box>

              <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 1.2, fontWeight: 500 }}>
                Target: Max 50.0% (₹{needs.target_amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })})
              </Typography>

              {/* Progress Bar with 50% Threshold */}
              <Box sx={{ position: 'relative', my: 1.5 }}>
                <LinearProgress 
                  variant="determinate" 
                  value={Math.min(100, (needs.percentage / 50) * 50)} 
                  sx={{ 
                    height: 8, 
                    borderRadius: 4, 
                    backgroundColor: 'rgba(255,255,255,0.06)',
                    '& .MuiLinearProgress-bar': { backgroundColor: needs.status === 'optimal' ? '#38bdf8' : needsUI.color, borderRadius: 4 }
                  }} 
                />
              </Box>

              {/* Variance Tag */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.74rem', fontWeight: 500 }}>Variance vs Target:</Typography>
                <Typography variant="caption" sx={{ fontWeight: 800, color: needs.percentage <= 50 ? '#34d399' : '#f87171', fontSize: '0.74rem' }}>
                  {needs.percentage <= 50 
                    ? `₹${(needs.target_amount - needs.amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cushion` 
                    : `+₹${(needs.amount - needs.target_amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Over Budget`}
                </Typography>
              </Box>
            </Box>

            {/* Top Sub-categories */}
            {needs.categories && needs.categories.length > 0 && (
              <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, display: 'block', mb: 0.8, fontSize: '0.7rem' }}>
                  Key Categories:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.6 }}>
                  {needs.categories.slice(0, 3).map((c) => (
                    <Chip 
                      key={c.name}
                      label={`${c.name}: ₹${c.amount >= 1000 ? `${(c.amount / 1000).toFixed(0)}k` : c.amount}`} 
                      size="small"
                      clickable={Boolean(onCategoryClick)}
                      onClick={() => onCategoryClick && onCategoryClick(c.name)}
                      sx={{ 
                        backgroundColor: 'rgba(56, 189, 248, 0.12)', 
                        border: '1px solid rgba(56, 189, 248, 0.25)',
                        color: '#7dd3fc', 
                        fontSize: '0.7rem', 
                        fontWeight: 600,
                        height: 22,
                        '&:hover': { backgroundColor: 'rgba(56, 189, 248, 0.22)' }
                      }} 
                    />
                  ))}
                </Box>
              </Box>
            )}
          </Box>
        </Grid>

        {/* 2. 🎯 WANTS (30% TARGET) */}
        <Grid item xs={12} md={4}>
          <Box sx={{ 
            p: 2.5, 
            height: '100%',
            background: 'linear-gradient(135deg, rgba(244, 114, 182, 0.05) 0%, rgba(15, 23, 42, 0.6) 100%)', 
            border: '1px solid',
            borderColor: wants.status === 'optimal' ? 'rgba(244, 114, 182, 0.3)' : wantsUI.border, 
            borderRadius: '16px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            transition: 'all 0.25s ease',
            '&:hover': {
              transform: 'translateY(-3px)',
              borderColor: 'rgba(244, 114, 182, 0.5)',
              boxShadow: '0 12px 28px rgba(244, 114, 182, 0.12)'
            }
          }}>
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ p: 0.6, borderRadius: '8px', bgcolor: 'rgba(244, 114, 182, 0.15)', display: 'flex' }}>
                    <SportsEsportsIcon sx={{ color: '#f472b6', fontSize: 18 }} />
                  </Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#f8fafc', fontSize: '0.88rem' }}>
                    Wants (Lifestyle)
                  </Typography>
                </Box>
                <Chip 
                  label={wantsUI.label} 
                  icon={wantsUI.icon} 
                  size="small" 
                  sx={{ backgroundColor: wantsUI.bg, color: wantsUI.color, border: `1px solid ${wantsUI.border}`, fontWeight: 800, fontSize: '0.7rem', height: 24 }} 
                />
              </Box>

              {/* Amount & Target Numbers */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mt: 1.5, mb: 0.5 }}>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#f472b6', fontVariantNumeric: 'tabular-nums' }}>
                  {wants.percentage.toFixed(1)}%
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 800, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>
                  ₹{wants.amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </Typography>
              </Box>

              <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 1.2, fontWeight: 500 }}>
                Target: Max 30.0% (₹{wants.target_amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })})
              </Typography>

              {/* Progress Bar */}
              <Box sx={{ position: 'relative', my: 1.5 }}>
                <LinearProgress 
                  variant="determinate" 
                  value={Math.min(100, (wants.percentage / 30) * 30)} 
                  sx={{ 
                    height: 8, 
                    borderRadius: 4, 
                    backgroundColor: 'rgba(255,255,255,0.06)',
                    '& .MuiLinearProgress-bar': { backgroundColor: wants.status === 'optimal' ? '#f472b6' : wantsUI.color, borderRadius: 4 }
                  }} 
                />
              </Box>

              {/* Variance Tag */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.74rem', fontWeight: 500 }}>Variance vs Target:</Typography>
                <Typography variant="caption" sx={{ fontWeight: 800, color: wants.percentage <= 30 ? '#34d399' : '#f87171', fontSize: '0.74rem' }}>
                  {wants.percentage <= 30 
                    ? `₹${(wants.target_amount - wants.amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Within Limit` 
                    : `+₹${(wants.amount - wants.target_amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Overspending`}
                </Typography>
              </Box>
            </Box>

            {/* Top Sub-categories */}
            {wants.categories && wants.categories.length > 0 && (
              <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, display: 'block', mb: 0.8, fontSize: '0.7rem' }}>
                  Key Categories:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.6 }}>
                  {wants.categories.slice(0, 3).map((c) => (
                    <Chip 
                      key={c.name}
                      label={`${c.name}: ₹${c.amount >= 1000 ? `${(c.amount / 1000).toFixed(0)}k` : c.amount}`} 
                      size="small"
                      clickable={Boolean(onCategoryClick)}
                      onClick={() => onCategoryClick && onCategoryClick(c.name)}
                      sx={{ 
                        backgroundColor: 'rgba(244, 114, 182, 0.12)', 
                        border: '1px solid rgba(244, 114, 182, 0.25)',
                        color: '#fbcfe8', 
                        fontSize: '0.7rem', 
                        fontWeight: 600,
                        height: 22,
                        '&:hover': { backgroundColor: 'rgba(244, 114, 182, 0.22)' }
                      }} 
                    />
                  ))}
                </Box>
              </Box>
            )}
          </Box>
        </Grid>

        {/* 3. 📈 INVESTMENTS & SAVINGS (20% TARGET) */}
        <Grid item xs={12} md={4}>
          <Box sx={{ 
            p: 2.5, 
            height: '100%',
            background: 'linear-gradient(135deg, rgba(52, 211, 153, 0.05) 0%, rgba(15, 23, 42, 0.6) 100%)', 
            border: '1px solid',
            borderColor: investments.status === 'optimal' ? 'rgba(52, 211, 153, 0.3)' : invUI.border, 
            borderRadius: '16px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            transition: 'all 0.25s ease',
            '&:hover': {
              transform: 'translateY(-3px)',
              borderColor: 'rgba(52, 211, 153, 0.5)',
              boxShadow: '0 12px 28px rgba(52, 211, 153, 0.12)'
            }
          }}>
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ p: 0.6, borderRadius: '8px', bgcolor: 'rgba(52, 211, 153, 0.15)', display: 'flex' }}>
                    <TrendingUpIcon sx={{ color: '#34d399', fontSize: 18 }} />
                  </Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#f8fafc', fontSize: '0.88rem' }}>
                    Investments & Savings
                  </Typography>
                </Box>
                <Chip 
                  label={invUI.label} 
                  icon={invUI.icon} 
                  size="small" 
                  sx={{ backgroundColor: invUI.bg, color: invUI.color, border: `1px solid ${invUI.border}`, fontWeight: 800, fontSize: '0.7rem', height: 24 }} 
                />
              </Box>

              {/* Amount & Target Numbers */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mt: 1.5, mb: 0.5 }}>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#34d399', fontVariantNumeric: 'tabular-nums' }}>
                  {investments.percentage.toFixed(1)}%
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 800, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>
                  ₹{investments.amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </Typography>
              </Box>

              <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 1.2, fontWeight: 500 }}>
                Target: Min 20.0% (₹{investments.target_amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })})
              </Typography>

              {/* Progress Bar */}
              <Box sx={{ position: 'relative', my: 1.5 }}>
                <LinearProgress 
                  variant="determinate" 
                  value={Math.min(100, (investments.percentage / 20) * 100)} 
                  sx={{ 
                    height: 8, 
                    borderRadius: 4, 
                    backgroundColor: 'rgba(255,255,255,0.06)',
                    '& .MuiLinearProgress-bar': { backgroundColor: investments.status === 'optimal' ? '#34d399' : invUI.color, borderRadius: 4 }
                  }} 
                />
              </Box>

              {/* Variance Tag */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.74rem', fontWeight: 500 }}>Variance vs Target:</Typography>
                <Typography variant="caption" sx={{ fontWeight: 800, color: investments.percentage >= 20 ? '#34d399' : '#f87171', fontSize: '0.74rem' }}>
                  {investments.percentage >= 20 
                    ? `+₹${(investments.amount - investments.target_amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Wealth Acceleration` 
                    : `₹${(investments.target_amount - investments.amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Below 20% Goal`}
                </Typography>
              </Box>
            </Box>

            {/* Direct SIPs vs Surplus Flow breakdown */}
            <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, display: 'block', mb: 0.8, fontSize: '0.7rem' }}>
                Composition:
              </Typography>
              <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap' }}>
                <Chip 
                  label={`SIPs/Demat: ₹${(investments.direct_investments || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`} 
                  size="small"
                  sx={{ 
                    backgroundColor: 'rgba(52, 211, 153, 0.12)', 
                    border: '1px solid rgba(52, 211, 153, 0.25)', 
                    color: '#6ee7b7', 
                    fontSize: '0.7rem', 
                    fontWeight: 600,
                    height: 22 
                  }} 
                />
                <Chip 
                  label={`Cash Surplus: ₹${(investments.surplus_savings || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`} 
                  size="small"
                  sx={{ 
                    backgroundColor: 'rgba(52, 211, 153, 0.12)', 
                    border: '1px solid rgba(52, 211, 153, 0.25)', 
                    color: '#6ee7b7', 
                    fontSize: '0.7rem', 
                    fontWeight: 600,
                    height: 22 
                  }} 
                />
              </Box>
            </Box>
          </Box>
        </Grid>
      </Grid>

      {/* Target vs Actual Visual Allocation Strip */}
      <Box sx={{ p: 2, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 2.5, mb: 2.5 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, fontSize: '0.7rem' }}>
            Macro Split: Target (50 / 30 / 20) vs Actual
          </Typography>
          <Typography variant="caption" sx={{ color: '#cbd5e1', fontWeight: 600, fontSize: '0.72rem' }}>
            🛡️ {needs.percentage.toFixed(0)}% Needs • 🎯 {wants.percentage.toFixed(0)}% Wants • 📈 {investments.percentage.toFixed(0)}% Invested
          </Typography>
        </Box>
        
        {/* Actual Bar */}
        <Box sx={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.05)', mb: 0.8 }}>
          <Box sx={{ width: `${Math.min(100, needs.percentage)}%`, backgroundColor: '#38bdf8' }} title={`Needs: ${needs.percentage.toFixed(1)}%`} />
          <Box sx={{ width: `${Math.min(100, wants.percentage)}%`, backgroundColor: '#f472b6' }} title={`Wants: ${wants.percentage.toFixed(1)}%`} />
          <Box sx={{ width: `${Math.min(100, investments.percentage)}%`, backgroundColor: '#34d399' }} title={`Investments: ${investments.percentage.toFixed(1)}%`} />
        </Box>

        {/* Benchmark Marker Guide */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', px: 0.5 }}>
          <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem' }}>0%</Typography>
          <Typography variant="caption" sx={{ color: '#38bdf8', fontSize: '0.65rem' }}>50% Needs Limit</Typography>
          <Typography variant="caption" sx={{ color: '#f472b6', fontSize: '0.65rem' }}>80% Wants Limit</Typography>
          <Typography variant="caption" sx={{ color: '#34d399', fontSize: '0.65rem' }}>100% (20% Savings)</Typography>
        </Box>
      </Box>

      {/* Actionable Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <Box sx={{ p: 2, background: 'rgba(99, 102, 241, 0.04)', border: '1px solid rgba(99, 102, 241, 0.15)', borderRadius: 2.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <AutoAwesomeIcon sx={{ color: '#818cf8', fontSize: 16 }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#a5b4fc', fontSize: '0.8rem' }}>
              Actionable AI Budgeting Verdict & Recommendations
            </Typography>
          </Box>
          <Stack spacing={0.8}>
            {recommendations.map((rec) => (
              <Box key={rec} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                <Typography variant="caption" sx={{ color: '#818cf8', fontWeight: 800, mt: '2px' }}>•</Typography>
                <Typography variant="body2" sx={{ color: '#cbd5e1', fontSize: '0.8rem', lineHeight: 1.4 }}>
                  {rec}
                </Typography>
              </Box>
            ))}
          </Stack>
        </Box>
      )}
    </Card>
  )
}

// `data` is a slice of the overview query's result and `onCategoryClick` is stable at
// the call site, so this only re-renders when the 50/30/20 figures actually change.
export default React.memo(BudgetHealth503020Card)
