import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper, Checkbox, Button, FormControl, Select, MenuItem, TextField,
  Chip, Stack, InputAdornment, Tooltip, TablePagination
} from '@mui/material'
import type { SxProps } from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import SearchIcon from '@mui/icons-material/Search'
import { apiClient } from '../../../shared/api/client'
import type { BudgetTransaction } from '../types'

interface TransactionsTabProps {
  transactions: BudgetTransaction[]
  uniqueBanks: string[]
  onTransactionsUpdated: () => void
}

const BANK_COLOR_MAP: Record<string, { bg: string, border: string, text: string }> = {
  HDFC: { bg: 'rgba(0, 75, 141, 0.15)', border: 'rgba(0, 75, 141, 0.4)', text: '#60a5fa' },
  ICICI: { bg: 'rgba(179, 39, 44, 0.15)', border: 'rgba(179, 39, 44, 0.4)', text: '#f87171' },
  SBI: { bg: 'rgba(40, 56, 144, 0.15)', border: 'rgba(40, 56, 144, 0.4)', text: '#38bdf8' },
  AXIS: { bg: 'rgba(151, 18, 74, 0.15)', border: 'rgba(151, 18, 74, 0.4)', text: '#f472b6' },
  KOTAK: { bg: 'rgba(237, 28, 36, 0.15)', border: 'rgba(237, 28, 36, 0.4)', text: '#fb7185' },
  GENERIC: { bg: 'rgba(100, 116, 139, 0.15)', border: 'rgba(100, 116, 139, 0.4)', text: '#94a3b8' },
}

/**
 * Every `sx` below was an inline object literal inside the row map.
 *
 * An object literal has a new identity on every render, so emotion re-serialises it
 * each time - here that was nine cells' worth per row, for every row in the table.
 * Hoisting to module constants makes the identity stable; the two-state ones are
 * precomputed pairs rather than ternaries over fresh literals.
 */
const ROWS_PER_PAGE_OPTIONS = [25, 50, 100, 250]

const CELL_BORDER = '1px solid rgba(255,255,255,0.05)'

const HEADER_CELL: SxProps = { color: '#cbd5e1', background: '#0f172a', fontWeight: 700 }
const HEADER_CELL_DATE: SxProps = { ...HEADER_CELL, minWidth: 100 }
const HEADER_CELL_DESC: SxProps = { ...HEADER_CELL, minWidth: 220 }
const HEADER_CELL_ACCOUNT: SxProps = { ...HEADER_CELL, minWidth: 150 }
const HEADER_CELL_FLOW: SxProps = { ...HEADER_CELL, minWidth: 110 }
const HEADER_CELL_CATEGORY: SxProps = { ...HEADER_CELL, minWidth: 140 }
const HEADER_CELL_NOTES: SxProps = { ...HEADER_CELL, minWidth: 140 }
const HEADER_CELL_AMOUNT: SxProps = { ...HEADER_CELL, minWidth: 120 }
const HEADER_CELL_CHECKBOX: SxProps = { background: '#0f172a', width: 40 }
const HEADER_CELL_ACTIONS: SxProps = { background: '#0f172a', width: 50 }

const ROW_SX: SxProps = {
  backgroundColor: 'transparent',
  '&:hover': { background: 'rgba(255,255,255,0.04)' },
  transition: 'background-color 0.15s',
}
const ROW_SELECTED_SX: SxProps = { ...ROW_SX, backgroundColor: 'rgba(99, 102, 241, 0.08)' }

const CHECKBOX_SX: SxProps = { color: 'rgba(255,255,255,0.3)', '&.Mui-checked': { color: '#818cf8' } }
const HEADER_CHECKBOX_SX: SxProps = { color: 'rgba(255,255,255,0.4)', '&.Mui-checked': { color: '#818cf8' } }

const DATE_CELL: SxProps = { color: '#94a3b8', borderBottom: CELL_BORDER, fontSize: '0.85rem' }
const DESC_CELL: SxProps = {
  color: '#f1f5f9', borderBottom: CELL_BORDER, maxWidth: 260,
  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500,
}
const PLAIN_CELL: SxProps = { borderBottom: CELL_BORDER }
const CATEGORY_CELL: SxProps = { color: '#cbd5e1', borderBottom: CELL_BORDER }
const NOTES_CELL: SxProps = { color: '#94a3b8', borderBottom: CELL_BORDER, fontSize: '0.8rem' }
const AMOUNT_CELL_CREDIT: SxProps = {
  color: '#34d399', borderBottom: CELL_BORDER, fontWeight: 700, fontSize: '0.9rem',
}
const AMOUNT_CELL_DEBIT: SxProps = { ...AMOUNT_CELL_CREDIT, color: '#f87171' }

const BANK_CHIP_SX: Record<string, SxProps> = Object.fromEntries(
  Object.entries(BANK_COLOR_MAP).map(([bank, style]) => [bank, {
    height: 20,
    fontSize: '0.65rem',
    fontWeight: 700,
    backgroundColor: style.bg,
    color: style.text,
    border: `1px solid ${style.border}`,
  }]),
)

const ACCOUNT_CHIP_SX: SxProps = {
  height: 20,
  fontSize: '0.65rem',
  backgroundColor: 'rgba(255,255,255,0.03)',
  color: '#94a3b8',
  border: '1px solid rgba(255,255,255,0.06)',
}

const FLOW_CHIP_CREDIT_SX: SxProps = {
  height: 22,
  fontSize: '0.7rem',
  fontWeight: 700,
  backgroundColor: 'rgba(16, 185, 129, 0.12)',
  color: '#34d399',
  border: '1px solid rgba(16, 185, 129, 0.3)',
}
const FLOW_CHIP_DEBIT_SX: SxProps = {
  ...FLOW_CHIP_CREDIT_SX,
  backgroundColor: 'rgba(239, 68, 68, 0.12)',
  color: '#f87171',
  border: '1px solid rgba(239, 68, 68, 0.3)',
}

const CATEGORY_CHIP_SX: SxProps = {
  height: 22,
  fontSize: '0.75rem',
  backgroundColor: 'rgba(255,255,255,0.05)',
  color: '#cbd5e1',
  border: '1px solid rgba(255,255,255,0.08)',
}
const CATEGORY_CHIP_UNCATEGORIZED_SX: SxProps = {
  ...CATEGORY_CHIP_SX,
  backgroundColor: 'rgba(245, 158, 11, 0.15)',
  color: '#fbbf24',
  border: '1px solid rgba(245, 158, 11, 0.4)',
}

const EDIT_FIELD_SX: SxProps = { input: { color: '#fff', py: 0.5, fontSize: '0.85rem' }, minWidth: 120 }
const SAVE_BTN_SX: SxProps = { minWidth: 44, fontSize: '0.7rem', px: 1 }
const CANCEL_BTN_SX: SxProps = { minWidth: 44, fontSize: '0.7rem', color: '#94a3b8', px: 1 }
const EDIT_BTN_SX: SxProps = { minWidth: 'auto', p: 0.5 }
const EDIT_ICON_SX: SxProps = { color: '#64748b', '&:hover': { color: '#818cf8' } }

const SELECT_SX: SxProps = {
  color: '#fff',
  backgroundColor: 'rgba(255,255,255,0.03)',
  '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
}
const SEARCH_FIELD_SX: SxProps = {
  minWidth: 200,
  backgroundColor: 'rgba(255,255,255,0.03)',
  borderRadius: 2,
  input: { color: '#fff', py: 0.8 },
  '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
}
const TABLE_PAPER_SX: SxProps = {
  background: 'rgba(255,255,255,0.02)',
  border: '1px solid rgba(255,255,255,0.07)',
  borderRadius: 3,
  overflowX: 'auto',
}
const PAGINATION_SX: SxProps = {
  color: '#94a3b8',
  borderTop: '1px solid rgba(255,255,255,0.07)',
  '.MuiTablePagination-selectIcon': { color: '#94a3b8' },
}

const CREDIT_CARD_ICON = <CreditCardIcon style={{ fontSize: 12, color: '#f472b6' }} />
const BANK_ICON = <AccountBalanceIcon style={{ fontSize: 12, color: '#94a3b8' }} />
const INFLOW_ICON = <ArrowUpwardIcon style={{ fontSize: 12, color: '#34d399' }} />
const OUTFLOW_ICON = <ArrowDownwardIcon style={{ fontSize: 12, color: '#f87171' }} />

interface TransactionRowProps {
  txn: BudgetTransaction
  selected: boolean
  editing: boolean
  /** Only passed for the row being edited, so a keystroke re-renders one row. */
  editCategory?: string
  editNotes?: string
  saving: boolean
  onToggleSelect: (id: string) => void
  onStartEdit: (txn: BudgetTransaction) => void
  onCancelEdit: () => void
  onSaveEdit: (txn: BudgetTransaction) => void
  onChangeCategory: (value: string) => void
  onChangeNotes: (value: string) => void
}

/**
 * One transaction row.
 *
 * Extracted and memoised because the edit fields are controlled by state that has to
 * live above the rows: with everything in one component, each keystroke in an inline
 * category field re-rendered every row in the table.
 */
const TransactionRow = React.memo(function TransactionRow({
  txn, selected, editing, editCategory, editNotes, saving,
  onToggleSelect, onStartEdit, onCancelEdit, onSaveEdit, onChangeCategory, onChangeNotes,
}: TransactionRowProps) {
  const bankUpper = (txn.source_bank || 'GENERIC').toUpperCase()
  const bankChipSx = BANK_CHIP_SX[bankUpper] || BANK_CHIP_SX['GENERIC']
  const accType = txn.account_type || 'Savings Account'
  const isCreditCard = accType.toLowerCase().includes('card')
  const isCredit = txn.type === 'credit'
  const isUncategorized = txn.category === 'Uncategorized'

  return (
    <TableRow sx={selected ? ROW_SELECTED_SX : ROW_SX}>
      <TableCell padding="checkbox">
        <Checkbox
          size="small"
          checked={selected}
          onChange={() => onToggleSelect(txn.txn_id)}
          sx={CHECKBOX_SX}
        />
      </TableCell>
      <TableCell sx={DATE_CELL}>
        {txn.date}
      </TableCell>
      <TableCell sx={DESC_CELL} title={txn.description}>
        {txn.description}
      </TableCell>
      <TableCell sx={PLAIN_CELL}>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Chip size="small" label={bankUpper} sx={bankChipSx} />
          <Chip
            size="small"
            icon={isCreditCard ? CREDIT_CARD_ICON : BANK_ICON}
            label={accType}
            sx={ACCOUNT_CHIP_SX}
          />
        </Stack>
      </TableCell>

      {/* Debit vs Credit Flow Column */}
      <TableCell sx={PLAIN_CELL}>
        <Chip
          size="small"
          icon={isCredit ? INFLOW_ICON : OUTFLOW_ICON}
          label={isCredit ? 'Credit (Inflow)' : 'Debit (Outflow)'}
          sx={isCredit ? FLOW_CHIP_CREDIT_SX : FLOW_CHIP_DEBIT_SX}
        />
      </TableCell>

      <TableCell sx={CATEGORY_CELL}>
        {editing ? (
          <TextField
            size="small"
            value={editCategory ?? ''}
            onChange={e => onChangeCategory(e.target.value)}
            sx={EDIT_FIELD_SX}
          />
        ) : (
          <Chip
            size="small"
            label={txn.category}
            sx={isUncategorized ? CATEGORY_CHIP_UNCATEGORIZED_SX : CATEGORY_CHIP_SX}
          />
        )}
      </TableCell>

      <TableCell sx={NOTES_CELL}>
        {editing ? (
          <TextField
            size="small"
            value={editNotes ?? ''}
            onChange={e => onChangeNotes(e.target.value)}
            placeholder="Add note..."
            sx={EDIT_FIELD_SX}
          />
        ) : (txn.notes || <span style={{ opacity: 0.3 }}>-</span>)}
      </TableCell>

      <TableCell align="right" sx={isCredit ? AMOUNT_CELL_CREDIT : AMOUNT_CELL_DEBIT}>
        {isCredit ? '+' : '-'}₹{txn.amount?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </TableCell>

      <TableCell sx={PLAIN_CELL}>
        {editing ? (
          <Stack direction="row" spacing={0.5}>
            <Button size="small" variant="contained" onClick={() => onSaveEdit(txn)} disabled={saving} sx={SAVE_BTN_SX}>Save</Button>
            <Button size="small" onClick={onCancelEdit} sx={CANCEL_BTN_SX}>Cancel</Button>
          </Stack>
        ) : (
          <Tooltip title="Edit Category & Notes">
            <Button size="small" sx={EDIT_BTN_SX} onClick={() => onStartEdit(txn)}>
              <EditIcon fontSize="small" sx={EDIT_ICON_SX} />
            </Button>
          </Tooltip>
        )}
      </TableCell>
    </TableRow>
  )
})

function TransactionsTab({ transactions, uniqueBanks, onTransactionsUpdated }: TransactionsTabProps) {
  const [selectedTxns, setSelectedTxns] = useState<Set<string>>(new Set())
  const [bulkCategory, setBulkCategory] = useState<string>('')
  const [saving, setSaving] = useState(false)

  // Filtering states
  const [filterBank, setFilterBank] = useState<string>('all')
  const [filterType, setFilterType] = useState<string>('all') // 'all', 'debit', 'credit'
  const [filterAccountType, setFilterAccountType] = useState<string>('all')
  const [filterReview, setFilterReview] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Inline editing state
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editCategory, setEditCategory] = useState('')
  const [editNotes, setEditNotes] = useState('')

  // Paging. The table has no virtualization, and for sessionId === 'overall' the list
  // is every transaction across every uploaded statement.
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)

  // Get unique account types across transactions
  const uniqueAccountTypes = useMemo(
    () => Array.from(new Set(transactions.map(t => t.account_type || 'Savings Account').filter(Boolean))),
    [transactions],
  )

  const filteredTransactions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return transactions.filter(t => {
      if (filterBank !== 'all' && (t.source_bank || '').toUpperCase() !== filterBank.toUpperCase()) return false
      if (filterType !== 'all' && t.type !== filterType) return false
      if (filterAccountType !== 'all' && (t.account_type || 'Savings Account').toLowerCase() !== filterAccountType.toLowerCase()) return false
      if (filterReview && t.category !== 'Uncategorized') return false
      if (q) {
        const desc = (t.description || '').toLowerCase()
        const cat = (t.category || '').toLowerCase()
        const notes = (t.notes || '').toLowerCase()
        if (!desc.includes(q) && !cat.includes(q) && !notes.includes(q)) return false
      }
      return true
    })
  }, [transactions, filterBank, filterType, filterAccountType, filterReview, searchQuery])

  /**
   * Drop the selection whenever the visible set changes.
   *
   * The Set used to survive filter changes, so the header checkbox could read "all
   * selected" while nothing on screen was checked - and Apply then re-categorized the
   * off-screen rows that were still in the Set. That was silent data corruption, not
   * just a confusing checkbox.
   */
  useEffect(() => {
    setSelectedTxns(new Set())
  }, [filteredTransactions])

  // Keep the page in range when the list shrinks, but do not reset it on every
  // refetch - an inline edit refreshes the data and would otherwise throw the user
  // back to page 1.
  useEffect(() => {
    setPage(prev => (prev * rowsPerPage >= filteredTransactions.length ? 0 : prev))
  }, [filteredTransactions.length, rowsPerPage])

  // Summary counts for filtered list
  const { totalCredits, totalDebits } = useMemo(() => {
    let credits = 0
    let debits = 0
    for (const t of filteredTransactions) {
      if (t.type === 'credit') credits += t.amount || 0
      else if (t.type === 'debit') debits += t.amount || 0
    }
    return { totalCredits: credits, totalDebits: debits }
  }, [filteredTransactions])

  const visibleTransactions = useMemo(
    () => filteredTransactions.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage),
    [filteredTransactions, page, rowsPerPage],
  )

  const handleSelectAll = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedTxns(new Set(filteredTransactions.map(t => t.txn_id)))
    } else {
      setSelectedTxns(new Set())
    }
  }, [filteredTransactions])

  const handleSelectRow = useCallback((id: string) => {
    setSelectedTxns(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleBulkUpdate = useCallback(async () => {
    if (!bulkCategory || selectedTxns.size === 0) return
    setSaving(true)
    // Scoped to the filtered list: the selection can only ever contain rows the user
    // could actually see when they ticked them.
    const updates = filteredTransactions
      .filter(t => selectedTxns.has(t.txn_id))
      .map(t => ({
        txn_id: t.txn_id,
        session_id: t.session_id,
        category: bulkCategory,
        notes: t.notes
      }))

    try {
      await apiClient.updateBudgetTransactions(updates)
      setSelectedTxns(new Set())
      setBulkCategory('')
      onTransactionsUpdated()
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }, [bulkCategory, selectedTxns, filteredTransactions, onTransactionsUpdated])

  const startEdit = useCallback((t: BudgetTransaction) => {
    setEditingId(t.txn_id)
    setEditCategory(t.category || '')
    setEditNotes(t.notes || '')
  }, [])

  const cancelEdit = useCallback(() => setEditingId(null), [])

  const saveEdit = useCallback(async (t: BudgetTransaction) => {
    setSaving(true)
    try {
      await apiClient.updateBudgetTransactions([{
        txn_id: t.txn_id,
        session_id: t.session_id,
        category: editCategory,
        notes: editNotes
      }])
      setEditingId(null)
      onTransactionsUpdated()
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }, [editCategory, editNotes, onTransactionsUpdated])

  const handleChangePage = useCallback((_: unknown, next: number) => setPage(next), [])

  const handleChangeRowsPerPage = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(e.target.value, 10))
    setPage(0)
  }, [])

  return (
    <Box>
      {/* Filter Controls Row */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3, flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center">
          {/* Search Field */}
          <TextField
            size="small"
            placeholder="Search description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: '#94a3b8', fontSize: 20 }} />
                </InputAdornment>
              )
            }}
            sx={SEARCH_FIELD_SX}
          />

          {/* Debit vs Credit Flow Filter */}
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <Select
              value={filterType}
              onChange={e => setFilterType(e.target.value as string)}
              sx={SELECT_SX}
            >
              <MenuItem value="all">All Flow Types</MenuItem>
              <MenuItem value="debit">🔴 Debits Only</MenuItem>
              <MenuItem value="credit">🟢 Credits Only</MenuItem>
            </Select>
          </FormControl>

          {/* Bank Filter */}
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <Select
              value={filterBank}
              onChange={e => setFilterBank(e.target.value as string)}
              sx={SELECT_SX}
            >
              <MenuItem value="all">All Banks</MenuItem>
              {uniqueBanks.map(b => <MenuItem key={b} value={b}>{b}</MenuItem>)}
            </Select>
          </FormControl>

          {/* Account Type Filter */}
          {uniqueAccountTypes.length > 0 && (
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <Select
                value={filterAccountType}
                onChange={e => setFilterAccountType(e.target.value as string)}
                sx={SELECT_SX}
              >
                <MenuItem value="all">All Account Types</MenuItem>
                {uniqueAccountTypes.map(at => <MenuItem key={at} value={at}>{at}</MenuItem>)}
              </Select>
            </FormControl>
          )}

          {/* Review Filter */}
          <Button
            variant={filterReview ? "contained" : "outlined"}
            color="warning"
            size="small"
            onClick={() => setFilterReview(!filterReview)}
            sx={{ textTransform: 'none', fontWeight: 600, height: 38 }}
          >
            Needs Review
          </Button>
        </Stack>

        {/* Bulk Update Controls */}
        {selectedTxns.size > 0 && (
          <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', background: 'rgba(99, 102, 241, 0.15)', border: '1px solid rgba(99, 102, 241, 0.4)', p: 1, px: 2, borderRadius: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: '#a5b4fc' }}>{selectedTxns.size} selected</Typography>
            <TextField
              size="small"
              placeholder="Assign Category"
              value={bulkCategory}
              onChange={e => setBulkCategory(e.target.value)}
              sx={EDIT_FIELD_SX}
            />
            <Button
              variant="contained"
              size="small"
              onClick={handleBulkUpdate}
              disabled={saving || !bulkCategory}
              sx={{ textTransform: 'none', fontWeight: 600, background: '#6366f1' }}
            >
              Apply
            </Button>
          </Box>
        )}
      </Box>

      {/* Quick Summary Pill Bar */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2, alignItems: 'center', flexWrap: 'wrap', color: '#94a3b8', fontSize: '0.85rem' }}>
        <span>Showing <strong>{filteredTransactions.length}</strong> transactions</span>
        <span>•</span>
        <span style={{ color: '#34d399' }}>Total Inflow (Credits): <strong>+₹{totalCredits.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</strong></span>
        <span>•</span>
        <span style={{ color: '#f87171' }}>Total Outflow (Debits): <strong>-₹{totalDebits.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</strong></span>
      </Box>

      {/* Transactions Table */}
      <TableContainer component={Paper} sx={TABLE_PAPER_SX}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={HEADER_CELL_CHECKBOX}>
                <Checkbox
                  size="small"
                  checked={filteredTransactions.length > 0 && selectedTxns.size === filteredTransactions.length}
                  indeterminate={selectedTxns.size > 0 && selectedTxns.size < filteredTransactions.length}
                  onChange={handleSelectAll}
                  sx={HEADER_CHECKBOX_SX}
                />
              </TableCell>
              <TableCell sx={HEADER_CELL_DATE}>Date</TableCell>
              <TableCell sx={HEADER_CELL_DESC}>Description</TableCell>
              <TableCell sx={HEADER_CELL_ACCOUNT}>Account</TableCell>
              <TableCell sx={HEADER_CELL_FLOW}>Flow Type</TableCell>
              <TableCell sx={HEADER_CELL_CATEGORY}>Category</TableCell>
              <TableCell sx={HEADER_CELL_NOTES}>Notes</TableCell>
              <TableCell align="right" sx={HEADER_CELL_AMOUNT}>Amount</TableCell>
              <TableCell sx={HEADER_CELL_ACTIONS}></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleTransactions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} sx={{ textAlign: 'center', py: 6, color: '#94a3b8' }}>
                  No transactions match the selected filters.
                </TableCell>
              </TableRow>
            ) : (
              visibleTransactions.map(t => (
                <TransactionRow
                  key={t.txn_id}
                  txn={t}
                  selected={selectedTxns.has(t.txn_id)}
                  editing={editingId === t.txn_id}
                  editCategory={editingId === t.txn_id ? editCategory : undefined}
                  editNotes={editingId === t.txn_id ? editNotes : undefined}
                  saving={saving}
                  onToggleSelect={handleSelectRow}
                  onStartEdit={startEdit}
                  onCancelEdit={cancelEdit}
                  onSaveEdit={saveEdit}
                  onChangeCategory={setEditCategory}
                  onChangeNotes={setEditNotes}
                />
              ))
            )}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={filteredTransactions.length}
          page={page}
          onPageChange={handleChangePage}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          rowsPerPageOptions={ROWS_PER_PAGE_OPTIONS}
          sx={PAGINATION_SX}
        />
      </TableContainer>
    </Box>
  )
}

export default React.memo(TransactionsTab)
