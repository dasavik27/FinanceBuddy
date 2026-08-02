import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Box, Typography, Card, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Button, TextField, IconButton, FormControl, Select, MenuItem, InputLabel } from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import { apiClient } from '../../../shared/api/client'
import { useDebounce } from '../../../shared/hooks/useDebounce'
import { budgetErrorDetail } from '../hooks/useBudget'
import type { BudgetRule } from '../types'

interface RulesTabProps {
  onRulesApplied?: () => Promise<void> | void
}

/** Readable labels for the match types the server reports; unknown ones title-case. */
const MATCH_TYPE_LABELS: Record<string, string> = {
  contains: 'Text Contains',
  exact: 'Exact Match',
  starts_with: 'Starts With',
  ends_with: 'Ends With',
  regex: 'Regex',
}

function matchTypeLabel(value: string): string {
  return MATCH_TYPE_LABELS[value] || value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function RulesTab({ onRulesApplied }: RulesTabProps) {
  const qc = useQueryClient()

  const [newPattern, setNewPattern] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [newMatchType, setNewMatchType] = useState('contains')
  const [createError, setCreateError] = useState<string | null>(null)

  // Sandbox state
  const [testDescription, setTestDescription] = useState('')

  const { data: rules = [] } = useQuery({
    queryKey: ['budget', 'rules'],
    queryFn: () => apiClient.getBudgetRules(),
  })

  /**
   * The match types the server accepts.
   *
   * Hardcoding three of them here meant the dropdown silently omitted the two the
   * backend also supports. Static per deployment, so it never goes stale.
   */
  const { data: matchTypeInfo } = useQuery({
    queryKey: ['budget', 'match-types'],
    queryFn: () => apiClient.getBudgetMatchTypes(),
    staleTime: Infinity,
  })

  const matchTypes = matchTypeInfo?.match_types ?? ['contains']
  const maxPatternLength = matchTypeInfo?.max_pattern_length
  const maxRules = matchTypeInfo?.max_rules

  const createRule = useMutation({
    mutationFn: () => apiClient.createBudgetRule({
      pattern: newPattern,
      category: newCategory,
      match_type: newMatchType,
    }),
    onSuccess: () => {
      setNewPattern('')
      setNewCategory('')
      setCreateError(null)
      qc.invalidateQueries({ queryKey: ['budget', 'rules'] })
    },
    // The server rejects unsafe or over-quota patterns with 422 and an explanation.
    // Swallowing it into console.error left the Add button looking like it had worked.
    onError: (e) => setCreateError(budgetErrorDetail(e, 'Could not save this rule.')),
  })

  const deleteRule = useMutation({
    mutationFn: (ruleId: string) => apiClient.deleteBudgetRule(ruleId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget', 'rules'] }),
  })

  const applyAll = useMutation({
    mutationFn: () => apiClient.applyBudgetRules(),
    onSuccess: async () => {
      // Re-categorization rewrites transactions, so the analytics are stale too.
      qc.invalidateQueries({ queryKey: ['budget'] })
      if (onRulesApplied) await onRulesApplied()
    },
  })

  /**
   * Sandbox: does the rule being drafted catch this description?
   *
   * Evaluated by POST /budget/rules/test rather than in the browser. The old version
   * ran `new RegExp(pattern, 'i')` over every saved rule on every keystroke, so one
   * stored `(a+)+$` froze the tab - the catastrophic-backtracking hazard is exactly
   * why the check belongs on the server, which validates the shape before compiling.
   */
  const debouncedDescription = useDebounce(testDescription, 300)
  const debouncedPattern = useDebounce(newPattern, 300)

  const { data: testResult } = useQuery({
    queryKey: ['budget', 'rule-test', debouncedPattern, newMatchType, debouncedDescription],
    queryFn: () => apiClient.testBudgetRule(
      { pattern: debouncedPattern, category: newCategory || 'Preview', match_type: newMatchType },
      debouncedDescription,
    ),
    enabled: debouncedPattern.trim().length > 0 && debouncedDescription.trim().length > 0,
    staleTime: Infinity,
  })

  const applyMessage = applyAll.isSuccess
    ? `Successfully re-categorized ${applyAll.data?.transactions_recalculated ?? 0} transactions!`
    : applyAll.isError
      ? budgetErrorDetail(applyAll.error, 'Failed to apply rules.')
      : null

  return (
    <Box sx={{ color: '#fff' }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, mb: 4 }}>
        <Card sx={{ flex: 1, minWidth: 300, p: 3, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Create Automation Rule</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <FormControl size="small" fullWidth>
              <InputLabel sx={{ color: 'text.secondary' }}>Match Type</InputLabel>
              <Select value={newMatchType} label="Match Type" onChange={e => setNewMatchType(e.target.value)} sx={{ color: '#fff' }}>
                {matchTypes.map(mt => (
                  <MenuItem key={mt} value={mt}>{matchTypeLabel(mt)}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              size="small"
              label="Pattern (e.g. Uber, Zomato)"
              value={newPattern}
              onChange={e => { setNewPattern(e.target.value); setCreateError(null) }}
              inputProps={maxPatternLength ? { maxLength: maxPatternLength } : undefined}
              InputLabelProps={{ sx: { color: 'text.secondary' } }}
              sx={{ input: { color: '#fff' } }}
            />
            <TextField
              size="small"
              label="Assign Category (e.g. Transport, Dining)"
              value={newCategory}
              onChange={e => { setNewCategory(e.target.value); setCreateError(null) }}
              InputLabelProps={{ sx: { color: 'text.secondary' } }}
              sx={{ input: { color: '#fff' } }}
            />
            {createError && (
              <Typography variant="body2" sx={{ color: '#f87171', fontWeight: 500 }}>
                {createError}
              </Typography>
            )}
            <Button variant="contained" onClick={() => createRule.mutate()} disabled={!newPattern || !newCategory || createRule.isPending}>
              {createRule.isPending ? 'Saving...' : 'Add Rule'}
            </Button>
            {maxRules != null && (
              <Typography variant="caption" color="text.secondary">
                {rules.length} of {maxRules} rules used.
              </Typography>
            )}
          </Box>
        </Card>

        <Card sx={{ flex: 1, minWidth: 300, p: 3, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Testing Sandbox</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Type a sample bank transaction description here to see whether the rule you are drafting will catch it.
          </Typography>
          <TextField
            fullWidth
            size="small"
            label="Sample Transaction Description"
            value={testDescription}
            onChange={e => setTestDescription(e.target.value)}
            InputLabelProps={{ sx: { color: 'text.secondary' } }}
            sx={{ input: { color: '#fff' }, mb: 2 }}
          />
          {testDescription && (
            !newPattern.trim() ? (
              <Box sx={{ p: 2, borderRadius: 2, background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
                <Typography variant="body2" color="text.secondary">Enter a pattern on the left to test it against this description.</Typography>
              </Box>
            ) : (
              <Box sx={{ p: 2, borderRadius: 2, background: testResult?.matches ? 'rgba(74, 222, 128, 0.1)' : 'rgba(255, 255, 255, 0.05)', border: testResult?.matches ? '1px solid rgba(74, 222, 128, 0.3)' : '1px solid rgba(255,255,255,0.1)' }}>
                {testResult?.valid === false ? (
                  <Typography variant="body2" sx={{ color: '#f87171', fontWeight: 600 }}>{testResult.error}</Typography>
                ) : testResult?.matches ? (
                  <>
                    <Typography variant="body2" sx={{ color: '#4ade80', fontWeight: 600 }}>Rule Matched!</Typography>
                    <Typography variant="body2" sx={{ mt: 1 }}>It will be categorized as: <strong>{newCategory || 'Uncategorized'}</strong></Typography>
                    <Typography variant="caption" color="text.secondary">Matched by rule: "{debouncedPattern}" ({matchTypeLabel(newMatchType)})</Typography>
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary">This rule does not match. It will remain Uncategorized.</Typography>
                )}
              </Box>
            )
          )}
        </Card>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 2 }}>
        <Typography variant="h6">Active Rules</Typography>
        <Button
          variant="outlined"
          color="primary"
          disabled={applyAll.isPending || rules.length === 0}
          onClick={() => applyAll.mutate()}
          sx={{ textTransform: 'none' }}
        >
          {applyAll.isPending ? 'Applying Rules...' : '⚡ Re-apply Rules to All Past Transactions'}
        </Button>
      </Box>

      {applyMessage && (
        <Typography variant="body2" sx={{ mb: 2, color: applyAll.isSuccess ? '#4ade80' : '#f87171', fontWeight: 500 }}>
          {applyMessage}
        </Typography>
      )}

      <TableContainer component={Paper} sx={{ background: 'rgba(255,255,255,0.03)', borderRadius: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ color: '#fff', background: '#1e293b' }}>Pattern</TableCell>
              <TableCell sx={{ color: '#fff', background: '#1e293b' }}>Match Type</TableCell>
              <TableCell sx={{ color: '#fff', background: '#1e293b' }}>Category</TableCell>
              <TableCell sx={{ color: '#fff', background: '#1e293b' }} align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rules.map((r: BudgetRule) => (
              <TableRow key={r.rule_id} sx={{ '&:hover': { background: 'rgba(255,255,255,0.05)' } }}>
                <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>{r.pattern}</TableCell>
                <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <span style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.75rem' }}>
                    {r.match_type}
                  </span>
                </TableCell>
                <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>{r.category}</TableCell>
                <TableCell align="right" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <IconButton size="small" color="error" onClick={() => deleteRule.mutate(r.rule_id)} disabled={deleteRule.isPending}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
            {rules.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} align="center" sx={{ color: 'text.secondary', py: 4, borderBottom: 'none' }}>
                  No automation rules created yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}

export default React.memo(RulesTab)
