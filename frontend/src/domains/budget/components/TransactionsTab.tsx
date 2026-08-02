import React, { useState } from 'react'
import { 
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, 
  TableRow, Paper, Checkbox, Button, FormControl, Select, MenuItem, TextField,
  Chip, Stack, InputAdornment, Tooltip
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import SearchIcon from '@mui/icons-material/Search'
import { api } from '../../../shared/api/client'

interface TransactionsTabProps {
  transactions: any[]
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

export default function TransactionsTab({ transactions, uniqueBanks, onTransactionsUpdated }: TransactionsTabProps) {
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

  // Get unique account types across transactions
  const uniqueAccountTypes = Array.from(new Set(transactions.map(t => t.account_type || 'Savings Account').filter(Boolean)))

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedTxns(new Set(filteredTransactions.map(t => t.txn_id)))
    } else {
      setSelectedTxns(new Set())
    }
  }

  const handleSelectRow = (id: string) => {
    const next = new Set(selectedTxns)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedTxns(next)
  }

  const handleBulkUpdate = async () => {
    if (!bulkCategory || selectedTxns.size === 0) return
    setSaving(true)
    const updates = transactions
      .filter(t => selectedTxns.has(t.txn_id))
      .map(t => ({
        txn_id: t.txn_id,
        session_id: t.session_id,
        category: bulkCategory,
        notes: t.notes
      }))

    try {
      await api.put('/budget/transactions/update', updates)
      setSelectedTxns(new Set())
      setBulkCategory('')
      onTransactionsUpdated()
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const startEdit = (t: any) => {
    setEditingId(t.txn_id)
    setEditCategory(t.category)
    setEditNotes(t.notes || '')
  }

  const saveEdit = async (t: any) => {
    setSaving(true)
    try {
      await api.put('/budget/transactions/update', [{
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
  }

  const filteredTransactions = transactions.filter(t => {
    if (filterBank !== 'all' && (t.source_bank || '').toUpperCase() !== filterBank.toUpperCase()) return false
    if (filterType !== 'all' && t.type !== filterType) return false
    if (filterAccountType !== 'all' && (t.account_type || 'Savings Account').toLowerCase() !== filterAccountType.toLowerCase()) return false
    if (filterReview && t.category !== 'Uncategorized') return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const desc = (t.description || '').toLowerCase()
      const cat = (t.category || '').toLowerCase()
      const notes = (t.notes || '').toLowerCase()
      if (!desc.includes(q) && !cat.includes(q) && !notes.includes(q)) return false
    }
    return true
  })

  // Summary counts for filtered list
  const totalCredits = filteredTransactions.filter(t => t.type === 'credit').reduce((sum, t) => sum + (t.amount || 0), 0)
  const totalDebits = filteredTransactions.filter(t => t.type === 'debit').reduce((sum, t) => sum + (t.amount || 0), 0)

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
            sx={{
              minWidth: 200,
              backgroundColor: 'rgba(255,255,255,0.03)',
              borderRadius: 2,
              input: { color: '#fff', py: 0.8 },
              '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' }
            }}
          />

          {/* Debit vs Credit Flow Filter */}
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <Select 
              value={filterType} 
              onChange={e => setFilterType(e.target.value as string)} 
              sx={{ 
                color: '#fff', 
                backgroundColor: 'rgba(255,255,255,0.03)',
                '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' } 
              }}
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
              sx={{ 
                color: '#fff', 
                backgroundColor: 'rgba(255,255,255,0.03)',
                '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' } 
              }}
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
                sx={{ 
                  color: '#fff', 
                  backgroundColor: 'rgba(255,255,255,0.03)',
                  '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' } 
                }}
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
              sx={{ input: { color: '#fff', py: 0.5, fontSize: '0.85rem' }, minWidth: 140 }}
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
      <TableContainer component={Paper} sx={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 3, overflowX: 'auto' }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ background: '#0f172a', width: 40 }}>
                <Checkbox 
                  size="small" 
                  checked={filteredTransactions.length > 0 && selectedTxns.size === filteredTransactions.length}
                  indeterminate={selectedTxns.size > 0 && selectedTxns.size < filteredTransactions.length}
                  onChange={handleSelectAll}
                  sx={{ color: 'rgba(255,255,255,0.4)', '&.Mui-checked': { color: '#818cf8' } }}
                />
              </TableCell>
              <TableCell sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 100 }}>Date</TableCell>
              <TableCell sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 220 }}>Description</TableCell>
              <TableCell sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 150 }}>Account</TableCell>
              <TableCell sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 110 }}>Flow Type</TableCell>
              <TableCell sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 140 }}>Category</TableCell>
              <TableCell sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 140 }}>Notes</TableCell>
              <TableCell align="right" sx={{ color: '#cbd5e1', background: '#0f172a', fontWeight: 700, minWidth: 120 }}>Amount</TableCell>
              <TableCell sx={{ background: '#0f172a', width: 50 }}></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredTransactions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} sx={{ textAlign: 'center', py: 6, color: '#94a3b8' }}>
                  No transactions match the selected filters.
                </TableCell>
              </TableRow>
            ) : (
              filteredTransactions.map(t => {
                const bankUpper = (t.source_bank || 'GENERIC').toUpperCase()
                const bankStyle = BANK_COLOR_MAP[bankUpper] || BANK_COLOR_MAP['GENERIC']
                const accType = t.account_type || 'Savings Account'
                const isCreditCard = accType.toLowerCase().includes('card')
                const isCredit = t.type === 'credit'

                return (
                  <TableRow 
                    key={t.txn_id} 
                    sx={{ 
                      backgroundColor: selectedTxns.has(t.txn_id) ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                      '&:hover': { background: 'rgba(255,255,255,0.04)' },
                      transition: 'background-color 0.15s'
                    }}
                  >
                    <TableCell padding="checkbox">
                      <Checkbox 
                        size="small" 
                        checked={selectedTxns.has(t.txn_id)}
                        onChange={() => handleSelectRow(t.txn_id)}
                        sx={{ color: 'rgba(255,255,255,0.3)', '&.Mui-checked': { color: '#818cf8' } }}
                      />
                    </TableCell>
                    <TableCell sx={{ color: '#94a3b8', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '0.85rem' }}>
                      {t.date}
                    </TableCell>
                    <TableCell sx={{ color: '#f1f5f9', borderBottom: '1px solid rgba(255,255,255,0.05)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }} title={t.description}>
                      {t.description}
                    </TableCell>
                    <TableCell sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Chip
                          size="small"
                          label={bankUpper}
                          sx={{
                            height: 20,
                            fontSize: '0.65rem',
                            fontWeight: 700,
                            backgroundColor: bankStyle.bg,
                            color: bankStyle.text,
                            border: `1px solid ${bankStyle.border}`
                          }}
                        />
                        <Chip
                          size="small"
                          icon={isCreditCard ? <CreditCardIcon style={{ fontSize: 12, color: '#f472b6' }} /> : <AccountBalanceIcon style={{ fontSize: 12, color: '#94a3b8' }} />}
                          label={accType}
                          sx={{
                            height: 20,
                            fontSize: '0.65rem',
                            backgroundColor: 'rgba(255,255,255,0.03)',
                            color: '#94a3b8',
                            border: '1px solid rgba(255,255,255,0.06)'
                          }}
                        />
                      </Stack>
                    </TableCell>
                    
                    {/* Debit vs Credit Flow Column */}
                    <TableCell sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <Chip
                        size="small"
                        icon={isCredit ? <ArrowUpwardIcon style={{ fontSize: 12, color: '#34d399' }} /> : <ArrowDownwardIcon style={{ fontSize: 12, color: '#f87171' }} />}
                        label={isCredit ? 'Credit (Inflow)' : 'Debit (Outflow)'}
                        sx={{
                          height: 22,
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          backgroundColor: isCredit ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
                          color: isCredit ? '#34d399' : '#f87171',
                          border: `1px solid ${isCredit ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`
                        }}
                      />
                    </TableCell>
                    
                    <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      {editingId === t.txn_id ? (
                        <TextField 
                          size="small" 
                          value={editCategory} 
                          onChange={e => setEditCategory(e.target.value)} 
                          sx={{ input: { color: '#fff', py: 0.5, fontSize: '0.85rem' }, minWidth: 120 }} 
                        />
                      ) : (
                        <Chip 
                          size="small" 
                          label={t.category} 
                          sx={{ 
                            height: 22, 
                            fontSize: '0.75rem', 
                            backgroundColor: t.category === 'Uncategorized' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(255,255,255,0.05)',
                            color: t.category === 'Uncategorized' ? '#fbbf24' : '#cbd5e1',
                            border: `1px solid ${t.category === 'Uncategorized' ? 'rgba(245, 158, 11, 0.4)' : 'rgba(255,255,255,0.08)'}`
                          }} 
                        />
                      )}
                    </TableCell>
                    
                    <TableCell sx={{ color: '#94a3b8', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '0.8rem' }}>
                      {editingId === t.txn_id ? (
                        <TextField 
                          size="small" 
                          value={editNotes} 
                          onChange={e => setEditNotes(e.target.value)} 
                          placeholder="Add note..."
                          sx={{ input: { color: '#fff', py: 0.5, fontSize: '0.85rem' }, minWidth: 120 }} 
                        />
                      ) : (t.notes || <span style={{ opacity: 0.3 }}>-</span>)}
                    </TableCell>
                    
                    <TableCell align="right" sx={{ color: isCredit ? '#34d399' : '#f87171', borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 700, fontSize: '0.9rem' }}>
                      {isCredit ? '+' : '-'}₹{t.amount?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </TableCell>
                    
                    <TableCell sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      {editingId === t.txn_id ? (
                        <Stack direction="row" spacing={0.5}>
                          <Button size="small" variant="contained" onClick={() => saveEdit(t)} disabled={saving} sx={{ minWidth: 44, fontSize: '0.7rem', px: 1 }}>Save</Button>
                          <Button size="small" onClick={() => setEditingId(null)} sx={{ minWidth: 44, fontSize: '0.7rem', color: '#94a3b8', px: 1 }}>Cancel</Button>
                        </Stack>
                      ) : (
                        <Tooltip title="Edit Category & Notes">
                          <Button size="small" sx={{ minWidth: 'auto', p: 0.5 }} onClick={() => startEdit(t)}>
                            <EditIcon fontSize="small" sx={{ color: '#64748b', '&:hover': { color: '#818cf8' } }} />
                          </Button>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}
