import { fmtInr } from '../../utils/fmt'
import React, { useState, useRef, useCallback, useEffect } from 'react'
import { Box, Typography, Chip, Menu, MenuItem, Checkbox,
         ListItemText, IconButton, Tooltip as MuiTooltip,
         Divider, alpha as muiAlpha } from '@mui/material'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Brush,
} from 'recharts'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import FullscreenIcon from '@mui/icons-material/Fullscreen'
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit'
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'

// ─── Constants ──────────────────────────────────────────────────────────────
const BENCHMARKS = [
  'Nifty 50',
  'Nifty Midcap 150',
  'Nifty Largemid 250',
  'Nifty Smallcap 250',
  'Nifty Next 50',
  'Sensex',
  'S&P 500 (US)',
]
const PERIODS = ['1M', '3M', '6M', '1Y', '3Y', '5Y', 'ALL']
const PORT_COLOR  = '#F59E0B'   // Amber/orange — portfolio

// Colors for multiple benchmarks (primary is purple, others distinct)
const BENCHMARK_COLORS = [
  '#7C3AED', // Purple (primary)
  '#06B6D4', // Cyan
  '#EC4899', // Pink
  '#10B981', // Emerald
  '#F43F5E', // Rose
  '#8B5CF6', // Violet
]

// ─── Types ──────────────────────────────────────────────────────────────────
interface Props {
  dates: string[]
  portfolioSeries: number[]
  primaryBenchmark: string
  primarySeries: number[]
  overlaySeries: Record<string, number[]>
  
  period: string
  selectedBenchmarks: string[]
  
  portReturn: number
  benchReturn: number
  alpha: number
  
  onPeriodChange: (p: string) => void
  onBenchmarksChange: (b: string[]) => void
}

// ─── Custom X-Axis Tick (Year-dominant, Month-secondary) ────────────────────
function HierarchicalXTick({ x, y, payload, period }: any) {
  if (!payload?.value) return null
  const raw = payload.value as string
  const [yr, mo, da] = raw.split('-')
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const monthStr = monthNames[(parseInt(mo, 10) - 1)] ?? mo

  const isShort = period === '1M' || period === '3M'

  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={0} dy={14} textAnchor="middle" fill="#94A3B8" fontSize={10}>
        {isShort ? `${parseInt(da, 10)} ${monthStr}` : monthStr}
      </text>
      {mo === '01' && !isShort && (
        <text x={0} y={0} dy={26} textAnchor="middle" fill="#475569" fontSize={11} fontWeight="600">
          {yr}
        </text>
      )}
    </g>
  )
}

// ─── Utility to format date (e.g., "5th Nov 2022") ─────────────────────────────
function formatZerodhaDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const day = d.getDate()
  const nth = (day > 3 && day < 21) ? 'th' : ['th', 'st', 'nd', 'rd', 'th', 'th', 'th', 'th', 'th', 'th'][day % 10]
  return `${day}${nth} ${months[d.getMonth()]} ${d.getFullYear()}`
}

// ─── Custom Crosshair Tooltip ────────────────────────────────────────────────
function CrosshairTooltip({ active, payload, startDate, basePoint, benchColors }: any) {
  if (!active || !payload?.length || !basePoint) return null

  const port = payload.find((p: any) => p.dataKey === 'PortfolioK')
  const portVal = port?.value ?? 1000
  const portBase = basePoint.PortfolioK ?? 1000
  const portPct = (((portVal - portBase) / portBase) * 100).toFixed(2)

  const hoveredDate = payload[0].payload.date
  const benchmarks = payload.filter((p: any) => p.dataKey !== 'PortfolioK')

  return (
    <Box sx={{
      background: '#0F172A',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '16px',
      p: 2,
      boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
      minWidth: 190,
      backdropFilter: 'blur(20px)',
    }}>
      {/* ── Header: Hovered Date ── */}
      <Typography sx={{ fontSize: 13, fontWeight: 800, color: '#fff', mb: 1.5, letterSpacing: '0.05em' }}>
        {formatZerodhaDate(hoveredDate)}
      </Typography>

      {/* ── Top Section: NAVs ── */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
        <Box sx={{ width: 8, height: 8, background: PORT_COLOR, borderRadius: '2px', flexShrink: 0, boxShadow: `0 0 8px ${PORT_COLOR}` }} />
        <Typography sx={{ fontSize: 12, fontWeight: 700, color: '#E2E8F0' }}>
          MF NAV: {fmtInr(portVal)}
        </Typography>
      </Box>

      {benchmarks.map((b: any) => {
        const color = benchColors[b.dataKey] || '#94A3B8'
        return (
          <Box key={b.dataKey} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
            <Box sx={{ width: 8, height: 8, background: color, borderRadius: '2px', flexShrink: 0, boxShadow: `0 0 8px ${color}` }} />
            <Typography sx={{ fontSize: 12, fontWeight: 700, color: '#E2E8F0' }}>
              {b.name}: {fmtInr(b.value)}
            </Typography>
          </Box>
        )
      })}

      <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.1)', borderStyle: 'dashed' }} />

      {/* ── Bottom Section: Returns ── */}
      <Typography sx={{ fontSize: 10, color: '#94A3B8', mb: 1, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 800 }}>
        SINCE {formatZerodhaDate(startDate).toUpperCase()}
      </Typography>

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography sx={{ fontSize: 12, color: '#94A3B8', fontWeight: 600 }}>Mutual Funds:</Typography>
        <Typography sx={{ fontSize: 12, color: parseFloat(portPct) >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>
          {portPct}% {parseFloat(portPct) >= 0 ? '▲' : '▼'}
        </Typography>
      </Box>

      {benchmarks.map((b: any) => {
        const bVal = b.value ?? 1000
        const bBase = basePoint[b.dataKey] ?? 1000
        const pct = (((bVal - bBase) / bBase) * 100).toFixed(2)
        
        return (
          <Box key={b.dataKey} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography sx={{ fontSize: 12, color: '#94A3B8', fontWeight: 600 }}>{b.name}:</Typography>
            <Typography sx={{ fontSize: 12, color: parseFloat(pct) >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>
              {pct}% {parseFloat(pct) >= 0 ? '▲' : '▼'}
            </Typography>
          </Box>
        )
      })}
    </Box>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function PortfolioChart({
  dates, portfolioSeries, primaryBenchmark, primarySeries, overlaySeries,
  period, selectedBenchmarks, portReturn, benchReturn, alpha,
  onPeriodChange, onBenchmarksChange,
}: Props) {
  const [compareAnchor, setCompareAnchor] = useState<null | HTMLElement>(null)
  const [fullscreen,    setFullscreen]    = useState(false)
  const [hoveredPoint, setHoveredPoint] = useState<any | null>(null)
  const [brushRange,    setBrushRange]    = useState({ startIndex: 0, endIndex: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  // Map benchmark names to colors
  const benchColors: Record<string, string> = {}
  selectedBenchmarks.forEach((bm, i) => {
    benchColors[bm] = BENCHMARK_COLORS[i % BENCHMARK_COLORS.length]
  })

  // Build combined data array with date-aware alignment for overlay benchmarks
  const combinedData = dates.map((d, i) => {
    const point: any = { date: d }
    
    // Portfolio is always aligned by index i
    let pk = parseFloat(((portfolioSeries[i] || 100) * 10).toFixed(2))
    point.PortfolioK = isNaN(pk) ? 1000 : pk
    
    // Primary benchmark is also aligned by index i
    if (selectedBenchmarks.includes(primaryBenchmark)) {
      let bk = parseFloat(((primarySeries[i] || 100) * 10).toFixed(2))
      point[primaryBenchmark] = isNaN(bk) ? 1000 : bk
    }
    
    // Overlay benchmarks
    Object.entries(overlaySeries).forEach(([bm, series]) => {
      if (selectedBenchmarks.includes(bm)) {
        const val = series[i] !== undefined ? series[i] : series[series.length - 1]
        let ovk = parseFloat(((val || 100) * 10).toFixed(2))
        point[bm] = isNaN(ovk) ? 1000 : ovk
      }
    })
    return point
  })

  // Reset brush when period/data changes
  useEffect(() => {
    setBrushRange({ startIndex: 0, endIndex: combinedData.length > 0 ? combinedData.length - 1 : 0 })
  }, [combinedData.length, period])

  // Base point for relative percentage calculations in the tooltip
  const basePoint = combinedData.length > 0 ? combinedData[brushRange.startIndex] : null
  const startDate = basePoint ? basePoint.date : ''

  // Y-axis domain
  let allVals: number[] = []
  combinedData.forEach(d => {
    allVals.push(d.PortfolioK)
    selectedBenchmarks.forEach(bm => {
      if (d[bm] !== undefined && !isNaN(d[bm])) allVals.push(d[bm])
    })
  })
  
  const yMin = allVals.length > 0 ? Math.min(...allVals) : 900
  const yMax = allVals.length > 0 ? Math.max(...allVals) : 1500
  const yPad = (yMax - yMin) * 0.08
  const yDomain: [number, number] = [Math.floor((yMin - yPad) / 100) * 100,
                                      Math.ceil((yMax + yPad)  / 100) * 100]

  const fmtK = (v: number) => {
    return new Intl.NumberFormat('en-IN').format(v)
  }

  const toggleFullscreen = useCallback(() => {
    if (!fullscreen) {
      containerRef.current?.requestFullscreen?.()
      setFullscreen(true)
    } else {
      document.exitFullscreen?.()
      setFullscreen(false)
    }
  }, [fullscreen])

  const openCompare  = (e: React.MouseEvent<HTMLElement>) => setCompareAnchor(e.currentTarget)
  const closeCompare = () => setCompareAnchor(null)

  const toggleBenchmark = (bm: string) => {
    if (selectedBenchmarks.includes(bm)) {
      if (selectedBenchmarks.length > 1) {
        onBenchmarksChange(selectedBenchmarks.filter(b => b !== bm))
      }
    } else {
      if (selectedBenchmarks.length < 5) {
        onBenchmarksChange([...selectedBenchmarks, bm])
      }
    }
  }

  // ── Determine Displayed Returns (Dynamic on Hover) ──
  const isHovering = !!hoveredPoint
  const pVal = isHovering ? hoveredPoint.PortfolioK : (combinedData.length ? combinedData[combinedData.length-1].PortfolioK : 1000)
  const pBase = basePoint?.PortfolioK ?? 1000
  const curPortRet = ((pVal - pBase) / pBase) * 100

  const bVal = isHovering ? (hoveredPoint[primaryBenchmark] ?? 1000) : (combinedData.length ? (combinedData[combinedData.length-1][primaryBenchmark] ?? 1000) : 1000)
  const bBase = basePoint?.[primaryBenchmark] ?? 1000
  const curBenchRet = bBase ? ((bVal - bBase) / bBase) * 100 : 0
  
  const curAlpha = curPortRet - curBenchRet

  const portPctStr  = curPortRet >= 0 ? `+${curPortRet.toFixed(2)}%` : `${curPortRet.toFixed(2)}%`
  const benchPctStr = curBenchRet >= 0 ? `+${curBenchRet.toFixed(2)}%` : `${curBenchRet.toFixed(2)}%`

  return (
    <Box
      ref={containerRef}
      sx={{
        background: 'transparent',
        borderRadius: fullscreen ? 0 : 4,
        p: { xs: 1, md: 2 },
        ...(fullscreen && { position: 'fixed', inset: 0, zIndex: 9999, bgcolor: '#0F172A', p: 4, overflow: 'auto' }),
      }}
    >
      {/* ── Top Header Row: Core Performance & Timeline ──────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 3, flexWrap: 'wrap', gap: 2 }}>
        {/* Left: Title + Portfolio Core Return + Alpha Pill */}
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Typography variant="overline" sx={{ fontSize: 13, fontWeight: 900, color: '#fff', letterSpacing: '0.15em' }}>
              PORTFOLIO PERFORMANCE & ATTRIBUTION
            </Typography>
            <MuiTooltip title="Indexed chart: ₹1,000 invested at period start → compounding growth shown. Compare multiple benchmarks." arrow>
              <InfoOutlinedIcon sx={{ fontSize: 14, color: '#94A3B8', cursor: 'help' }} />
            </MuiTooltip>
          </Box>
          {/* Core Return & Alpha Pill */}
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
            <Box sx={{ px: 2, py: 1, borderRadius: '12px', background: 'rgba(245, 158, 11, 0.1)', border: `1px solid ${muiAlpha(PORT_COLOR, 0.3)}`, display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Box sx={{ width: 10, height: 10, background: PORT_COLOR, borderRadius: '3px', boxShadow: `0 0 10px ${PORT_COLOR}` }} />
              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 14, fontWeight: 900, color: curPortRet >= 0 ? '#4EDE93' : '#FF516A' }}>
                MF {portPctStr}
              </Typography>
            </Box>

            <Chip
              size="small"
              label={isHovering ? `Spot Alpha ${curAlpha >= 0 ? '+' : ''}${curAlpha.toFixed(2)}%` : `Alpha vs ${primaryBenchmark} ${curAlpha >= 0 ? '+' : ''}${curAlpha.toFixed(2)}%`}
              variant="outlined"
              sx={{
                fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 900, px: 1, py: 2, borderRadius: '10px',
                background: curAlpha >= 0 ? 'rgba(78, 222, 147, 0.1)' : 'rgba(255, 81, 106, 0.1)',
                color:      curAlpha >= 0 ? '#4EDE93'  : '#FF516A',
                borderColor: curAlpha >= 0 ? 'rgba(78, 222, 147, 0.3)' : 'rgba(255, 81, 106, 0.3)',
                transition: 'all 0.2s'
              }}
            />
          </Box>
        </Box>

        {/* Right: Period selector + Fullscreen */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          {/* Period selector */}
          <Box sx={{ display: 'flex', background: 'rgba(0,0,0,0.3)', borderRadius: '14px', border: '1px solid rgba(255,255,255,0.1)', p: 0.5 }}>
            {PERIODS.map((p) => (
              <Box
                key={p}
                onClick={() => onPeriodChange(p)}
                sx={{
                  px: 1.5, py: 0.75, borderRadius: '10px', cursor: 'pointer',
                  fontSize: 11, fontWeight: 800, userSelect: 'none',
                  background: period === p ? 'primary.main' : 'transparent',
                  color:      period === p ? '#fff'    : '#94A3B8',
                  boxShadow:  period === p ? '0 4px 12px rgba(99, 102, 241, 0.4)' : 'none',
                  transition: 'all 0.2s',
                  '&:hover':  { color: '#fff', background: period === p ? 'primary.main' : 'rgba(255,255,255,0.05)' },
                }}
              >
                {p}
              </Box>
            ))}
          </Box>

          {/* Fullscreen */}
          <MuiTooltip title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'} arrow>
            <IconButton size="small" onClick={toggleFullscreen}
              sx={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.03)', color: '#fff', p: 1, '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' } }}>
              {fullscreen
                ? <FullscreenExitIcon sx={{ fontSize: 18 }} />
                : <FullscreenIcon    sx={{ fontSize: 18 }} />}
            </IconButton>
          </MuiTooltip>
        </Box>
      </Box>

      {/* ── Sub-Header Bar: Interactive Benchmark Comparator Strip ──────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap', mb: 3, p: 1.5, background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
        {/* Compare Menu Trigger */}
        <Box
          onClick={openCompare}
          sx={{
            display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer',
            border: '1px solid rgba(99, 102, 241, 0.3)', borderRadius: '12px', px: 2.5, py: 1,
            background: 'rgba(99, 102, 241, 0.1)', backdropFilter: 'blur(10px)',
            '&:hover': { background: 'rgba(99, 102, 241, 0.2)', borderColor: 'primary.main' },
            transition: 'all 0.2s',
          }}
        >
          <AddCircleOutlineIcon sx={{ fontSize: 16, color: 'primary.main' }} />
          <Typography sx={{ fontSize: 12, fontWeight: 800, color: '#fff' }}>+ Add Comparator</Typography>
        </Box>
        <Menu
          anchorEl={compareAnchor}
          open={Boolean(compareAnchor)}
          onClose={closeCompare}
          PaperProps={{ sx: { background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', mt: 1, boxShadow: '0 10px 40px rgba(0,0,0,0.5)' } }}
        >
          {BENCHMARKS.map((b) => {
            const checked = selectedBenchmarks.includes(b)
            return (
              <MenuItem
                key={b}
                dense
                onClick={() => toggleBenchmark(b)}
                sx={{ py: 1, px: 2, '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' } }}
              >
                <Checkbox
                  checked={checked}
                  size="small"
                  sx={{ p: 0.5, mr: 1, color: benchColors[b] || 'rgba(255,255,255,0.3)',
                        '&.Mui-checked': { color: benchColors[b] || 'primary.main' } }}
                />
                <ListItemText primary={b} primaryTypographyProps={{ fontSize: 13, fontWeight: 700, color: '#fff' }} />
              </MenuItem>
            )
          })}
        </Menu>

        {/* Selected Benchmark Interactive Chips */}
        {selectedBenchmarks.map((bm) => {
           const val = isHovering ? (hoveredPoint[bm] ?? 1000) : (combinedData.length ? (combinedData[combinedData.length-1][bm] ?? 1000) : 1000)
           const base = basePoint?.[bm] ?? 1000
           const ret = base ? ((val - base) / base) * 100 : 0
           const retStr = ret >= 0 ? `+${ret.toFixed(2)}%` : `${ret.toFixed(2)}%`
           const color = benchColors[bm] || '#94A3B8'
           
           return (
             <Chip
               key={bm}
               label={`${bm}: ${retStr}`}
               onDelete={selectedBenchmarks.length > 1 ? () => toggleBenchmark(bm) : undefined}
               sx={{
                 fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 800, py: 2.25, px: 1, borderRadius: '12px',
                 background: muiAlpha(color, 0.12),
                 color: ret >= 0 ? '#fff' : '#FF516A',
                 border: `1px solid ${muiAlpha(color, 0.4)}`,
                 '& .MuiChip-deleteIcon': { color: muiAlpha(color, 0.7), '&:hover': { color: '#FF516A' } },
                 boxShadow: `0 0 12px ${muiAlpha(color, 0.2)}`
               }}
             />
           )
        })}
      </Box>

      {/* ── Chart ─────────────────────────────────────────────────────────── */}
      <Box sx={{ position: 'relative', width: '100%', height: fullscreen ? 540 : 380, mt: 2 }}>
        {(!overlaySeries || Object.keys(overlaySeries).length === 0) && selectedBenchmarks.length > 1 && (
          <Box sx={{ 
            position: 'absolute', top: 10, right: 10, zIndex: 10, 
            display: 'flex', alignItems: 'center', gap: 1,
            background: 'rgba(15, 23, 42, 0.8)', px: 2, py: 1, borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)'
          }}>
            <Typography sx={{ fontSize: 11, color: '#4EDE93', fontWeight: 800 }}>FETCHING LIVE BENCHMARKS...</Typography>
          </Box>
        )}
        
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart 
            data={combinedData} 
            margin={{ top: 8, right: 24, left: 8, bottom: 0 }}
            onMouseMove={(e: any) => {
              if (e && e.activePayload && e.activePayload.length > 0) {
                setHoveredPoint(e.activePayload[0].payload)
              }
            }}
            onMouseLeave={() => setHoveredPoint(null)}
          >
            <defs>
              <linearGradient id="colorBench" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={benchColors[primaryBenchmark] || '#7C3AED'} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={benchColors[primaryBenchmark] || '#7C3AED'} stopOpacity={0.0}/>
              </linearGradient>
              <linearGradient id="colorPort" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={PORT_COLOR} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={PORT_COLOR} stopOpacity={0.0}/>
              </linearGradient>
            </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />

          <XAxis
            dataKey="date"
            tick={<HierarchicalXTick period={period} />}
            tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            height={40}
            interval="preserveStartEnd"
          />

          <YAxis
            domain={yDomain}
            tick={{ fontSize: 10, fill: '#94A3B8', fontWeight: 600 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={fmtK}
            tickCount={6}
            width={48}
          />


          <Tooltip
            content={<CrosshairTooltip startDate={startDate} basePoint={basePoint} benchColors={benchColors} />}
            cursor={{ stroke: 'rgba(255,255,255,0.2)', strokeWidth: 1.5, strokeDasharray: '4 4' }}
          />

          {/* Portfolio */}
          <Area
            type="monotone"
            dataKey="PortfolioK"
            name="Portfolio"
            stroke={PORT_COLOR}
            strokeWidth={3}
            fill="url(#colorPort)"
            fillOpacity={1}
            dot={false}
            activeDot={{ r: 6, fill: PORT_COLOR, stroke: '#0F172A', strokeWidth: 3 }}
          />

          {/* Selected Benchmarks */}
          {selectedBenchmarks.map((bm, i) => {
            const isPrimary = bm === primaryBenchmark
            const color = benchColors[bm] || '#94A3B8'
            
            if (isPrimary) {
              return (
                <Area
                  key={bm}
                  type="monotone"
                  dataKey={bm}
                  stroke={color}
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#colorBench)"
                  connectNulls
                  animationDuration={1000}
                />
              )
            }
            
            return (
              <Line
                key={bm}
                type="monotone"
                dataKey={bm}
                name={bm}
                stroke={color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, fill: color, stroke: '#0F172A', strokeWidth: 2 }}
                connectNulls
                animationDuration={1000}
              />
            )
          })}

          {/* Brush */}
          <Brush
            dataKey="date"
            height={32}
            stroke="rgba(255,255,255,0.2)"
            fill="rgba(255,255,255,0.02)"
            travellerWidth={8}
            onChange={(newRange: any) => {
              if (newRange && newRange.startIndex !== undefined) {
                setBrushRange({ startIndex: newRange.startIndex, endIndex: newRange.endIndex })
              }
            }}
            tickFormatter={(v) => {
              const parts = String(v).split('-')
              if (parts.length >= 3 && (period === '1M' || period === '3M')) {
                 const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
                 const mo = parseInt(parts[1], 10) - 1
                 return `${parts[2]} ${monthNames[mo]}`
              }
              return parts.length >= 2 ? `${parts[0]}-${parts[1]}` : v
            }}
          >
            <ComposedChart>
              <Line type="monotone" dataKey="PortfolioK" stroke={PORT_COLOR} dot={false} strokeWidth={1.5} />
              {selectedBenchmarks.map(bm => (
                <Line key={bm} type="monotone" dataKey={bm} stroke={benchColors[bm]} dot={false} strokeWidth={1.5} />
              ))}
            </ComposedChart>
          </Brush>
        </ComposedChart>
      </ResponsiveContainer>

      </Box>

      {/* ── Footer legend ──────────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: 4, mt: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ width: 14, height: 14, background: PORT_COLOR, borderRadius: '4px', boxShadow: `0 0 10px ${PORT_COLOR}` }} />
          <Typography sx={{ fontSize: 12, color: '#E2E8F0', fontWeight: 800 }}>Mutual Funds</Typography>
        </Box>
        {selectedBenchmarks.map(bm => (
          <Box key={bm} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ width: 14, height: 14, background: benchColors[bm], borderRadius: '4px', boxShadow: `0 0 10px ${benchColors[bm]}` }} />
            <Typography sx={{ fontSize: 12, color: '#E2E8F0', fontWeight: 800 }}>{bm}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  )
}
