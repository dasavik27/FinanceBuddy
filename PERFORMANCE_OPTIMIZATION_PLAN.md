# Mutual Fund Domain: Performance, Memory & Caching

**Target deployment:** Vercel (frontend) + a free-tier container (backend).
**Backend constraints that drive every decision below:** a single uvicorn worker
(`Dockerfile` has no `--workers`), ~512 MB RAM, ~0.1 shared vCPU.

Two consequences follow from that shape, and they explain most of the choices here:

1. **CPU is the binding constraint, and it is serialized.** One process, one event
   loop, one threadpool. Duplicate computation converts directly into wall-clock
   latency — there is no spare core to absorb it.
2. **In-process caches genuinely are shared caches.** With exactly one worker, a
   module-level dict is visible to every request. This is why there is no Redis in
   this design: a client plus connection pool would cost resident memory and buy
   nothing until we run multiple workers.

---

## What the previous version of this document got wrong

Worth recording, because the mistake was structural rather than a detail.

The earlier plan identified the top bottleneck as *"benchmark/NAV data re-fetched on
every call"* and proposed `fastapi-cache2` + Redis to fix it. But benchmark fetching
was **already cached** before that work started (`market_indices.py`, in-process,
locked, TTL'd). The result was a second cache layered on top of an existing one,
while the actual cost driver went untouched.

Concretely, that effort added:

- `redis`, `aioredis`, `fastapi-cache2` to `requirements.txt` with **zero import
  sites** anywhere in the repo (`aioredis` is also the archived package, superseded by
  `redis-py` ≥ 4.2) — in a file whose own header says *"Verify a package is actually
  imported before adding it."*
- A `FileBasedCache` class that nothing referenced.
- A `/health/cache` endpoint returning a hardcoded dict advertising a Redis backend
  that was never initialized — there was no startup hook in the application at all.
- A `@memoize` decorator applied to the one function that was already cached.
- `Cache-Control: public` on per-session portfolio responses. See below.

The lesson: **measure which layer is hot before choosing an infrastructure answer.**
Redis was a solution to a problem this app did not have.

---

## The actual bottleneck

`compute_period_comparison()` (`backend/domains/mutual_funds/finance.py`) simulates
the portfolio day by day over its full history. Inside the per-day loop it did this,
per fund, **twice** per day (once for start-of-day, once for end-of-day):

```python
past_navs = f_navs[f_navs.index.date <= d_obj]
```

`f_navs.index.date` materializes a brand-new object array of `datetime.date` on every
evaluation, then builds a boolean mask, then allocates a new Series. For a 10-year,
20-fund portfolio that is roughly **146,000 full-series scans per call**.

It was **not cached**, and it is called from five places — about **eight invocations
per dashboard load**:

| Endpoint | Invocations |
|---|---|
| `/overview` | 1 |
| `/benchmark-overlay` | 4 (default query is `"Nifty 50,S&P 500,Gold"`, plus the default benchmark) |
| `/performance` | 1 |
| `/drawdown` | 1 — runs the entire simulation only to read `comp["portfolio"]` |
| `/journey` | 1 — at `days=9999` |

The frontend fires these concurrently. On one shared vCPU they queue. That is the
5–10 s dashboard latency.

Other confirmed redundancy in a single `/performance` request:

- `_get_standard_ledger` (an `iterrows` rebuild) ran **3N + 4** times for N funds.
- `compute_trailing_returns(benchmark)` was recomputed **per fund**, though funds
  share benchmarks.
- `compute_consistency_score` was called **twice with identical arguments**.
- `/insights` called `get_summary()` (full benchmark fetch + two XIRRs) purely to read
  `alpha`, then recomputed a byte-identical copy of the expense-drag loop that
  `get_summary()` had just run.
- The benchmark cache keyed on `f"{ticker}_{period_days}"`, so one dashboard load
  downloaded the **same index three times** (at 1855, 9999, and `perf_days+30` days).
- `_fetch_amfi_data()` — the multi-MB AMFI `NAVAll.txt` download — was **completely
  uncached**, and `fetch_live_navs_with_date()` explicitly bypassed caching with the
  comment *"date mapping is not cached yet"*. It runs on every upload and every
  `/sync`. A single unresolvable ISIN re-triggered the whole download per lookup.
- `fetch_nav_series_by_code()`'s cache **hit** path ran `to_datetime` over the fund's
  entire NAV history plus a sort — per holding, per request. A hit cost nearly as much
  as a miss.

---

## Security fix (shipped first, independent of performance)

`get_cache_headers()` emitted `Cache-Control: public, max-age=N` for **every** type,
and it had just been applied to `/summary`, `/overview`, `/allocation` and
`/benchmark-overlay` — endpoints that return one user's holdings.

`public` explicitly authorizes *shared* caches (a CDN, a corporate proxy, an ISP
cache) to store the response and serve it to a different user. This was a data-leak
risk, not a tuning issue.

Cache policy is now a declared, tested property of each data type:

- User-derived (`portfolio_summary`, `holdings_detail`, `performance_metrics`,
  `tax_calculations`, `rebalance_roadmap`) → `private` or `no-store`.
- Only genuinely user-independent market data may be `public`.
- Unknown types **fail closed** to `no-store`.

`backend/tests/test_cache_core.py` asserts no user-derived type can ever be marked
`public`, so this cannot silently regress.

---

## Architecture: three cache tiers with distinct jobs

The previous design called itself "4-layer with fallback" but was three unconnected
pieces plus a config dict. The tiers now differ in purpose, not just in name.

### L0 — request-scoped memo (`request_scope`, `request_memo`)

A dict on the request, established by `RequestCacheMiddleware` and discarded with the
response. No TTL, no eviction, no growth. Kills duplicate work *within* one request —
the `3N+4` ledger rebuilds, repeated NAV lookups, repeated benchmark resolution.

Implemented with a `ContextVar` rather than a thread-local, because FastAPI runs sync
endpoints in a threadpool and anyio copies the context into the worker thread. Outside
a request it degrades to a pass-through, so decorated helpers stay usable from scripts
and tests.

### L1 — bounded process cache (`ProcessCache`)

LRU + TTL, holding **parsed** objects (`pd.Series`, `DataFrame`, result dicts).

- **Bounded by bytes, not entry count.** Entry count is a poor proxy when one entry is
  a 3-element dict and the next is a 3700×20 float frame. The previous `memoize` store
  was an unbounded dict — on a 512 MB box, a slow memory leak.
- **Single-flight per key.** N concurrent misses for the same key produce one
  computation; the rest wait and read the winner's result. This is the win that
  survives a cold cache, and on a single 0.1-vCPU worker it is the most valuable
  property in the whole design.
- **Copy-on-read.** Returning a cached object by reference lets any caller's in-place
  edit corrupt every later reader — and `fetch_benchmark_series` already copies on both
  sides *specifically* to prevent that, which the previous `@memoize` silently undid.
  Large read-only payloads can opt out via `copy_on_read=False` (used only for the AMFI
  bundle, with a documented rationale).
- Two separate budgets (`MARKET_CACHE` 32 MB, `DERIVED_CACHE` 24 MB) so a burst of
  large derived artifacts cannot evict the NAV series everything else depends on.
- Real hit/miss/eviction counters, surfaced by `/health/cache`.

### L2 — disk cache (`MarketCache`)

Raw network payloads as JSON, surviving restart. Hardened:

- **Atomic writes** (temp file + `os.replace`). The previous `open()` + `json.dump()`
  let a concurrent reader observe a truncated file.
- **Non-lossy keys.** Sanitization alone mapped `nav_series_a-b` and `nav_series_a_b`
  onto the same file — two different schemes could serve each other's NAV history. That
  was a correctness bug, not a performance one. Keys are now hash-suffixed.
- **Expired entries are deleted on read**, not merely reported as misses.
- **Size budget with oldest-first eviction** (64 MB default), swept on a rate limit and
  from the session GC thread. The directory previously only grew.
- `invalidate("")` **no longer wipes the entire cache** — the pattern is required, and
  `invalidate_all()` exists for when that is genuinely intended.

> **Free-tier caveat:** free hosting tiers generally provide no persistent disk and
> spin down when idle. On those, L2 *and* the SQLite session store are cleared on
> restart. Treat L2 as a warm-start optimization, not as storage — and note this is
> exactly why the algorithmic work matters: you cannot cache your way out of a cache
> that keeps vanishing.

### Invalidation: content-addressed, so there isn't any

`derived.cached_period_comparison()` keys on a hash of the actual input frames plus
portfolio value and benchmark identity. If any input changes, the key changes — a
stale entry becomes unreachable rather than wrong.

This removes a whole class of bug. It also removed the `1 + 2N` full directory scans
`/sync` performed per N-fund portfolio (each `invalidate()` call scanned the entire
cache directory); those are now exact-key deletes.

Fingerprinting uses `pd.util.hash_pandas_object` — vectorized C, microseconds for a
few thousand rows, against a simulation measured in seconds. If a frame cannot be
hashed, the code **recomputes rather than guessing**: serving a wrong-but-plausible
portfolio would be far worse than being slow.

---

## Memory

- **`_SESSIONS` is now bounded** (LRU, default 3 resident) **and locked.** It was an
  unbounded plain dict mutated by both request threads and the GC daemon without a
  lock; steady-state size was "however many uploads happened in the last 4 hours."
  Eviction is safe because rehydration from SQLite already existed.
- **Rehydration now refreshes live NAVs.** This was previously skipped "to save API
  calls," leaving disk-restored portfolios valued at CAS-era NAVs — a correctness
  problem that memory-bounded eviction would have made routine. It is affordable now
  precisely *because* the AMFI bundle is cached: normally a dict lookup, not a download.
- **`category` dtype** for repeated string columns (`Fund`, `AMC`, `Category`, `Type`,
  …). A fund name as `object` is a separate ~90-byte Python string per row; as
  `category` it is one small integer plus a single copy of each distinct value.
- **Money columns are deliberately left as `float64`.** `float32` carries ~7
  significant digits and an amount like `10000000.50` needs 10 — the "obvious" memory
  saving would silently corrupt cost basis and XIRR inputs. There is a test pinning
  this decision.
- **Lazy imports** for `yfinance` and `casparser`, both of which were eager at startup
  and neither of which is needed until a specific endpoint runs. Follows the pattern
  already documented in `requirements.txt` for camelot/OpenCV. *(Investigated and
  cleared: camelot, OpenCV, pdfplumber and nsepython were already lazy.)*
- **`df_to_records` vectorized.** It ran a Python lambda over every cell — rows ×
  columns interpreter calls on every `/holdings` and `/transactions` request.
- **`CACHE_DIR` is no longer CWD-relative.** It depended on where the process was
  launched from, producing multiple independent cache directories that never shared a
  hit.

---

## Database

`load_session()` runs `SELECT * FROM mf_* WHERE session_id=?` against three tables that
hold **every** session's rows until the 24-hour purge. There were no indexes on
`session_id`, so each rehydration was three full table scans across unrelated sessions'
data.

This was latent before — sessions stayed resident indefinitely, so the path was rare.
Capping resident sessions made rehydration routine and turned a dormant problem into a
hot one, so the indexes are a direct requirement of that change rather than an
independent nicety.

Added `idx_mf_{holdings,transactions,sips}_session_id`, plus
`idx_sessions_created_at` for the GC sweep's `created_at < datetime('now','-24 hours')`
scan. Because the `mf_*` tables are created implicitly by `DataFrame.to_sql`, indexes
are ensured both in `_init_db()` (existing databases) and after the `to_sql` calls in
`save_session()` (fresh databases); `CREATE INDEX IF NOT EXISTS` makes both idempotent.

Verified via `EXPLAIN QUERY PLAN`, which changed from `SCAN mf_transactions` to
`SEARCH mf_transactions USING INDEX idx_mf_transactions_session_id (session_id=?)`.

---

## Peer comparison

`get_diverse_category_peers()` was the largest remaining latency source: up to eight
uncached fund searches, **thirty sequential** mfapi NAV round-trips, and thirty
risk-metric computations — all re-run in full on every `/compare/peers` request.

- **NAV histories are now fetched concurrently** (`_prefetch_peer_navs`, 8 workers).
  These are network-bound, so threads help even on a shared vCPU — the GIL is released
  during the HTTP wait. The metric loop still iterates peers in the original order
  afterwards, so results and tie-breaking are unchanged; only the waiting overlaps.
- **The whole result is cached and single-flighted** (30 min). A category's peer set is
  user-independent fund data, so one entry serves every caller.
- **`search_mutual_funds` is cached**, which also benefits `/compare/search`.
- **`compute_consistency_score` no longer runs twice** with identical arguments in the
  fallback-harvest branch (once for the number, once for the display string).

Not parallelized: the fallback "veteran harvesting" branch, which only runs when the
primary search yields too few diverse peers and is inherently sequential (it stops as
soon as it has enough).

---

## Verified results

### CPU: vectorization

The shared anti-pattern was a boolean mask over a full-length Series *inside* a loop.
Replaced with one up-front conversion of the index to an `int64` epoch array plus
`np.searchsorted`; `compute_period_comparison` additionally became a wide day×fund NAV
matrix, a units-per-day matrix, and an `np.einsum` row-wise multiply-and-sum.

Benchmarked at 20 funds / 3650 days / 2445 transactions, "before" being the literal
reference transcription in the test file:

| Function | Before | After | Speedup |
|---|---|---|---|
| `compute_period_comparison` | 560,321 ms | **210 ms** | **~2670×** |
| `compute_consistency_score` | 230 ms | 7.5 ms | ~31× |
| `compute_benchmark_xirr` | 1,332 ms | 50 ms | ~27× |
| `compute_rolling_return_series` | 576 ms | 25 ms | ~23× |
| `compute_rolling_return_avg` | 739 ms | 34 ms | ~22× |
| `_get_standard_ledger` | 219 ms | 14 ms | ~16× |

Independently re-verified at a smaller size (6 funds / 900 days) to confirm direction
and numerical agreement: `compute_period_comparison` 21,547 ms → 121 ms (177×), with
`port_pct`, `bench_pct`, both value scalars and the full chart series agreeing at
`rtol=1e-9`. The reference is roughly quadratic in days×funds, which is why the
speedup grows with portfolio size.

At eight invocations per dashboard load, that single function went from roughly
75 minutes of CPU to about 1.7 s — and the derived cache then reduces the eight to
the number of genuinely distinct inputs.

Two notes from the work:
- **`float64`, not `float32`, for the NAV matrix.** float32's ~7 significant digits
  shift a rupee-denominated market value of ~1e6 by ~0.1, which the equivalence tests
  caught at `rtol=1e-9`. Memory cost of float64 is negligible (584 KB for 3650×20).
  This is the second place where the obvious memory optimization was wrong for money.
- **One deliberate behaviour change**, documented at `finance.py:43-53`: a transaction
  row whose *only* non-null value was the date previously raised `TypeError` (an
  artifact of `iterrows` re-inferring a dtype per row); it is now skipped. Reaching it
  requires a row with no Fund, no Type and no Amount/Units/NAV. Crash → no-op.

### Caching and memory

| Metric | Before | After |
|---|---|---|
| Startup traced memory | 64.0 MB | **50.3 MB** |
| Eager heavy imports | `yfinance`, `casparser` | none |
| AMFI downloads for 3 consumers + repeat | 4 | **1** |
| Repeat lookups of an unresolvable ISIN | 1 download each | **0** after first |
| Dashboard simulation pattern (8 calls) | 8 computations | **3** (distinct inputs only) |
| 6 concurrent identical requests | 6 computations | **1** |
| Benchmark downloads per dashboard load | 3 per index | **1** per index |
| Disk cache bound | none (grew forever) | **64 MB**, oldest-first eviction |
| Resident sessions | unbounded, unlocked | **3**, LRU + locked |
| Test count | 51 | **143** |

Still unmeasured: end-to-end dashboard latency against a live session, which needs a
real CAS upload and network access. Everything above is measured in-process.

---

## Instrumentation

`TimingMiddleware` adds a `Server-Timing: total;dur=<ms>` header to every response and
logs any request slower than `FINANCEBUDDY_SLOW_REQUEST_MS` (default 1500) with its
path. `/health/cache` returns live hit/miss/eviction counters per tier.

The point is that the next person to ask "is this actually faster?" can answer it from
the logs instead of re-deriving it from the code.

---

## Testing approach

The four hottest functions in `finance.py` had **zero test coverage** before this work,
and they are financial calculations — a silent numerical regression there is worse than
being slow.

Following the pattern already established by `tests/test_reconciliation_equivalence.py`,
`tests/test_finance_equivalence.py` transcribes each original implementation as a
`reference_*` function and pins the optimized version against it over randomized inputs
with a fixed seed. Network access is stubbed at the defining modules (the functions use
function-local imports, so patching the caller's namespace would not intercept them) and
a live-HTTP attempt fails the test loudly rather than hanging.

**If those tests fail, the optimization changed behaviour and is wrong. The reference is
the specification.**

---

## Remaining work

- **`/benchmark-overlay` runs one full simulation per benchmark**, although the
  *portfolio* half of each result is identical — only the benchmark curve differs.
  Splitting `compute_period_comparison` into a portfolio pass plus a cheap benchmark
  alignment would remove that redundancy. Currently mitigated by the cache absorbing the
  overlap between the default benchmark and the first list entry.
- **`compute_xirr_by_fy`** is `O(FY × funds × txns)` — it rebuilds FIFO lots per
  (financial year × fund).
- **`ThreadPoolExecutor(max_workers=8/10)`** is right for network fan-out but wrong for
  the mixed CPU work in `_compute_fund_performance`; 8 threads of GIL-bound pandas on
  0.1 vCPU adds contention without parallelism. Split the I/O and CPU phases.
- **`sessions.py` retention claim** has been corrected in the docstring; the wider
  privacy posture (SQLite rows persist for 24 h) is worth an explicit product decision
  rather than an implementation detail.
