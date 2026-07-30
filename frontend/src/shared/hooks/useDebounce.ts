import { useEffect, useState } from 'react'

/**
 * Defer a rapidly-changing value until it settles.
 *
 * Exists because several inputs feed straight into a react-query `queryKey`, and a
 * key change is a fetch. Typing "HDFC Small Cap" into an undebounced search box
 * issued 14 sequential GETs, which the backend — one uvicorn worker on ~0.1 shared
 * vCPU — had to serve in order. It also minted 14 distinct cache entries, each
 * retained for the default 5-minute gcTime.
 *
 * Pair with `placeholderData: keepPreviousData` on the query so the UI shows the
 * previous result while the new one is in flight rather than blanking.
 */
export function useDebounce<T>(value: T, delayMs = 300): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return settled
}
