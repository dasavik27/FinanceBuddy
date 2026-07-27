/**
 * rules/taxRules.ts
 * Centralized Indian Mutual Fund Tax Rulebook (Updated for Budget 2024 & beyond)
 * Single source of truth for tax classification, slabs, and exemptions across Finance Buddy.
 */

export interface TaxProfile {
  stcgRate: number;
  ltcgRate: number;
  stcgLabel: string;
  ltcgLabel: string;
  stcgVal: string;
  ltcgVal: string;
  note: string;
}

export const INDIAN_TAX_SLABS = {
  equity_stcg: 0.20, // 20%
  equity_ltcg: 0.125, // 12.5%
  debt_proxy_slab: 0.30, // 30% proxy for income tax slab
  ltcg_exemption_inr: 125000, // ₹1.25L annual exemption
};

export function getTaxProfile(category: string): TaxProfile {
  const cat = (category || '').toUpperCase();

  // 1. ELSS (Equity Linked Savings Scheme)
  if (cat.includes('ELSS')) {
    return {
      stcgRate: 0,
      ltcgRate: INDIAN_TAX_SLABS.equity_ltcg,
      stcgLabel: 'STCG (N/A)',
      ltcgLabel: 'LTCG (>3Y)',
      stcgVal: 'N/A (Lock-in)',
      ltcgVal: `${INDIAN_TAX_SLABS.equity_ltcg * 100}% (above ₹1.25L)`,
      note: 'ELSS qualifies for ₹1.5L deduction u/s 80C. 3-year mandatory lock-in. LTCG taxed at 12.5% without indexation.',
    };
  }

  // 2. Debt / Liquid / Money Market / Conservative
  const isDebt = ['DEBT', 'LIQUID', 'GILT', 'BOND', 'OVERNIGHT', 'MONEY MARKET', 'INCOME', 'CREDIT RISK'].some(k => cat.includes(k));
  if (isDebt) {
    return {
      stcgRate: INDIAN_TAX_SLABS.debt_proxy_slab,
      ltcgRate: INDIAN_TAX_SLABS.debt_proxy_slab,
      stcgLabel: 'STCG (Slab)',
      ltcgLabel: 'LTCG (Slab)',
      stcgVal: 'Slab Rate',
      ltcgVal: 'Slab Rate',
      note: 'Post Apr 2023: all debt mutual fund gains are taxed at your income tax slab (proxied at 30%). No indexation benefit.',
    };
  }

  // 3. Core Equity / Index / Sectoral / Flexi
  return {
    stcgRate: INDIAN_TAX_SLABS.equity_stcg,
    ltcgRate: INDIAN_TAX_SLABS.equity_ltcg,
    stcgLabel: 'STCG (<1Y)',
    ltcgLabel: 'LTCG (>1Y)',
    stcgVal: `${INDIAN_TAX_SLABS.equity_stcg * 100}.0%`,
    ltcgVal: `${INDIAN_TAX_SLABS.equity_ltcg * 100}% (above ₹1.25L)`,
    note: 'Budget 2024: LTCG raised to 12.5% (annual exemption ₹1.25L); STCG raised to 20%. No indexation benefits.',
  };
}
