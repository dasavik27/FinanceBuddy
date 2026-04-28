import { createTheme, alpha } from '@mui/material/styles'

const FONT = '"Plus Jakarta Sans", sans-serif'
const MONO = '"DM Mono", monospace'

// ── Palette ─────────────────────────────────────────────────────────────────
const P = {
  navy:    '#0A1628',
  blue:    '#1D4ED8',
  blue50:  '#EFF6FF',
  blue100: '#DBEAFE',
  blue200: '#BFDBFE',
  green:   '#059669',
  green50: '#ECFDF5',
  red:     '#DC2626',
  red50:   '#FEF2F2',
  amber:   '#D97706',
  amber50: '#FFFBEB',
  slate50:  '#F8FAFC',
  slate100: '#F1F5F9',
  slate200: '#E2E8F0',
  slate300: '#CBD5E1',
  slate400: '#94A3B8',
  slate500: '#64748B',
  slate700: '#334155',
  slate900: '#0F172A',
}

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary:   { main: P.blue,  light: P.blue100, dark: '#1E40AF', contrastText: '#fff' },
    secondary: { main: P.green, light: P.green50,  dark: '#047857', contrastText: '#fff' },
    error:     { main: P.red,   light: P.red50,    dark: '#B91C1C', contrastText: '#fff' },
    warning:   { main: P.amber, light: P.amber50,  dark: '#B45309', contrastText: '#fff' },
    background: { default: '#F0F4FA', paper: '#FFFFFF' },
    text: {
      primary:   P.slate900,
      secondary: P.slate500,
      disabled:  P.slate400,
    },
    divider: P.slate200,
  },

  typography: {
    fontFamily: FONT,
    h1: { fontSize: '2.25rem',  fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.15 },
    h2: { fontSize: '1.875rem', fontWeight: 800, letterSpacing: '-0.03em' },
    h3: { fontSize: '1.5rem',   fontWeight: 700, letterSpacing: '-0.02em' },
    h4: { fontSize: '1.25rem',  fontWeight: 700, letterSpacing: '-0.02em' },
    h5: { fontSize: '1.0625rem',fontWeight: 700, letterSpacing: '-0.01em' },
    h6: { fontSize: '0.9375rem',fontWeight: 700, letterSpacing: '-0.01em' },
    subtitle1: { fontSize: '0.9375rem', fontWeight: 600, letterSpacing: '-0.01em' },
    subtitle2: { fontSize: '0.8125rem', fontWeight: 600 },
    body1:     { fontSize: '0.875rem',  fontWeight: 400, lineHeight: 1.6 },
    body2:     { fontSize: '0.8125rem', fontWeight: 400, lineHeight: 1.55 },
    caption:   { fontSize: '0.6875rem', fontWeight: 400, color: P.slate400 },
    overline: {
      fontSize:      '0.625rem',
      fontWeight:    700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color:         P.slate400,
    },
    button: { fontFamily: FONT, fontWeight: 700, fontSize: '0.8125rem', letterSpacing: '0.02em', textTransform: 'none' },
  },

  shape: { borderRadius: 12 },

  shadows: [
    'none',
    '0 1px 2px rgba(15,23,42,0.04), 0 1px 6px rgba(15,23,42,0.06)',
    '0 1px 3px rgba(15,23,42,0.05), 0 4px 14px rgba(15,23,42,0.08)',
    '0 2px 6px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.11)',
    '0 4px 10px rgba(15,23,42,0.07), 0 16px 40px rgba(15,23,42,0.13)',
    '0 6px 14px rgba(15,23,42,0.08), 0 24px 56px rgba(15,23,42,0.15)',
    ...Array(19).fill('none'),
  ] as any,

  components: {

    // ── CssBaseline ────────────────────────────────────────────────────────
    MuiCssBaseline: {
      styleOverrides: `
        *, *::before, *::after { box-sizing: border-box; }
        html { -webkit-font-smoothing: antialiased; scroll-behavior: smooth; }
        body { background: #F0F4FA; font-family: ${FONT}; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${P.slate300}; border-radius: 999px; }
        ::-webkit-scrollbar-thumb:hover { background: ${P.slate400}; }
        .num { font-family: ${MONO} !important; }
      `,
    },

    // ── AppBar ─────────────────────────────────────────────────────────────
    MuiAppBar: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          background:    'rgba(240,244,250,0.88)',
          backdropFilter:'blur(16px)',
          borderBottom:  `1px solid ${P.slate200}`,
          color:          P.slate900,
        },
      },
    },

    // ── Drawer (Sidebar) ───────────────────────────────────────────────────
    MuiDrawer: {
      styleOverrides: {
        paper: {
          background:  P.navy,
          borderRight: `1px solid rgba(255,255,255,0.07)`,
          color:       '#94A3B8',
          width:       268,
        },
      },
    },

    // ── Card ───────────────────────────────────────────────────────────────
    MuiCard: {
      defaultProps: { elevation: 1 },
      styleOverrides: {
        root: {
          borderRadius: 16,
          border:       `1px solid ${P.slate200}`,
          background:   '#FFFFFF',
          transition:   'box-shadow 200ms cubic-bezier(0.2,0,0,1), transform 200ms cubic-bezier(0.2,0,0,1)',
          '&:hover': {
            boxShadow: '0 2px 6px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.11)',
            transform: 'translateY(-2px)',
          },
        },
      },
    },

    MuiCardContent: {
      styleOverrides: { root: { padding: '20px 22px', '&:last-child': { paddingBottom: 20 } } },
    },

    // ── Paper ──────────────────────────────────────────────────────────────
    MuiPaper: {
      defaultProps: { elevation: 1 },
      styleOverrides: {
        root: { backgroundImage: 'none' },
        rounded: { borderRadius: 16 },
        elevation1: { boxShadow: '0 1px 2px rgba(15,23,42,0.04), 0 1px 6px rgba(15,23,42,0.06)', border: `1px solid ${P.slate200}` },
        elevation2: { boxShadow: '0 1px 3px rgba(15,23,42,0.05), 0 4px 14px rgba(15,23,42,0.08)' },
        elevation3: { boxShadow: '0 2px 6px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.11)' },
      },
    },

    // ── Button ─────────────────────────────────────────────────────────────
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          borderRadius: 10,
          fontWeight:   700,
          fontSize:     '0.8125rem',
          padding:      '9px 22px',
          transition:   'all 150ms cubic-bezier(0.2,0,0,1)',
        },
        contained: {
          boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
          '&:hover': {
            boxShadow: '0 2px 6px rgba(29,78,216,0.3)',
            transform: 'translateY(-1px)',
          },
          '&:active': { transform: 'translateY(0)', boxShadow: 'none' },
        },
        outlined: {
          borderColor: P.slate200,
          color:       P.slate700,
          '&:hover': { borderColor: P.blue200, background: P.blue50, color: P.blue },
        },
        sizeLarge: { padding: '11px 28px', fontSize: '0.9375rem' },
        sizeSmall: { padding: '5px 14px',  fontSize: '0.75rem', borderRadius: 8 },
      },
    },

    // ── IconButton ─────────────────────────────────────────────────────────
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          transition: 'all 150ms ease',
          '&:hover': { background: P.slate100 },
        },
      },
    },

    // ── Chip ───────────────────────────────────────────────────────────────
    MuiChip: {
      styleOverrides: {
        root: {
          fontFamily:    FONT,
          fontWeight:    700,
          fontSize:      '0.6875rem',
          letterSpacing: '0.04em',
          borderRadius:  999,
          height:        24,
        },
        label: { padding: '0 10px' },
      },
    },

    // ── Tabs ───────────────────────────────────────────────────────────────
    MuiTabs: {
      styleOverrides: {
        root: {
          background:   '#FFFFFF',
          border:       `1px solid ${P.slate200}`,
          borderRadius: 14,
          padding:       4,
          minHeight:     42,
        },
        indicator: { display: 'none' },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontFamily:    FONT,
          fontWeight:    600,
          fontSize:      '0.8125rem',
          textTransform: 'none',
          minHeight:     34,
          borderRadius:  10,
          padding:       '6px 18px',
          color:         P.slate500,
          transition:    'all 120ms ease',
          '&:hover':     { background: P.slate100, color: P.slate700 },
          '&.Mui-selected': {
            background: P.slate900,
            color:      '#FFFFFF',
            fontWeight: 700,
          },
        },
      },
    },

    // ── TextField ──────────────────────────────────────────────────────────
    MuiTextField: {
      defaultProps: { variant: 'outlined', size: 'small' },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          background:   '#FFFFFF',
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: P.blue200 },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: P.blue,
            borderWidth:  2,
          },
        },
        notchedOutline: { borderColor: P.slate200 },
        input: { fontSize: '0.875rem', padding: '9px 14px' },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: { fontSize: '0.875rem', color: P.slate400 },
      },
    },

    // ── Select ─────────────────────────────────────────────────────────────
    MuiSelect: {
      defaultProps: { size: 'small' },
      styleOverrides: { select: { fontSize: '0.875rem' } },
    },

    // ── Table ──────────────────────────────────────────────────────────────
    MuiTableHead: {
      styleOverrides: {
        root: { background: P.slate50 },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontFamily:    FONT,
          fontWeight:    700,
          fontSize:      '0.6875rem',
          textTransform: 'uppercase',
          letterSpacing: '0.07em',
          color:         P.slate400,
          borderBottom:  `1px solid ${P.slate200}`,
          padding:       '10px 14px',
          whiteSpace:    'nowrap',
        },
        body: {
          fontSize:    '0.8125rem',
          color:       P.slate700,
          borderBottom:`1px solid ${P.slate100}`,
          padding:     '11px 14px',
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          '&:hover td': { background: '#F8FAFD' },
          '&:last-child td': { borderBottom: 'none' },
        },
      },
    },

    // ── Accordion ──────────────────────────────────────────────────────────
    MuiAccordion: {
      defaultProps: { disableGutters: true, elevation: 0 },
      styleOverrides: {
        root: {
          border:       `1px solid ${P.slate200}`,
          borderRadius: '12px !important',
          marginBottom: 8,
          '&::before':  { display: 'none' },
          '&.Mui-expanded': { boxShadow: '0 2px 6px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.11)' },
        },
      },
    },
    MuiAccordionSummary: {
      styleOverrides: {
        root: { padding: '0 18px', minHeight: 52, fontWeight: 600 },
        content: { margin: '14px 0' },
      },
    },
    MuiAccordionDetails: {
      styleOverrides: { root: { padding: '4px 18px 18px' } },
    },

    // ── LinearProgress ─────────────────────────────────────────────────────
    MuiLinearProgress: {
      styleOverrides: {
        root:        { borderRadius: 999, height: 7, background: P.slate100 },
        bar:         { borderRadius: 999 },
        colorPrimary:{ '& .MuiLinearProgress-bar': { background: `linear-gradient(90deg, ${P.blue}, #60A5FA)` } },
        colorSuccess:{ '& .MuiLinearProgress-bar': { background: `linear-gradient(90deg, ${P.green}, #34D399)` } },
        colorWarning:{ '& .MuiLinearProgress-bar': { background: `linear-gradient(90deg, ${P.amber}, #FCD34D)` } },
        colorError:  { '& .MuiLinearProgress-bar': { background: `linear-gradient(90deg, ${P.red}, #F87171)` } },
      },
    },

    // ── Alert ──────────────────────────────────────────────────────────────
    MuiAlert: {
      styleOverrides: {
        root:             { borderRadius: 12, fontWeight: 500 },
        standardSuccess:  { background: '#F0FDF4', color: '#14532D', borderLeft: `4px solid ${P.green}` },
        standardWarning:  { background: '#FFFBEB', color: '#78350F', borderLeft: `4px solid ${P.amber}` },
        standardError:    { background: '#FEF2F2', color: '#7F1D1D', borderLeft: `4px solid ${P.red}` },
        standardInfo:     { background: '#EFF6FF', color: '#1E3A8A', borderLeft: `4px solid ${P.blue}` },
      },
    },

    // ── Skeleton ───────────────────────────────────────────────────────────
    MuiSkeleton: {
      styleOverrides: {
        root:        { borderRadius: 8 },
        rectangular: { borderRadius: 12 },
      },
    },

    // ── Tooltip ────────────────────────────────────────────────────────────
    MuiTooltip: {
      defaultProps: { arrow: true },
      styleOverrides: {
        tooltip: {
          background:   P.slate900,
          borderRadius: 8,
          fontSize:     '0.75rem',
          fontWeight:   500,
          padding:      '6px 10px',
        },
      },
    },

    // ── Menu ───────────────────────────────────────────────────────────────
    MuiMenu: {
      styleOverrides: {
        paper: { borderRadius: 12, border: `1px solid ${P.slate200}`, boxShadow: '0 4px 10px rgba(15,23,42,0.07), 0 16px 40px rgba(15,23,42,0.13)' },
        list:  { padding: '6px' },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontSize:     '0.875rem',
          fontWeight:   500,
          padding:      '8px 12px',
          '&:hover':    { background: P.slate100 },
          '&.Mui-selected': { background: P.blue50, color: P.blue, '&:hover': { background: P.blue100 } },
        },
      },
    },

    // ── Divider ────────────────────────────────────────────────────────────
    MuiDivider: {
      styleOverrides: { root: { borderColor: P.slate200 } },
    },

    // ── Badge ──────────────────────────────────────────────────────────────
    MuiBadge: {
      styleOverrides: {
        badge: { fontFamily: FONT, fontWeight: 700, fontSize: '0.625rem' },
      },
    },
  },
})

// ── Export colour palette for use in components ──────────────────────────────
export const palette = P
export const monoFont = MONO
