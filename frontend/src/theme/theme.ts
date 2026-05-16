import { createTheme, alpha } from '@mui/material/styles'

const FONT = '"Plus Jakarta Sans", sans-serif'
const MONO = '"DM Mono", monospace'

// ── AlphaTrack Pro Palette ──────────────────────────────────────────────────
const P = {
  background: '#0B1326',
  surface: '#131B2E',
  primary: '#6366F1',
  secondary: '#4EDE93',
  tertiary: '#FF516A',
  outline: 'rgba(255, 255, 255, 0.1)',
  slate50: '#F8FAFC',
  slate400: '#94A3B8',
  slate500: '#64748B',
  slate900: '#0F172A',
}

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: P.primary, light: alpha(P.primary, 0.5), dark: '#4F46E5', contrastText: '#fff' },
    secondary: { main: P.secondary, light: alpha(P.secondary, 0.5), dark: '#10B981', contrastText: '#fff' },
    error: { main: P.tertiary, light: alpha(P.tertiary, 0.5), dark: '#E11D48', contrastText: '#fff' },
    background: { default: P.background, paper: P.surface },
    text: {
      primary: '#F8FAFC',
      secondary: '#94A3B8',
      disabled: alpha('#94A3B8', 0.5),
    },
    divider: P.outline,
  },

  typography: {
    fontFamily: FONT,
    h1: { fontSize: '2.5rem', fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.1 },
    h2: { fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.03em' },
    h3: { fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em' },
    h4: { fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.02em' },
    h5: { fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.01em' },
    h6: { fontSize: '1rem', fontWeight: 700, letterSpacing: '-0.01em' },
    subtitle1: { fontSize: '1rem', fontWeight: 600, letterSpacing: '-0.01em' },
    subtitle2: { fontSize: '0.875rem', fontWeight: 600 },
    body1: { fontSize: '0.9375rem', fontWeight: 400, lineHeight: 1.6 },
    body2: { fontSize: '0.875rem', fontWeight: 400, lineHeight: 1.55 },
    caption: { fontSize: '0.75rem', fontWeight: 400, color: P.slate400 },
    overline: {
      fontSize: '0.6875rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.15em',
      color: P.primary,
    },
    button: { fontFamily: FONT, fontWeight: 700, fontSize: '0.875rem', letterSpacing: '0.02em', textTransform: 'none' },
  },

  shape: { borderRadius: 16 },

  shadows: [
    'none',
    '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
    '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
    '0 0 30px rgba(99, 102, 241, 0.2)', // Glow shadow for cards
    ...Array(20).fill('none'),
  ] as any,

  components: {
    MuiCssBaseline: {
      styleOverrides: `
        *, *::before, *::after { box-sizing: border-box; }
        html { -webkit-font-smoothing: antialiased; scroll-behavior: smooth; }
        body { 
          background: ${P.background}; 
          font-family: ${FONT}; 
          color: #F8FAFC;
          overflow-x: hidden;
        }
        /* AlphaTrack Pro Scrollbars */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { 
          background: ${alpha(P.primary, 0.2)}; 
          border-radius: 999px; 
        }
        ::-webkit-scrollbar-thumb:hover { background: ${P.primary}; }
        
        .num { font-family: ${MONO} !important; letter-spacing: -0.02em; font-weight: 500; }
        .glass {
          background: rgba(19, 27, 46, 0.6) !important;
          backdrop-filter: blur(40px) !important;
          -webkit-backdrop-filter: blur(40px) !important;
          border: 1px solid rgba(99, 102, 241, 0.2) !important;
          box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.05) !important;
        }
      `,
    },

    MuiAppBar: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          background: alpha(P.background, 0.8),
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderBottom: `1px solid ${P.outline}`,
          color: '#fff',
        },
      },
    },

    MuiDrawer: {
      styleOverrides: {
        paper: {
          background: alpha(P.surface, 0.95),
          backdropFilter: 'blur(20px)',
          borderRight: `1px solid ${P.outline}`,
          width: 280,
        },
      },
    },

    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: {
          borderRadius: 24,
          background: 'rgba(19, 27, 46, 0.6)',
          backdropFilter: 'blur(40px)',
          border: '1px solid rgba(99, 102, 241, 0.2)',
          transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translateY(-4px)',
            borderColor: alpha(P.primary, 0.4),
            boxShadow: '0 0 30px rgba(99, 102, 241, 0.2)',
          },
        },
      },
    },

    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { backgroundImage: 'none' },
        rounded: { borderRadius: 24 },
      },
    },

    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          borderRadius: 14,
          fontWeight: 700,
          padding: '12px 28px',
          transition: 'all 200ms ease',
        },
        containedPrimary: {
          background: `linear-gradient(135deg, ${P.primary}, #4F46E5)`,
          boxShadow: `0 4px 14px 0 ${alpha(P.primary, 0.39)}`,
          '&:hover': {
            background: `linear-gradient(135deg, #4F46E5, ${P.primary})`,
            boxShadow: `0 6px 20px rgba(99, 102, 241, 0.45)`,
            transform: 'scale(1.02)',
          },
        },
        outlined: {
          borderColor: alpha(P.primary, 0.3),
          color: P.primary,
          '&:hover': {
            borderColor: P.primary,
            background: alpha(P.primary, 0.08),
          },
        },
      },
    },

    MuiTabs: {
      styleOverrides: {
        root: {
          background: alpha(P.surface, 0.5),
          borderRadius: 20,
          padding: 6,
          minHeight: 48,
        },
        indicator: { display: 'none' },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontWeight: 700,
          fontSize: '0.875rem',
          minHeight: 36,
          borderRadius: 14,
          margin: '0 4px',
          color: P.slate400,
          transition: 'all 0.2s ease',
          '&.Mui-selected': {
            background: P.primary,
            color: '#fff',
            boxShadow: `0 4px 12px ${alpha(P.primary, 0.3)}`,
          },
          '&:hover': {
            color: '#fff',
          },
        },
      },
    },

    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 18,
          fontWeight: 600,
          border: '1px solid transparent',
        },
        standardSuccess: {
          background: alpha(P.secondary, 0.1),
          color: P.secondary,
          borderColor: alpha(P.secondary, 0.2),
        },
        standardError: {
          background: alpha(P.tertiary, 0.1),
          color: P.tertiary,
          borderColor: alpha(P.tertiary, 0.2),
        },
      },
    },

    MuiTooltip: {
      defaultProps: { arrow: true },
      styleOverrides: {
        tooltip: {
          background: '#1E293B',
          borderRadius: 10,
          fontSize: '0.8125rem',
          padding: '8px 12px',
          border: `1px solid ${P.outline}`,
        },
      },
    },
  },
})

export const palette = P
export const monoFont = MONO
