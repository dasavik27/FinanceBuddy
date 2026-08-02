import React, { useState } from 'react'
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Box,
  Typography, Stack, FormControl, InputLabel, Select, MenuItem, TextField,
  IconButton, Divider, CircularProgress, Alert
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile'

interface UploadStatementModalProps {
  open: boolean
  onClose: () => void
  /** Resolves to null on success, or the server's message when the upload is refused. */
  onUpload: (file: File, bank: string, accountType: string) => Promise<string | null>
  loading?: boolean
}

const POPULAR_BANKS = [
  { value: 'HDFC', label: 'HDFC Bank' },
  { value: 'ICICI', label: 'ICICI Bank' },
  { value: 'SBI', label: 'State Bank of India (SBI)' },
  { value: 'AXIS', label: 'Axis Bank' },
  { value: 'KOTAK', label: 'Kotak Mahindra Bank' },
  { value: 'OTHER', label: 'Other Bank (Custom)' },
]

const ACCOUNT_TYPES = [
  { value: 'Savings Account', label: 'Savings Account' },
  { value: 'Credit Card', label: 'Credit Card' },
  { value: 'Current Account', label: 'Current Account' },
  { value: 'Salary Account', label: 'Salary Account' },
  { value: 'Wallet / Prepaid', label: 'Wallet / Prepaid Card' },
]

export default function UploadStatementModal({
  open,
  onClose,
  onUpload,
  loading = false
}: UploadStatementModalProps) {
  const [selectedBank, setSelectedBank] = useState<string>('HDFC')
  const [customBankName, setCustomBankName] = useState<string>('')
  const [selectedAccountType, setSelectedAccountType] = useState<string>('Savings Account')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0])
      setErrorMessage(null)
    }
  }

  const handleSubmit = async () => {
    if (!selectedFile) {
      setErrorMessage('Please select a CSV or Excel statement file.')
      return
    }

    const bankName = selectedBank === 'OTHER' ? (customBankName.trim() || 'CUSTOM') : selectedBank
    if (!bankName) {
      setErrorMessage('Please specify the Bank Name.')
      return
    }

    setErrorMessage(null)
    // A refused upload answers 422 (oversized / unsupported) or 400 (with the columns
    // the parser did find). That message belongs here, in front of the user, rather
    // than on a card behind the still-open dialog.
    const failure = await onUpload(selectedFile, bankName, selectedAccountType)
    if (failure) {
      setErrorMessage(failure)
      return
    }
    setSelectedFile(null)
    setCustomBankName('')
    onClose()
  }

  const handleModalClose = () => {
    if (!loading) {
      setSelectedFile(null)
      setErrorMessage(null)
      onClose()
    }
  }

  return (
    <Dialog
      open={open}
      onClose={handleModalClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          background: 'linear-gradient(180deg, #0f172a 0%, #020617 100%)',
          color: '#fff',
          borderRadius: 4,
          border: '1px solid rgba(255, 255, 255, 0.1)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)'
        }
      }}
    >
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <CloudUploadIcon sx={{ color: '#818cf8', fontSize: 28 }} />
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              Upload Bank / Card Statement
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8' }}>
              Specify your bank and account type to ensure precise categorization
            </Typography>
          </Box>
        </Box>
        <IconButton onClick={handleModalClose} disabled={loading} sx={{ color: '#94a3b8', '&:hover': { color: '#fff' } }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <Divider sx={{ borderColor: 'rgba(255, 255, 255, 0.08)' }} />

      <DialogContent sx={{ py: 3 }}>
        <Stack spacing={2.5}>
          {errorMessage && (
            <Alert severity="error" sx={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#fca5a5', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
              {errorMessage}
            </Alert>
          )}

          {/* Bank Selection */}
          <FormControl fullWidth size="small">
            <InputLabel sx={{ color: '#94a3b8' }}>Bank Name *</InputLabel>
            <Select
              value={selectedBank}
              label="Bank Name *"
              onChange={(e) => setSelectedBank(e.target.value as string)}
              sx={{
                color: '#fff',
                backgroundColor: 'rgba(255,255,255,0.03)',
                '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' }
              }}
            >
              {POPULAR_BANKS.map((b) => (
                <MenuItem key={b.value} value={b.value}>
                  {b.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Custom Bank Name if "OTHER" selected */}
          {selectedBank === 'OTHER' && (
            <TextField
              label="Enter Custom Bank Name *"
              size="small"
              fullWidth
              value={customBankName}
              onChange={(e) => setCustomBankName(e.target.value)}
              placeholder="e.g. IndusInd Bank, Citibank, HSBC"
              sx={{
                input: { color: '#fff' },
                '.MuiInputLabel-root': { color: '#94a3b8' },
                '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' }
              }}
            />
          )}

          {/* Account Type Selection */}
          <FormControl fullWidth size="small">
            <InputLabel sx={{ color: '#94a3b8' }}>Account / Instrument Type *</InputLabel>
            <Select
              value={selectedAccountType}
              label="Account / Instrument Type *"
              onChange={(e) => setSelectedAccountType(e.target.value as string)}
              sx={{
                color: '#fff',
                backgroundColor: 'rgba(255,255,255,0.03)',
                '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' }
              }}
            >
              {ACCOUNT_TYPES.map((at) => (
                <MenuItem key={at.value} value={at.value}>
                  {at.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* File Selector Dropzone Area */}
          <Box
            component="label"
            sx={{
              p: 3,
              border: '2px dashed',
              borderColor: selectedFile ? '#818cf8' : 'rgba(255, 255, 255, 0.15)',
              borderRadius: 3,
              textAlign: 'center',
              cursor: 'pointer',
              background: selectedFile ? 'rgba(99, 102, 241, 0.08)' : 'rgba(255, 255, 255, 0.02)',
              transition: 'all 0.2s ease',
              display: 'block',
              '&:hover': {
                borderColor: '#818cf8',
                backgroundColor: 'rgba(99, 102, 241, 0.05)'
              }
            }}
          >
            <input
              type="file"
              hidden
              accept=".csv,.xlsx,.xls"
              onChange={handleFileChange}
            />
            {selectedFile ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                <InsertDriveFileIcon sx={{ fontSize: 40, color: '#34d399' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#fff' }}>
                  {selectedFile.name}
                </Typography>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  {(selectedFile.size / 1024).toFixed(1)} KB • Click to change file
                </Typography>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                <CloudUploadIcon sx={{ fontSize: 40, color: '#818cf8' }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#fff' }}>
                  Click to select Statement File
                </Typography>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Supports CSV, XLS, XLSX statements from all banks
                </Typography>
              </Box>
            )}
          </Box>
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
        <Button onClick={handleModalClose} disabled={loading} sx={{ color: '#94a3b8', textTransform: 'none', fontWeight: 600 }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={loading || !selectedFile}
          startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <CloudUploadIcon />}
          sx={{
            background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
            px: 3, py: 1, borderRadius: 2,
            fontWeight: 600,
            textTransform: 'none',
            boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)',
            '&:hover': { background: 'linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)' }
          }}
        >
          {loading ? 'Processing Statement...' : 'Import Statement'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
