import React, { useState, useEffect } from 'react'
import { Box, Typography, Card, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Button, TextField, IconButton, FormControl, Select, MenuItem, InputLabel } from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import { api } from '../../../shared/api/client'

interface RulesTabProps {
  onRulesApplied?: () => Promise<void> | void
}

export default function RulesTab({ onRulesApplied }: RulesTabProps) {
  const [rules, setRules] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [applyMessage, setApplyMessage] = useState<string | null>(null)
  
  const [newPattern, setNewPattern] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [newMatchType, setNewMatchType] = useState('contains')

  // Sandbox state
  const [testDescription, setTestDescription] = useState('')
  const [matchedRule, setMatchedRule] = useState<any | null>(null)

  const fetchRules = async () => {
    try {
      setLoading(true)
      const res = await api.get('/budget/rules')
      setRules(res.data)
    } catch (e) {
      console.error('Failed to fetch rules', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRules()
  }, [])

  const handleAddRule = async () => {
    if (!newPattern || !newCategory) return
    try {
      await api.post('/budget/rules', {
        pattern: newPattern,
        category: newCategory,
        match_type: newMatchType
      })
      setNewPattern('')
      setNewCategory('')
      fetchRules()
    } catch (e) {
      console.error('Failed to add rule', e)
    }
  }

  const handleDeleteRule = async (id: string) => {
    try {
      await api.delete(`/budget/rules/${id}`)
      fetchRules()
    } catch (e) {
      console.error('Failed to delete rule', e)
    }
  }

  const handleApplyRulesToAll = async () => {
    try {
      setApplying(true)
      setApplyMessage(null)
      const res = await api.post('/budget/rules/apply-all')
      setApplyMessage(`Successfully re-categorized ${res.data.transactions_recalculated} transactions!`)
      fetchRules()
      if (onRulesApplied) {
        await onRulesApplied()
      }
    } catch (e) {
      console.error('Failed to apply rules', e)
      setApplyMessage('Failed to apply rules.')
    } finally {
      setApplying(false)
    }
  }

  // Sandbox Logic
  useEffect(() => {
    if (!testDescription) {
      setMatchedRule(null)
      return
    }
    
    // Find first matching rule
    const match = rules.find(r => {
      if (r.match_type === 'exact') {
        return testDescription.trim().toLowerCase() === r.pattern.trim().toLowerCase()
      } else if (r.match_type === 'regex') {
        try {
          const regex = new RegExp(r.pattern, 'i')
          return regex.test(testDescription)
        } catch {
          return false
        }
      } else {
        // contains
        return testDescription.toLowerCase().includes(r.pattern.toLowerCase())
      }
    })
    
    setMatchedRule(match || null)
  }, [testDescription, rules])

  return (
    <Box sx={{ color: '#fff' }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, mb: 4 }}>
        <Card sx={{ flex: 1, minWidth: 300, p: 3, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Create Automation Rule</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <FormControl size="small" fullWidth>
              <InputLabel sx={{ color: 'text.secondary' }}>Match Type</InputLabel>
              <Select value={newMatchType} label="Match Type" onChange={e => setNewMatchType(e.target.value)} sx={{ color: '#fff' }}>
                <MenuItem value="contains">Text Contains</MenuItem>
                <MenuItem value="exact">Exact Match</MenuItem>
                <MenuItem value="regex">Regex</MenuItem>
              </Select>
            </FormControl>
            <TextField 
              size="small" 
              label="Pattern (e.g. Uber, Zomato)" 
              value={newPattern} 
              onChange={e => setNewPattern(e.target.value)}
              InputLabelProps={{ sx: { color: 'text.secondary' } }}
              sx={{ input: { color: '#fff' } }}
            />
            <TextField 
              size="small" 
              label="Assign Category (e.g. Transport, Dining)" 
              value={newCategory} 
              onChange={e => setNewCategory(e.target.value)}
              InputLabelProps={{ sx: { color: 'text.secondary' } }}
              sx={{ input: { color: '#fff' } }}
            />
            <Button variant="contained" onClick={handleAddRule} disabled={!newPattern || !newCategory}>
              Add Rule
            </Button>
          </Box>
        </Card>
        
        <Card sx={{ flex: 1, minWidth: 300, p: 3, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Testing Sandbox</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Type a sample bank transaction description here to see if any of your rules will catch it.
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
            <Box sx={{ p: 2, borderRadius: 2, background: matchedRule ? 'rgba(74, 222, 128, 0.1)' : 'rgba(255, 255, 255, 0.05)', border: matchedRule ? '1px solid rgba(74, 222, 128, 0.3)' : '1px solid rgba(255,255,255,0.1)' }}>
              {matchedRule ? (
                <>
                  <Typography variant="body2" sx={{ color: '#4ade80', fontWeight: 600 }}>Rule Matched!</Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>It will be categorized as: <strong>{matchedRule.category}</strong></Typography>
                  <Typography variant="caption" color="text.secondary">Matched by rule: "{matchedRule.pattern}" ({matchedRule.match_type})</Typography>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">No rules matched. It will remain Uncategorized.</Typography>
              )}
            </Box>
          )}
        </Card>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 2 }}>
        <Typography variant="h6">Active Rules</Typography>
        <Button 
          variant="outlined" 
          color="primary" 
          disabled={applying || rules.length === 0}
          onClick={handleApplyRulesToAll}
          sx={{ textTransform: 'none' }}
        >
          {applying ? 'Applying Rules...' : '⚡ Re-apply Rules to All Past Transactions'}
        </Button>
      </Box>

      {applyMessage && (
        <Typography variant="body2" sx={{ mb: 2, color: applyMessage.includes('Successfully') ? '#4ade80' : '#f87171', fontWeight: 500 }}>
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
            {rules.map(r => (
              <TableRow key={r.rule_id} sx={{ '&:hover': { background: 'rgba(255,255,255,0.05)' } }}>
                <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>{r.pattern}</TableCell>
                <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <span style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.75rem' }}>
                    {r.match_type}
                  </span>
                </TableCell>
                <TableCell sx={{ color: '#cbd5e1', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>{r.category}</TableCell>
                <TableCell align="right" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <IconButton size="small" color="error" onClick={() => handleDeleteRule(r.rule_id)}>
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
