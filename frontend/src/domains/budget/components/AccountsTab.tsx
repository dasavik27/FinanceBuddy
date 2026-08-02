import React, { useCallback, useMemo, useState } from 'react'
import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Divider,
  LinearProgress, Skeleton, Stack, TextField, Tooltip, Typography,
} from '@mui/material'
import type { SxProps } from '@mui/material'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import EditIcon from '@mui/icons-material/Edit'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

import {
  budgetErrorDetail, useBudgetAccounts, useBudgetCoverage, useBudgetReconciliation,
  useUpdateBudgetAccount,
} from '../hooks/useBudget'
import type {
  BudgetAccount, BudgetAccountMetaUpdate, BudgetCoverageAccount,
  BudgetReconciliationAccount, UtilisationStatus,
} from '../types'

interface AccountsTabProps {
  sessionId: string
}

// ── Palette and shared sx ────────────────────────────────────────────────────
//
// Every `sx` that does not depend on props lives at module level. An object literal
// in JSX has a fresh identity on each render, so emotion re-serialises it every time -
// with one card per account and half a dozen styled nodes per card that adds up, and
// it is the pattern the rest of the domain now follows.

const TEXT = '#e2e8f0'
const MUTED = '#94a3b8'
const GREEN = '#34d399'
const AMBER = '#fbbf24'
const RED = '#f87171'

const CARD_BORDER = '1px solid rgba(148, 163, 184, 0.15)'

const UTILISATION_COLOR: Record<UtilisationStatus, string> = {
  healthy: GREEN,
  warning: AMBER,
  critical: RED,
}

/** Cap on how many missing months are listed before collapsing into "+N more". */
const MISSING_MONTHS_SHOWN = 6

const ROOT_SX: SxProps = { color: TEXT }

const SUMMARY_STRIP_SX: SxProps = {
  display: 'grid',
  gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' },
  gap: 2,
  mb: 3,
}

const SUMMARY_TILE_SX: SxProps = {
  p: 2,
  borderRadius: 2,
  background: 'rgba(30, 41, 59, 0.5)',
  border: CARD_BORDER,
}

const SUMMARY_LABEL_SX: SxProps = {
  color: MUTED, fontSize: '0.75rem', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.04em',
}
const SUMMARY_VALUE_SX: SxProps = { color: TEXT, fontSize: '1.5rem', fontWeight: 700, mt: 0.5 }
const SUMMARY_VALUE_CARD_SX: SxProps = { color: RED, fontSize: '1.5rem', fontWeight: 700, mt: 0.5 }
const SUMMARY_SUB_SX: SxProps = { color: MUTED, fontSize: '0.75rem', mt: 0.25 }

const WARNING_PANEL_SX: SxProps = {
  p: 2,
  mb: 3,
  borderRadius: 2,
  background: 'rgba(245, 158, 11, 0.10)',
  border: '1px solid rgba(245, 158, 11, 0.35)',
}
const WARNING_TITLE_SX: SxProps = {
  color: AMBER, fontWeight: 700, fontSize: '0.9rem',
  display: 'flex', alignItems: 'center', gap: 0.75,
}
const WARNING_BODY_SX: SxProps = { color: '#fcd34d', fontSize: '0.8rem', mt: 0.5 }
const WARNING_ITEM_SX: SxProps = { color: '#fde68a', fontSize: '0.8rem' }

const GRID_SX: SxProps = {
  display: 'grid',
  gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
  gap: 2,
}

const CARD_SX: SxProps = {
  p: 2,
  borderRadius: 2,
  background: 'rgba(30, 41, 59, 0.5)',
  border: CARD_BORDER,
  display: 'flex',
  flexDirection: 'column',
  gap: 1.25,
}

const CARD_HEAD_SX: SxProps = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1,
}
const CARD_LABEL_SX: SxProps = { color: TEXT, fontWeight: 700, fontSize: '1rem', lineHeight: 1.3 }
const CARD_META_SX: SxProps = { color: MUTED, fontSize: '0.75rem', mt: 0.25 }
const EDIT_BTN_SX: SxProps = {
  minWidth: 'auto', p: 0.5, color: MUTED, '&:hover': { color: '#a5b4fc' },
}

const HEADLINE_LABEL_SX: SxProps = { color: MUTED, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.04em' }
const HEADLINE_BALANCE_SX: SxProps = { color: GREEN, fontWeight: 700, fontSize: '1.4rem' }
const HEADLINE_OUTSTANDING_SX: SxProps = { color: RED, fontWeight: 700, fontSize: '1.4rem' }
const HEADLINE_MISSING_SX: SxProps = {
  color: MUTED, fontWeight: 700, fontSize: '1.4rem',
  borderBottom: '1px dotted rgba(148, 163, 184, 0.5)', cursor: 'help',
}

const FLOW_ROW_SX: SxProps = { display: 'flex', gap: 2, flexWrap: 'wrap' }
const FLOW_IN_SX: SxProps = { color: GREEN, fontSize: '0.8rem', fontWeight: 600 }
const FLOW_OUT_SX: SxProps = { color: RED, fontSize: '0.8rem', fontWeight: 600 }

const barSx = (color: string): SxProps => ({
  height: 8,
  borderRadius: 4,
  backgroundColor: 'rgba(148, 163, 184, 0.15)',
  '& .MuiLinearProgress-bar': { backgroundColor: color, borderRadius: 4 },
})

const UTILISATION_BAR_SX: Record<UtilisationStatus, SxProps> = {
  healthy: barSx(GREEN),
  warning: barSx(AMBER),
  critical: barSx(RED),
}

const utilTextSx = (color: string): SxProps => ({ color, fontSize: '0.78rem', fontWeight: 600 })

const UTILISATION_TEXT_SX: Record<UtilisationStatus, SxProps> = {
  healthy: utilTextSx(GREEN),
  warning: utilTextSx(AMBER),
  critical: utilTextSx(RED),
}

const MISSING_LIMIT_SX: SxProps = {
  alignSelf: 'flex-start',
  textTransform: 'none',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: AMBER,
  borderColor: 'rgba(245, 158, 11, 0.4)',
  '&:hover': { borderColor: AMBER, background: 'rgba(245, 158, 11, 0.08)' },
}

const SCHEDULE_ROW_SX: SxProps = { color: MUTED, fontSize: '0.75rem', display: 'flex', gap: 2, flexWrap: 'wrap' }

const DIVIDER_SX: SxProps = { borderColor: 'rgba(148, 163, 184, 0.12)' }

const HEALTH_ROW_SX: SxProps = { display: 'flex', flexDirection: 'column', gap: 0.5 }
const HEALTH_OK_SX: SxProps = { color: GREEN, fontSize: '0.75rem', fontWeight: 600 }
const HEALTH_WARN_SX: SxProps = { color: AMBER, fontSize: '0.75rem', fontWeight: 600 }
const HEALTH_NEUTRAL_SX: SxProps = { color: MUTED, fontSize: '0.75rem' }

const ERROR_PANEL_SX: SxProps = {
  p: 3,
  borderRadius: 2,
  background: 'rgba(239, 68, 68, 0.08)',
  border: '1px solid rgba(239, 68, 68, 0.3)',
}
const ERROR_TITLE_SX: SxProps = { color: RED, fontWeight: 700, fontSize: '0.95rem' }
const ERROR_BODY_SX: SxProps = { color: '#fca5a5', fontSize: '0.85rem', mt: 0.5, mb: 2 }
const RETRY_BTN_SX: SxProps = { textTransform: 'none', fontWeight: 600 }

const EMPTY_PANEL_SX: SxProps = {
  p: 6,
  textAlign: 'center',
  borderRadius: 2,
  background: 'rgba(30, 41, 59, 0.5)',
  border: CARD_BORDER,
  color: MUTED,
}

const SKELETON_SX: SxProps = { bgcolor: 'rgba(148, 163, 184, 0.12)', borderRadius: 2 }
const SKELETON_CARD_SX: SxProps = { bgcolor: 'rgba(148, 163, 184, 0.10)', borderRadius: 2 }

const DIALOG_PAPER_SX: SxProps = {
  background: '#0f172a',
  border: CARD_BORDER,
  borderRadius: 2,
  backgroundImage: 'none',
}
const DIALOG_TITLE_SX: SxProps = { color: TEXT, fontWeight: 700, fontSize: '1.05rem' }
const DIALOG_HINT_SX: SxProps = { color: MUTED, fontSize: '0.75rem', mb: 2 }
const DIALOG_ERROR_SX: SxProps = {
  mt: 2, p: 1.5, borderRadius: 2, fontSize: '0.8rem', color: '#fca5a5',
  background: 'rgba(239, 68, 68, 0.10)', border: '1px solid rgba(239, 68, 68, 0.3)',
}
const FIELD_SX: SxProps = {
  '& .MuiInputBase-input': { color: TEXT },
  '& .MuiInputLabel-root': { color: MUTED },
  '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(148, 163, 184, 0.25)' },
}
const DIALOG_FIELDS_SX: SxProps = {
  display: 'grid',
  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
  gap: 2,
  mt: 0.5,
}
const PAPER_PROPS = { sx: DIALOG_PAPER_SX }
const CANCEL_BTN_SX: SxProps = { textTransform: 'none', color: MUTED }
const SAVE_BTN_SX: SxProps = { textTransform: 'none', fontWeight: 600 }

const CARD_ICON = (
  <CreditCardIcon style={{ fontSize: 15, color: '#f472b6', verticalAlign: '-2px' }} />
)
const DEPOSIT_ICON = (
  <AccountBalanceIcon style={{ fontSize: 15, color: MUTED, verticalAlign: '-2px' }} />
)

/**
 * Why a card can show "—" instead of a figure.
 *
 * `balance` and `outstanding` are nullable by design and never both set. Rendering
 * `?? 0` would tell the user a card owes nothing when the truth is that the statement
 * carried no balance column - a wrong number is worse than an absent one.
 */
const NO_BALANCE_TOOLTIP =
  'No balance data in the uploaded statement, and no opening balance set. This is not the same as zero - set an opening balance to have it computed.'

// ── Formatting ───────────────────────────────────────────────────────────────

const money = (value: number): string =>
  `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

const dateRange = (first: string | null, last: string | null): string | null => {
  if (!first && !last) return null
  if (first && last) return first === last ? first : `${first} – ${last}`
  return (first || last) as string
}

// ── Summary strip ────────────────────────────────────────────────────────────

interface SummaryStripProps {
  depositBalance: number
  cardOutstanding: number
  accountCount: number
  cardCount: number
}

const SummaryStrip = React.memo(function SummaryStrip({
  depositBalance, cardOutstanding, accountCount, cardCount,
}: SummaryStripProps) {
  return (
    <Box sx={SUMMARY_STRIP_SX}>
      <Box sx={SUMMARY_TILE_SX}>
        <Typography sx={SUMMARY_LABEL_SX}>Deposit balance</Typography>
        <Typography sx={SUMMARY_VALUE_SX}>{money(depositBalance)}</Typography>
      </Box>
      <Box sx={SUMMARY_TILE_SX}>
        <Typography sx={SUMMARY_LABEL_SX}>Card outstanding</Typography>
        <Typography sx={SUMMARY_VALUE_CARD_SX}>{money(cardOutstanding)}</Typography>
      </Box>
      <Box sx={SUMMARY_TILE_SX}>
        <Typography sx={SUMMARY_LABEL_SX}>Accounts</Typography>
        <Typography sx={SUMMARY_VALUE_SX}>{accountCount}</Typography>
        <Typography sx={SUMMARY_SUB_SX}>
          {cardCount} card{cardCount === 1 ? '' : 's'}
        </Typography>
      </Box>
    </Box>
  )
})

// ── Per-account health (reconciliation + coverage) ───────────────────────────

interface HealthRowProps {
  reconciliation?: BudgetReconciliationAccount
  unverifiable: boolean
  coverage?: BudgetCoverageAccount
}

const HealthRow = React.memo(function HealthRow({
  reconciliation, unverifiable, coverage,
}: HealthRowProps) {
  const coverageLine = useMemo(() => {
    if (!coverage) return null
    if (coverage.complete) {
      const n = coverage.months_covered.length
      return { ok: true, text: `✓ ${n} month${n === 1 ? '' : 's'}, no gaps` }
    }
    const shown = coverage.missing_months.slice(0, MISSING_MONTHS_SHOWN)
    const rest = coverage.missing_months.length - shown.length
    const suffix = rest > 0 ? ` +${rest} more` : ''
    return { ok: false, text: `⚠ Missing: ${shown.join(', ')}${suffix}` }
  }, [coverage])

  // Nothing known about this account from either endpoint - say nothing rather than
  // implying it passed a check that never ran.
  if (!reconciliation && !unverifiable && !coverageLine) return null

  return (
    <Box sx={HEALTH_ROW_SX}>
      {unverifiable ? (
        <Typography sx={HEALTH_NEUTRAL_SX}>No balance column — cannot verify</Typography>
      ) : reconciliation ? (
        reconciliation.status === 'reconciled' ? (
          <Typography sx={HEALTH_OK_SX}>✓ Balances reconciled</Typography>
        ) : (
          <Typography sx={HEALTH_WARN_SX}>
            ⚠ {reconciliation.break_count} unexplained break
            {reconciliation.break_count === 1 ? '' : 's'} ({money(reconciliation.unexplained_total)})
          </Typography>
        )
      ) : null}

      {coverageLine && (
        <Typography sx={coverageLine.ok ? HEALTH_OK_SX : HEALTH_WARN_SX}>
          {coverageLine.text}
        </Typography>
      )}
    </Box>
  )
})

// ── One account card ─────────────────────────────────────────────────────────

interface AccountCardProps {
  account: BudgetAccount
  missingLimit: boolean
  reconciliation?: BudgetReconciliationAccount
  unverifiable: boolean
  coverage?: BudgetCoverageAccount
  onEdit: (account: BudgetAccount) => void
}

const AccountCard = React.memo(function AccountCard({
  account, missingLimit, reconciliation, unverifiable, coverage, onEdit,
}: AccountCardProps) {
  const handleEdit = useCallback(() => onEdit(account), [onEdit, account])

  const range = dateRange(account.first_txn, account.last_txn)
  const status = account.utilisation_status
  const showUtilisation =
    account.is_card && account.credit_limit !== null && account.utilisation !== null && status !== null

  // Branch on is_card, never on truthiness of the figure: a card's `balance` is null
  // and a deposit's `outstanding` is null by contract.
  const headlineValue = account.is_card ? account.outstanding : account.balance

  return (
    <Box sx={CARD_SX}>
      <Box sx={CARD_HEAD_SX}>
        <Box>
          <Typography sx={CARD_LABEL_SX}>
            {account.is_card ? CARD_ICON : DEPOSIT_ICON} {account.label}
          </Typography>
          <Typography sx={CARD_META_SX}>
            {account.bank}
            {account.last4 ? ` · ••${account.last4}` : ''}
            {' · '}
            {account.txn_count.toLocaleString('en-IN')} txn
            {account.txn_count === 1 ? '' : 's'}
            {range ? ` · ${range}` : ''}
          </Typography>
        </Box>
        <Tooltip title="Edit account details">
          <Button size="small" sx={EDIT_BTN_SX} onClick={handleEdit}>
            <EditIcon fontSize="small" />
          </Button>
        </Tooltip>
      </Box>

      <Box>
        <Typography sx={HEADLINE_LABEL_SX}>
          {account.is_card ? 'Outstanding' : 'Balance'}
        </Typography>
        {headlineValue === null ? (
          <Tooltip title={NO_BALANCE_TOOLTIP}>
            <Typography component="span" sx={HEADLINE_MISSING_SX}>—</Typography>
          </Tooltip>
        ) : (
          <Typography sx={account.is_card ? HEADLINE_OUTSTANDING_SX : HEADLINE_BALANCE_SX}>
            {money(headlineValue)}
          </Typography>
        )}
      </Box>

      {account.is_card ? (
        <>
          {showUtilisation && (
            <Box>
              <LinearProgress
                variant="determinate"
                value={Math.min(100, Math.max(0, (account.utilisation as number) * 100))}
                sx={UTILISATION_BAR_SX[status as UtilisationStatus]}
              />
              <Typography sx={UTILISATION_TEXT_SX[status as UtilisationStatus]} mt={0.5}>
                {Math.round((account.utilisation as number) * 100)}% of{' '}
                {money(account.credit_limit as number)} used
              </Typography>
            </Box>
          )}

          {missingLimit && (
            <Button variant="outlined" size="small" sx={MISSING_LIMIT_SX} onClick={handleEdit}>
              Set a credit limit to track utilisation
            </Button>
          )}

          {(account.statement_day !== null || account.due_day !== null) && (
            <Box sx={SCHEDULE_ROW_SX}>
              {account.statement_day !== null && <span>Statement day {account.statement_day}</span>}
              {account.due_day !== null && <span>Due day {account.due_day}</span>}
            </Box>
          )}
        </>
      ) : (
        <Box sx={FLOW_ROW_SX}>
          <Typography sx={FLOW_IN_SX}>In {money(account.inflow)}</Typography>
          <Typography sx={FLOW_OUT_SX}>Out {money(account.outflow)}</Typography>
        </Box>
      )}

      <Divider sx={DIVIDER_SX} />
      <HealthRow
        reconciliation={reconciliation}
        unverifiable={unverifiable}
        coverage={coverage}
      />
    </Box>
  )
})

// ── Edit dialog ──────────────────────────────────────────────────────────────

interface FormState {
  label: string
  last4: string
  creditLimit: string
  statementDay: string
  dueDay: string
  openingBalance: string
}

type FormErrors = Partial<Record<keyof FormState, string>>

const toForm = (a: BudgetAccount): FormState => ({
  label: a.label ?? '',
  last4: a.last4 ?? '',
  creditLimit: a.credit_limit === null ? '' : String(a.credit_limit),
  statementDay: a.statement_day === null ? '' : String(a.statement_day),
  dueDay: a.due_day === null ? '' : String(a.due_day),
  openingBalance: a.opening_balance === null ? '' : String(a.opening_balance),
})

/** Blank means "clear this field"; anything unparseable is rejected before submit. */
function parseNumeric(raw: string): { ok: boolean; value: number | null } {
  const trimmed = raw.trim()
  if (!trimmed) return { ok: true, value: null }
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return { ok: false, value: null }
  return { ok: true, value: n }
}

function parseDay(raw: string): { ok: boolean; value: number | null } {
  const parsed = parseNumeric(raw)
  if (!parsed.ok) return parsed
  if (parsed.value === null) return parsed
  if (!Number.isInteger(parsed.value) || parsed.value < 1 || parsed.value > 31) {
    return { ok: false, value: null }
  }
  return parsed
}

function validate(form: FormState): FormErrors {
  const errors: FormErrors = {}

  if (!form.label.trim()) errors.label = 'A label is required.'

  const last4 = form.last4.trim()
  if (last4 && !/^\d{4}$/.test(last4)) errors.last4 = 'Exactly 4 digits, or leave blank.'

  const limit = parseNumeric(form.creditLimit)
  if (!limit.ok) errors.creditLimit = 'Enter a number, or leave blank.'
  else if (limit.value !== null && limit.value < 0) errors.creditLimit = 'Cannot be negative.'

  if (!parseDay(form.statementDay).ok) errors.statementDay = 'A day from 1 to 31, or blank.'
  if (!parseDay(form.dueDay).ok) errors.dueDay = 'A day from 1 to 31, or blank.'

  if (!parseNumeric(form.openingBalance).ok) errors.openingBalance = 'Enter a number, or leave blank.'

  return errors
}

/**
 * Only the fields the user actually touched.
 *
 * PUT /budget/accounts/{key} preserves omitted fields and clears explicit nulls, so
 * sending the whole form would turn "I did not fill in the credit limit" into "clear
 * the credit limit". Returns null when nothing changed.
 */
function buildPatch(account: BudgetAccount, form: FormState): BudgetAccountMetaUpdate | null {
  const patch: BudgetAccountMetaUpdate = {}

  const label = form.label.trim()
  if (label !== (account.label ?? '')) patch.label = label

  const last4 = form.last4.trim() || null
  if (last4 !== account.last4) patch.last4 = last4

  const limit = parseNumeric(form.creditLimit).value
  if (limit !== account.credit_limit) patch.credit_limit = limit

  const statementDay = parseDay(form.statementDay).value
  if (statementDay !== account.statement_day) patch.statement_day = statementDay

  const dueDay = parseDay(form.dueDay).value
  if (dueDay !== account.due_day) patch.due_day = dueDay

  const opening = parseNumeric(form.openingBalance).value
  if (opening !== account.opening_balance) patch.opening_balance = opening

  return Object.keys(patch).length ? patch : null
}

interface EditAccountDialogProps {
  account: BudgetAccount
  onClose: () => void
}

function EditAccountDialog({ account, onClose }: EditAccountDialogProps) {
  const [form, setForm] = useState<FormState>(() => toForm(account))
  const [errors, setErrors] = useState<FormErrors>({})
  const mutation = useUpdateBudgetAccount()

  const setField = useCallback((field: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const { value } = e.target
      setForm(prev => ({ ...prev, [field]: value }))
      setErrors(prev => (prev[field] ? { ...prev, [field]: undefined } : prev))
    }, [])

  const handleSave = useCallback(() => {
    const found = validate(form)
    if (Object.keys(found).length) {
      setErrors(found)
      return
    }
    const patch = buildPatch(account, form)
    if (!patch) {
      onClose()
      return
    }
    mutation.mutate({ accountKey: account.account_key, patch }, { onSuccess: onClose })
  }, [account, form, mutation, onClose])

  return (
    <Dialog open fullWidth maxWidth="sm" onClose={onClose} PaperProps={PAPER_PROPS}>
      <DialogTitle sx={DIALOG_TITLE_SX}>Edit {account.label}</DialogTitle>
      <DialogContent>
        <Typography sx={DIALOG_HINT_SX}>
          Statements do not carry credit limits or billing dates. Fill these in and the
          utilisation, due-date and net-worth figures start using them. Clearing a field
          removes the stored value.
        </Typography>

        <Box sx={DIALOG_FIELDS_SX}>
          <TextField
            label="Label"
            size="small"
            value={form.label}
            onChange={setField('label')}
            error={!!errors.label}
            helperText={errors.label}
            sx={FIELD_SX}
          />
          <TextField
            label="Last 4 digits"
            size="small"
            value={form.last4}
            onChange={setField('last4')}
            error={!!errors.last4}
            helperText={errors.last4}
            sx={FIELD_SX}
          />
          <TextField
            label="Credit limit (₹)"
            size="small"
            value={form.creditLimit}
            onChange={setField('creditLimit')}
            error={!!errors.creditLimit}
            helperText={errors.creditLimit}
            sx={FIELD_SX}
          />
          <TextField
            label="Opening balance (₹)"
            size="small"
            value={form.openingBalance}
            onChange={setField('openingBalance')}
            error={!!errors.openingBalance}
            helperText={errors.openingBalance}
            sx={FIELD_SX}
          />
          <TextField
            label="Statement day (1–31)"
            size="small"
            value={form.statementDay}
            onChange={setField('statementDay')}
            error={!!errors.statementDay}
            helperText={errors.statementDay}
            sx={FIELD_SX}
          />
          <TextField
            label="Due day (1–31)"
            size="small"
            value={form.dueDay}
            onChange={setField('dueDay')}
            error={!!errors.dueDay}
            helperText={errors.dueDay}
            sx={FIELD_SX}
          />
        </Box>

        {mutation.isError && (
          <Box sx={DIALOG_ERROR_SX}>
            {budgetErrorDetail(mutation.error, 'Could not save these account details.')}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={CANCEL_BTN_SX}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={mutation.isPending}
          sx={SAVE_BTN_SX}
        >
          {mutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// ── Loading skeleton ─────────────────────────────────────────────────────────

const SKELETON_KEYS = [0, 1, 2, 3]

function AccountsSkeleton() {
  return (
    <Box sx={ROOT_SX}>
      <Box sx={SUMMARY_STRIP_SX}>
        <Skeleton variant="rectangular" height={86} sx={SKELETON_SX} />
        <Skeleton variant="rectangular" height={86} sx={SKELETON_SX} />
        <Skeleton variant="rectangular" height={86} sx={SKELETON_SX} />
      </Box>
      <Box sx={GRID_SX}>
        {SKELETON_KEYS.map(k => (
          <Skeleton key={k} variant="rectangular" height={220} sx={SKELETON_CARD_SX} />
        ))}
      </Box>
    </Box>
  )
}

// ── Tab ──────────────────────────────────────────────────────────────────────

function AccountsTab({ sessionId }: AccountsTabProps) {
  const accountsQuery = useBudgetAccounts(sessionId)
  const reconciliationQuery = useBudgetReconciliation(sessionId)
  const coverageQuery = useBudgetCoverage(sessionId)

  const [editing, setEditing] = useState<BudgetAccount | null>(null)

  const closeEditor = useCallback(() => setEditing(null), [])

  const { refetch: refetchAccounts } = accountsQuery
  const { refetch: refetchReconciliation } = reconciliationQuery
  const { refetch: refetchCoverage } = coverageQuery

  const handleRetry = useCallback(() => {
    void refetchAccounts()
    void refetchReconciliation()
    void refetchCoverage()
  }, [refetchAccounts, refetchReconciliation, refetchCoverage])

  const data = accountsQuery.data
  const reconciliation = reconciliationQuery.data
  const coverage = coverageQuery.data

  const missingLimitKeys = useMemo(
    () => new Set(data?.cards_missing_limit ?? []),
    [data?.cards_missing_limit],
  )

  const reconciliationByKey = useMemo(() => {
    const map = new Map<string, BudgetReconciliationAccount>()
    for (const entry of reconciliation?.accounts ?? []) map.set(entry.account_key, entry)
    return map
  }, [reconciliation?.accounts])

  const unverifiableKeys = useMemo(
    () => new Set(reconciliation?.unverifiable_accounts ?? []),
    [reconciliation?.unverifiable_accounts],
  )

  const coverageByKey = useMemo(() => {
    const map = new Map<string, BudgetCoverageAccount>()
    for (const entry of coverage?.accounts ?? []) map.set(entry.account_key, entry)
    return map
  }, [coverage?.accounts])

  if (accountsQuery.isPending) return <AccountsSkeleton />

  if (accountsQuery.isError) {
    return (
      <Box sx={ERROR_PANEL_SX}>
        <Typography sx={ERROR_TITLE_SX}>Could not load your accounts</Typography>
        <Typography sx={ERROR_BODY_SX}>
          {budgetErrorDetail(accountsQuery.error, 'The accounts service did not respond.')}
        </Typography>
        <Button variant="outlined" color="error" onClick={handleRetry} sx={RETRY_BTN_SX}>
          Retry
        </Button>
      </Box>
    )
  }

  if (!data || data.accounts.length === 0) {
    return <Box sx={EMPTY_PANEL_SX}>Upload a statement to see your accounts.</Box>
  }

  const warnings = data.utilisation_warnings

  return (
    <Box sx={ROOT_SX}>
      {warnings.length > 0 && (
        <Box sx={WARNING_PANEL_SX}>
          <Typography sx={WARNING_TITLE_SX}>
            <WarningAmberIcon fontSize="small" />
            Card utilisation above 30% can lower your credit score.
          </Typography>
          <Typography sx={WARNING_BODY_SX}>
            {warnings.length === 1 ? 'This card is above the threshold:' : 'These cards are above the threshold:'}
          </Typography>
          <Stack spacing={0.25} mt={0.5}>
            {warnings.map(w => (
              <Typography key={w.account_key} sx={WARNING_ITEM_SX}>
                • {w.label} — {Math.round(w.utilisation * 100)}% ({w.status})
              </Typography>
            ))}
          </Stack>
        </Box>
      )}

      <SummaryStrip
        depositBalance={data.totals.deposit_balance}
        cardOutstanding={data.totals.card_outstanding}
        accountCount={data.totals.account_count}
        cardCount={data.totals.card_count}
      />

      {/* The API already sorts cards first - preserved as sent, not re-sorted here. */}
      <Box sx={GRID_SX}>
        {data.accounts.map(account => (
          <AccountCard
            key={account.account_key}
            account={account}
            missingLimit={missingLimitKeys.has(account.account_key)}
            reconciliation={reconciliationByKey.get(account.account_key)}
            unverifiable={unverifiableKeys.has(account.account_key)}
            coverage={coverageByKey.get(account.account_key)}
            onEdit={setEditing}
          />
        ))}
      </Box>

      {/*
        Mounted only while open, and keyed on the account: the form is seeded from the
        account in useState, so a shared instance would keep the previous card's values
        when the user opens a different one.
      */}
      {editing && (
        <EditAccountDialog
          key={editing.account_key}
          account={editing}
          onClose={closeEditor}
        />
      )}
    </Box>
  )
}

export default React.memo(AccountsTab)
