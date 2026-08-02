// fmt.ts — number / string formatting helpers

export function fmtInr(n: number | null | undefined, compact = false): string {
  // Number.isFinite, not isNaN: isNaN(Infinity) is false, so a divide-by-zero ratio
  // used to sail through and render as "Infinity".
  if (n == null || !Number.isFinite(n)) return '₹0'
  const neg = n < 0
  const absVal = Math.abs(n)
  let result: string

  if (compact) {
    const absRound = Math.round(absVal)
    if (absRound >= 1_00_00_000) result = `₹${(absVal / 1_00_00_000).toFixed(2)} Cr`
    else if (absRound >= 1_00_000) result = `₹${(absVal / 1_00_000).toFixed(2)} L`
    else result = `₹${Math.round(absVal).toLocaleString('en-IN')}`
  } else {
    // Indian numbering with decimals
    const parts = absVal.toFixed(2).split('.')
    const integerPart = parts[0]
    const decimalPart = parts[1] === '00' ? '' : `.${parts[1]}`

    if (integerPart.length <= 3) {
      result = `₹${integerPart}${decimalPart}`
    } else {
      const last3 = integerPart.slice(-3)
      const rest  = integerPart.slice(0, -3)
      const commaParts = []
      let tmp = rest
      while (tmp.length > 2) {
        commaParts.unshift(tmp.slice(-2))
        tmp = tmp.slice(0, -2)
      }
      if (tmp) commaParts.unshift(tmp)
      result = `₹${commaParts.join(',')},${last3}${decimalPart}`
    }
  }
  return neg ? `-${result}` : result
}

export function fmtPct(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return '0.00%'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(decimals)}%`
}

export function fmtNum(n: number | null | undefined, decimals = 2): string {
  if (n == null || !Number.isFinite(n)) return '0'
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
