/**
 * tabCommon.ts
 * 
 * Centralized Shared Logic for Analytical Tabs
 * Contains reusable calculations, constants, and formatting utilities to enforce DRY principles.
 */

export const COLORS = ['#6366F1', '#4EDE93', '#F472B6', '#FBBF24', '#FB7185'];

export const CATEGORY_INSIGHTS: Record<string, { strategy: string, focus: string, timeline: string }> = {
  'Large Cap': {
    strategy: 'Allocates heavily to top 100 blue-chip entities. Acts as a core foundation that prioritizes capital preservation.',
    focus: 'Capital Stability & Dividend Yields',
    timeline: '3 - 5 Years'
  },
  'Mid Cap': {
    strategy: 'Targets fast-growing mid-tier companies ranked 101-250. Offers a balance of scalability and market agility.',
    focus: 'Aggressive Capital Appreciation',
    timeline: '5 - 7 Years'
  },
  'Small Cap': {
    strategy: 'Mandated to target high-alpha micro-companies. Leads aggressive bullish market trends but exhibits deeper volatile pullbacks.',
    focus: 'High Alpha Compounding',
    timeline: '7+ Years'
  },
  'Flexi/Multi Cap': {
    strategy: 'Unconstrained deployment allowing managers to shift between cap sizes based on economic tailwinds.',
    focus: 'All-Weather Diversification',
    timeline: '5 Years'
  },
  'ELSS': {
    strategy: 'Tax-saving equity funds with a 3-year statutory lock-in period. Promotes disciplined compounding.',
    focus: 'Section 80C Tax Breaks & Growth',
    timeline: '3+ Years'
  },
  'Index': {
    strategy: 'Passively tracks primary benchmarks like the Nifty 50. Minimizes active manager risk and maximizes cost efficiency.',
    focus: 'Low-Cost Market Beta',
    timeline: '3 - 5 Years'
  },
  'Debt': {
    strategy: 'Invests in sovereign securities, corporate debentures, and money market instruments to insulate against equity downturns.',
    focus: 'Yield Accrual & Capital Preservation',
    timeline: '1 - 3 Years'
  },
  'Hybrid': {
    strategy: 'Dynamic asset allocation models balancing equity growth momentum with fixed income stability.',
    focus: 'Risk-Adjusted Compounding',
    timeline: '3 - 5 Years'
  }
};

/**
 * Calculates the percentage drawdown from the peak value in a series.
 */
export function calculateDrawdown(values: number[]): number[] {
  if (!values || !values.length) return [];
  let peak = -Infinity;
  return values.map(v => {
    if (v > peak) peak = v;
    return peak === 0 ? 0 : ((v / peak) - 1) * 100;
  });
}
export function getHealthSignal(gainPct: number): { label: string; color: string; bg: string } {
  if (gainPct >= 15) return { label: 'STRONG', color: '#4EDE93', bg: 'rgba(78, 222, 147, 0.1)' }
  if (gainPct >= 5)  return { label: 'WATCH',  color: '#6366F1', bg: 'rgba(99, 102, 241, 0.1)' }
  if (gainPct >= 0)  return { label: 'NEUTRAL', color: '#94A3B8', bg: 'rgba(255, 255, 255, 0.05)' }
  return { label: 'REVIEW', color: '#FF516A', bg: 'rgba(255, 81, 106, 0.1)' }
}
