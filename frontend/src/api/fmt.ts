// fmt.ts — number / string formatting helpers

export function fmtInr(n: number | null | undefined, compact = false): string {
  if (n == null || isNaN(n)) return '₹0'
  const neg = n < 0
  const abs = Math.abs(Math.round(n))
  let result: string
  if (compact) {
    if (abs >= 1_00_00_000) result = `₹${(abs / 1_00_00_000).toFixed(2)} Cr`
    else if (abs >= 1_00_000) result = `₹${(abs / 1_00_000).toFixed(2)} L`
    else result = `₹${abs.toLocaleString('en-IN')}`
  } else {
    // Indian numbering
    const s = String(abs)
    if (s.length <= 3) result = `₹${s}`
    else {
      const last3 = s.slice(-3)
      const rest  = s.slice(0, -3)
      const parts = []
      let tmp = rest
      while (tmp.length > 2) { parts.unshift(tmp.slice(-2)); tmp = tmp.slice(0, -2) }
      if (tmp) parts.unshift(tmp)
      result = `₹${parts.join(',')},${last3}`
    }
  }
  return neg ? `-${result}` : result
}

export function fmtPct(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return '0.00%'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(decimals)}%`
}

export function fmtNum(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return '0'
  return n.toFixed(decimals)
}

export function gainColor(n: number): string {
  return n >= 0 ? '#059669' : '#DC2626'
}

export function gainBg(n: number): string {
  return n >= 0 ? '#ECFDF5' : '#FEF2F2'
}

export function verdictColor(v: string): string {
  return v === 'Strong' ? '#059669' : v === 'Average' ? '#D97706' : '#DC2626'
}
export function verdictBg(v: string): string {
  return v === 'Strong' ? '#ECFDF5' : v === 'Average' ? '#FFFBEB' : '#FEF2F2'
}
export function verdictBorder(v: string): string {
  return v === 'Strong' ? '#A7F3D0' : v === 'Average' ? '#FDE68A' : '#FECACA'
}
