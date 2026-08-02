import React, { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Box, Button, Card, Skeleton, Typography } from '@mui/material'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import { ResponsiveContainer, Sankey, Tooltip as RechartsTooltip } from 'recharts'

import { budgetErrorDetail, useBudgetSankey } from '../hooks/useBudget'
import type { BudgetSankey } from '../types'

/**
 * Where the money came from and where it went, as a Sankey.
 *
 * The endpoint already returns the exact shape recharts wants - `nodes` plus `links`
 * whose `source`/`target` are integer indices into `nodes` - so this passes the payload
 * through nearly unchanged. What it does not do is pass it through *blindly*.
 *
 * recharts' Sankey does no validation of its own and crashes rather than degrading:
 *
 *  - an empty `nodes` array makes `maxBy(tree, ...)` return undefined, and the layout
 *    then reads `.depth` off it - a TypeError that takes the whole dashboard down, so
 *    the empty case has to be caught before the chart mounts, not styled around;
 *  - a link pointing past the end of `nodes` dereferences `nodes[link.source]` as
 *    undefined in renderLinks;
 *  - a self-link, or any cycle, sends `updateDepthOfTargets` into unbounded recursion
 *    and blows the stack.
 *
 * So the payload is sanitised first and anything that survives is plottable. Links that
 * do not survive are counted and reported under the chart: a flow silently missing from
 * a picture of "everything you earned and spent" is exactly the kind of quiet omission
 * the rest of this dashboard goes out of its way to avoid.
 */

const NODE_COLOURS: Record<string, string> = {
  income: '#38bdf8',
  source: '#22d3ee',
  nature: '#a78bfa',
  category: '#f472b6',
}
const NODE_FALLBACK = '#64748b'

/** Only the groups actually present get a swatch, in this order. */
const LEGEND_ORDER = ['income', 'source', 'nature', 'category'] as const
const LEGEND_LABELS: Record<string, string> = {
  income: 'Income',
  source: 'Source',
  nature: 'Need / want',
  category: 'Category',
}

const CHART_HEIGHT = 420

const CARD_SX = {
  p: 2.5,
  mb: 3,
  borderRadius: 2,
  backgroundColor: 'rgba(30, 41, 59, 0.5)',
  border: '1px solid rgba(148, 163, 184, 0.15)',
  color: '#e2e8f0',
} as const

const HEADER_ROW_SX = {
  display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap',
} as const

const TITLE_SX = { fontWeight: 700, color: '#e2e8f0', fontSize: '1rem' } as const
const MUTED_SX = { color: '#94a3b8', fontSize: '0.85rem' } as const
const CAPTION_SX = { ...MUTED_SX, mt: 0.5, display: 'block' } as const

const AMBER_NOTE_SX = {
  mt: 1.5, px: 1.5, py: 1, borderRadius: 1.5, fontSize: '0.78rem', color: '#fcd34d',
  backgroundColor: 'rgba(245, 158, 11, 0.10)',
  border: '1px solid rgba(245, 158, 11, 0.30)',
} as const

const CHART_WRAP_SX = { mt: 2, width: '100%', height: CHART_HEIGHT } as const

const EMPTY_SX = {
  mt: 2, height: 200, display: 'flex', flexDirection: 'column',
  alignItems: 'center', justifyContent: 'center', gap: 0.5,
  borderRadius: 2, border: '1px dashed rgba(148, 163, 184, 0.25)',
} as const

const ERROR_CARD_SX = {
  ...CARD_SX,
  backgroundColor: 'rgba(239, 68, 68, 0.08)',
  border: '1px solid rgba(239, 68, 68, 0.3)',
} as const

const LEGEND_ROW_SX = {
  display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center', mt: 1.5,
} as const

const LEGEND_ITEM_SX = {
  display: 'flex', alignItems: 'center', gap: 0.6,
  color: '#94a3b8', fontSize: '0.75rem',
} as const

const TOOLTIP_SX = {
  backgroundColor: '#0f172a',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 2,
  px: 1.5,
  py: 1,
  color: '#fff',
} as const

/** The Sankey's own link styling. Merged over recharts' `#333` default. */
const LINK_STYLE = { stroke: '#94a3b8', strokeOpacity: 0.22 } as const

const CHART_MARGIN = { top: 12, right: 140, bottom: 12, left: 120 } as const

function money(value: number): string {
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

type SankeyLinkInput = BudgetSankey['links'][number]

/**
 * Drop the links that close a cycle.
 *
 * recharts walks the graph depth-first with `target.depth = max(cur.depth + 1, ...)`
 * and no visited set, so a single back edge recurses forever. Iterative DFS with the
 * usual white/grey/black colouring; an edge into a grey node is a back edge and is the
 * one dropped, which leaves the acyclic majority of the graph intact.
 */
function dropCycles(nodeCount: number, links: SankeyLinkInput[]): SankeyLinkInput[] {
  const outgoing: number[][] = Array.from({ length: nodeCount }, () => [])
  links.forEach((link, index) => { outgoing[link.source].push(index) })

  const WHITE = 0, GREY = 1, BLACK = 2
  const colour = new Uint8Array(nodeCount)
  const dropped = new Set<number>()

  for (let root = 0; root < nodeCount; root++) {
    if (colour[root] !== WHITE) continue
    colour[root] = GREY
    const stack: { node: number; next: number }[] = [{ node: root, next: 0 }]

    while (stack.length > 0) {
      const frame = stack[stack.length - 1]
      const edges = outgoing[frame.node]
      if (frame.next >= edges.length) {
        colour[frame.node] = BLACK
        stack.pop()
        continue
      }
      const edge = edges[frame.next++]
      if (dropped.has(edge)) continue
      const target = links[edge].target
      if (colour[target] === GREY) { dropped.add(edge); continue }
      if (colour[target] === WHITE) {
        colour[target] = GREY
        stack.push({ node: target, next: 0 })
      }
    }
  }

  return dropped.size === 0 ? links : links.filter((_, index) => !dropped.has(index))
}

interface PlottableSankey {
  nodes: BudgetSankey['nodes']
  links: SankeyLinkInput[]
  /** Links the server sent that could not be drawn. Reported, not swallowed. */
  droppedLinks: number
}

/**
 * Everything recharts will not check for itself.
 *
 * Nodes left with no surviving link are removed too - they would lay out with a zero
 * height and render as a floating label attached to nothing - which means the link
 * indices have to be remapped onto the compacted node array.
 */
function sanitise(data: BudgetSankey | undefined): PlottableSankey {
  const nodes = data?.nodes ?? []
  const rawLinks = data?.links ?? []

  const wellFormed = rawLinks.filter(link => (
    !!link
    && Number.isInteger(link.source) && link.source >= 0 && link.source < nodes.length
    && Number.isInteger(link.target) && link.target >= 0 && link.target < nodes.length
    && link.source !== link.target
    && Number.isFinite(link.value) && link.value > 0
  ))

  const acyclic = dropCycles(nodes.length, wellFormed)

  const used = new Set<number>()
  for (const link of acyclic) { used.add(link.source); used.add(link.target) }

  const kept: number[] = []
  const remap = new Map<number, number>()
  nodes.forEach((_, index) => {
    if (!used.has(index)) return
    remap.set(index, kept.length)
    kept.push(index)
  })

  return {
    nodes: kept.map(index => nodes[index]),
    links: acyclic.map(link => ({
      source: remap.get(link.source) as number,
      target: remap.get(link.target) as number,
      value: link.value,
    })),
    droppedLinks: rawLinks.length - acyclic.length,
  }
}

// ── Chart internals ──────────────────────────────────────────────────────────

interface SankeyNodeRenderProps {
  x: number
  y: number
  width: number
  height: number
  index: number
  payload: { name?: string; group?: string; value?: number }
}

/**
 * The node renderer, coloured by `group`.
 *
 * A factory rather than a component so the measured container width can decide which
 * side of the node its label sits on - past the midpoint the label has to run leftwards
 * or it is clipped by the edge of the chart.
 */
function makeNodeRenderer(containerWidth: number) {
  return function SankeyGroupNode(props: SankeyNodeRenderProps) {
    const { x, y, width, height, payload } = props
    const colour = NODE_COLOURS[payload?.group ?? ''] ?? NODE_FALLBACK
    const name = payload?.name ?? ''
    const value = payload?.value ?? 0

    // Right-hand nodes label leftwards; everything else labels to the right.
    const labelLeft = containerWidth > 0 && x + width > containerWidth * 0.6
    const textX = labelLeft ? x - 8 : x + width + 8
    const anchor = labelLeft ? 'end' : 'start'
    const showValue = height >= 16

    return (
      <g>
        <rect
          x={x}
          y={y}
          width={width}
          height={Math.max(height, 1)}
          fill={colour}
          fillOpacity={0.9}
          rx={2}
        />
        <text
          x={textX}
          y={y + height / 2 - (showValue ? 4 : 0)}
          textAnchor={anchor}
          dominantBaseline="middle"
          fill="#e2e8f0"
          fontSize={11}
          fontWeight={600}
        >
          {name}
        </text>
        {showValue && (
          <text
            x={textX}
            y={y + height / 2 + 9}
            textAnchor={anchor}
            dominantBaseline="middle"
            fill="#94a3b8"
            fontSize={10}
          >
            {money(value)}
          </text>
        )}
      </g>
    )
  }
}

interface SankeyTooltipProps {
  active?: boolean
  /** Sankey hands over one entry: a node's name, or "Source - Target" for a link. */
  payload?: { name?: string; value?: number | string }[]
}

function SankeyTooltip({ active, payload }: SankeyTooltipProps) {
  const entry = payload?.[0]
  if (!active || !entry) return null

  const value = typeof entry.value === 'number' ? entry.value : Number(entry.value)

  return (
    <Box sx={TOOLTIP_SX}>
      <Typography sx={{ fontSize: '0.8rem', fontWeight: 700, color: '#f1f5f9' }}>
        {entry.name}
      </Typography>
      <Typography sx={{ fontSize: '0.85rem', color: '#cbd5e1' }}>
        {Number.isFinite(value) ? money(value) : '—'}
      </Typography>
    </Box>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────

interface MoneyFlowCardProps {
  sessionId: string
}

function MoneyFlowCard({ sessionId }: MoneyFlowCardProps) {
  const { data, isPending, isError, error, refetch } = useBudgetSankey(sessionId)

  const chart = useMemo(() => sanitise(data), [data])
  const canPlot = chart.nodes.length > 0 && chart.links.length > 0

  // Label placement needs the pixel width, which ResponsiveContainer knows and does not
  // hand down to the node renderer. Measuring the wrapper is the only way to get it.
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [chartWidth, setChartWidth] = useState(0)

  useLayoutEffect(() => {
    const element = wrapRef.current
    if (!element) return

    const measure = () => setChartWidth(element.clientWidth)
    measure()

    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
    // The wrapper only exists once there is something to plot, so re-run when that flips.
  }, [canPlot])

  const renderNode = useMemo(() => makeNodeRenderer(chartWidth), [chartWidth])

  const legendGroups = useMemo(() => {
    const present = new Set(chart.nodes.map(node => node.group))
    return LEGEND_ORDER.filter(group => present.has(group))
  }, [chart.nodes])

  if (isPending) {
    return (
      <Skeleton
        variant="rounded"
        height={CHART_HEIGHT + 120}
        sx={{ mb: 3, bgcolor: 'rgba(148,163,184,0.08)' }}
      />
    )
  }

  if (isError) {
    return (
      <Card sx={ERROR_CARD_SX}>
        <Typography sx={{ color: '#fca5a5', fontSize: '0.9rem' }}>
          {budgetErrorDetail(error, 'Could not load your money flow.')}
        </Typography>
        <Button size="small" onClick={() => refetch()} sx={{ mt: 1, color: '#fca5a5' }}>
          Retry
        </Button>
      </Card>
    )
  }

  return (
    <Card sx={CARD_SX}>
      <Box sx={HEADER_ROW_SX}>
        <AccountTreeIcon sx={{ color: '#38bdf8' }} />
        <Typography sx={TITLE_SX}>Money flow</Typography>
      </Box>

      <Typography sx={CAPTION_SX}>
        Where your money came from and where it went. Transfers between your own accounts
        are excluded.
      </Typography>

      {canPlot ? (
        <>
          <Box sx={CHART_WRAP_SX} ref={wrapRef}>
            <ResponsiveContainer width="100%" height="100%">
              <Sankey
                data={chart}
                nameKey="name"
                dataKey="value"
                node={renderNode}
                link={LINK_STYLE}
                nodePadding={18}
                nodeWidth={12}
                margin={CHART_MARGIN}
              >
                <RechartsTooltip content={<SankeyTooltip />} />
              </Sankey>
            </ResponsiveContainer>
          </Box>

          {legendGroups.length > 0 && (
            <Box sx={LEGEND_ROW_SX}>
              {legendGroups.map(group => (
                <Box key={group} sx={LEGEND_ITEM_SX}>
                  <Box
                    component="span"
                    sx={{
                      width: 10, height: 10, borderRadius: '2px',
                      backgroundColor: NODE_COLOURS[group],
                    }}
                  />
                  {LEGEND_LABELS[group]}
                </Box>
              ))}
            </Box>
          )}
        </>
      ) : (
        <Box sx={EMPTY_SX}>
          <Typography sx={{ color: '#cbd5e1', fontSize: '0.9rem', fontWeight: 600 }}>
            No money flow to show yet
          </Typography>
          <Typography sx={MUTED_SX}>
            Upload a statement with both income and spending, and the flow appears here.
          </Typography>
        </Box>
      )}

      {chart.droppedLinks > 0 && (
        <Box sx={AMBER_NOTE_SX}>
          {chart.droppedLinks} flow{chart.droppedLinks === 1 ? '' : 's'} could not be
          plotted and {chart.droppedLinks === 1 ? 'is' : 'are'} not shown above. The
          diagram is therefore missing whatever {chart.droppedLinks === 1 ? 'it' : 'they'}{' '}
          carried.
        </Box>
      )}
    </Card>
  )
}

export default React.memo(MoneyFlowCard)
