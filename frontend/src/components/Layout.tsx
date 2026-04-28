import { useState, ReactNode } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Box, Drawer, AppBar, Toolbar, Typography, IconButton,
  List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Divider, Select, MenuItem, FormControl, InputLabel,
  Slider, ToggleButtonGroup, ToggleButton, Tooltip,
  Autocomplete, TextField, Chip, Stack, Badge,
} from '@mui/material'
import DashboardIcon    from '@mui/icons-material/Dashboard'
import ShowChartIcon    from '@mui/icons-material/ShowChart'
import TableChartIcon   from '@mui/icons-material/TableChart'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ReceiptIcon      from '@mui/icons-material/Receipt'
import LightbulbIcon    from '@mui/icons-material/Lightbulb'
import LoopIcon         from '@mui/icons-material/Loop'
import TrendingUpIcon   from '@mui/icons-material/TrendingUp'
import LogoutIcon       from '@mui/icons-material/Logout'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import { motion }       from 'framer-motion'
import { useAppStore, useFilters, useParseData, useIsPartial } from '../store/appStore'

const DRAWER_W = 268

const NAV = [
  { label: 'Overview',      icon: <DashboardIcon />,     path: '/dashboard' },
  { label: 'Performance',   icon: <ShowChartIcon />,      path: '/dashboard/performance' },
  { label: 'Holdings',      icon: <TableChartIcon />,     path: '/dashboard/holdings' },
  { label: 'Compare',       icon: <CompareArrowsIcon />,  path: '/dashboard/compare' },
  { label: 'Tax',           icon: <ReceiptIcon />,        path: '/dashboard/tax' },
  { label: 'Smart Insights',icon: <LightbulbIcon />,      path: '/dashboard/insights' },
  { label: 'SIP Calculator',icon: <LoopIcon />,           path: '/dashboard/sip' },
]

interface Props { children: ReactNode }

export default function Layout({ children }: Props) {
  const navigate  = useNavigate()
  const location  = useLocation()
  const filters   = useFilters()
  const parseData = useParseData()
  const isPartial = useIsPartial()
  const { setFilters, clearSession } = useAppStore()

  const allCats = parseData?.categories ?? []
  const allAmcs = parseData?.amcs ?? []
  const benchmarks = parseData?.benchmarks ?? ['Nifty 50']

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>

      {/* ── Sidebar ───────────────────────────────────────────────────── */}
      <Drawer variant="permanent" sx={{ width: DRAWER_W, flexShrink: 0, '& .MuiDrawer-paper': { width: DRAWER_W, boxSizing: 'border-box' } }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', p: 2 }}>

          {/* Logo */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3, px: 1 }}>
            <Box sx={{
              width: 38, height: 38, borderRadius: '11px',
              background: 'linear-gradient(135deg, #2563EB 0%, #6D28D9 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(37,99,235,0.45)', flexShrink: 0,
            }}>
              <TrendingUpIcon sx={{ fontSize: 20, color: '#fff' }} />
            </Box>
            <Box>
              <Typography sx={{ fontSize: 16, fontWeight: 800, color: '#E2E8F0', letterSpacing: '-0.3px', lineHeight: 1.2 }}>
                FolioIQ
              </Typography>
              <Typography sx={{ fontSize: 9, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.9px' }}>
                MF Intelligence
              </Typography>
            </Box>
          </Box>

          {/* Partial CAS warning */}
          {isPartial && (
            <Box sx={{ background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 2, p: 1.5, mb: 2, display: 'flex', gap: 1 }}>
              <WarningAmberIcon sx={{ fontSize: 16, color: '#F59E0B', flexShrink: 0, mt: 0.2 }} />
              <Typography sx={{ fontSize: 11, color: '#FCD34D', lineHeight: 1.5 }}>
                Partial CAS — XIRR may be inaccurate. Download a full CAS since inception.
              </Typography>
            </Box>
          )}

          {/* Nav */}
          <List dense disablePadding>
            {NAV.map((item) => {
              const active = location.pathname === item.path ||
                (item.path !== '/dashboard' && location.pathname.startsWith(item.path))
              return (
                <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
                  <ListItemButton
                    onClick={() => navigate(item.path)}
                    sx={{
                      borderRadius: 2,
                      px: 1.5, py: 1,
                      background: active ? 'rgba(59,130,246,0.18)' : 'transparent',
                      '&:hover': { background: 'rgba(255,255,255,0.07)' },
                      transition: 'background 150ms ease',
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 36, color: active ? '#60A5FA' : '#64748B', '& svg': { fontSize: 19 } }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.label}
                      primaryTypographyProps={{
                        fontSize: 13, fontWeight: active ? 700 : 500,
                        color: active ? '#E2E8F0' : '#94A3B8',
                      }}
                    />
                    {active && (
                      <Box sx={{ width: 4, height: 4, borderRadius: '50%', background: '#60A5FA', flexShrink: 0 }} />
                    )}
                  </ListItemButton>
                </ListItem>
              )
            })}
          </List>

          <Divider sx={{ borderColor: 'rgba(255,255,255,0.07)', my: 2 }} />

          {/* Filters */}
          <Typography sx={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.9px', mb: 1.5, px: 1 }}>
            Global Filters
          </Typography>

          {/* Benchmark */}
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel sx={{ fontSize: 11, color: '#64748B' }}>Benchmark</InputLabel>
            <Select
              value={filters.benchmark}
              label="Benchmark"
              onChange={(e) => setFilters({ benchmark: e.target.value })}
              sx={{
                background: 'rgba(255,255,255,0.06)',
                color: '#E2E8F0',
                fontSize: 12,
                borderRadius: 2,
                '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.12)' },
                '& svg': { color: '#64748B' },
              }}
            >
              {benchmarks.map((b: string) => (
                <MenuItem key={b} value={b} sx={{ fontSize: 12 }}>{b}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Category filter */}
          <Autocomplete
            multiple
            size="small"
            options={allCats}
            value={filters.categories}
            onChange={(_, v) => setFilters({ categories: v })}
            renderTags={(val, getProps) =>
              val.map((option, index) => (
                <Chip {...getProps({ index })} key={option} label={option} size="small"
                  sx={{ fontSize: 10, height: 18, background: 'rgba(59,130,246,0.2)', color: '#93C5FD', '& svg': { color: '#93C5FD' } }} />
              ))
            }
            renderInput={(params) => (
              <TextField {...params} label="Category" placeholder="All"
                sx={{
                  mb: 2,
                  '& .MuiInputBase-root': { background: 'rgba(255,255,255,0.06)', color: '#E2E8F0', borderRadius: 2, fontSize: 12 },
                  '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.12)' },
                  '& label': { color: '#64748B', fontSize: 11 },
                }}
              />
            )}
          />

          {/* Plan filter */}
          <Typography sx={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', mb: 1 }}>Plan Type</Typography>
          <ToggleButtonGroup
            exclusive
            value={filters.plan}
            onChange={(_, v) => v && setFilters({ plan: v })}
            fullWidth
            size="small"
            sx={{
              mb: 2,
              '& .MuiToggleButton-root': {
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#64748B', fontSize: 11, fontWeight: 600, py: 0.6,
                '&.Mui-selected': { background: 'rgba(59,130,246,0.25)', color: '#93C5FD', borderColor: 'rgba(59,130,246,0.4)' },
              },
            }}
          >
            {['All','Direct','Regular'].map((p) => (
              <ToggleButton key={p} value={p}>{p}</ToggleButton>
            ))}
          </ToggleButtonGroup>

          {/* Min allocation */}
          <Typography sx={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', mb: 1 }}>
            Min Allocation: {filters.minAlloc.toFixed(1)}%
          </Typography>
          <Slider
            value={filters.minAlloc}
            onChange={(_, v) => setFilters({ minAlloc: v as number })}
            min={0} max={20} step={0.5}
            sx={{
              mb: 2, color: '#3B82F6',
              '& .MuiSlider-rail': { background: 'rgba(255,255,255,0.12)' },
              '& .MuiSlider-thumb': { width: 14, height: 14 },
            }}
          />

          {/* Spacer + footer */}
          <Box sx={{ flex: 1 }} />
          <Divider sx={{ borderColor: 'rgba(255,255,255,0.07)', mb: 2 }} />
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 1 }}>
            <Typography sx={{ fontSize: 10, color: '#334155', lineHeight: 1.6 }}>
              SEBI CSCRF 2025<br />Zero Data Retention
            </Typography>
            <Tooltip title="Upload new CAS">
              <IconButton size="small" onClick={clearSession} sx={{ color: '#64748B' }}>
                <LogoutIcon sx={{ fontSize: 17 }} />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </Drawer>

      {/* ── Main ──────────────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <AppBar position="sticky" elevation={0}>
          <Toolbar variant="dense" sx={{ minHeight: 52, px: 3 }}>
            <Box sx={{ flex: 1 }} />
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip
                size="small"
                label={`${parseData?.fund_count ?? 0} Funds`}
                sx={{ background: '#EFF6FF', color: '#1D4ED8', fontWeight: 700, fontSize: 11 }}
              />
              <Chip
                size="small"
                label={`${parseData?.amc_count ?? 0} AMCs`}
                sx={{ background: '#ECFDF5', color: '#059669', fontWeight: 700, fontSize: 11 }}
              />
              {isPartial && (
                <Chip
                  size="small"
                  icon={<WarningAmberIcon sx={{ fontSize: 13 }} />}
                  label="Partial CAS"
                  color="warning"
                  variant="outlined"
                  sx={{ fontWeight: 700, fontSize: 11 }}
                />
              )}
            </Stack>
          </Toolbar>
        </AppBar>

        <Box
          component={motion.div}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          sx={{ flex: 1, p: { xs: 2, md: 3 }, overflowY: 'auto' }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  )
}
