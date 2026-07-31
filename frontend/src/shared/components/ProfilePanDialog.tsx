/**
 * Captures the user's PAN after sign-in.
 *
 * PAN stopped being the credential when Google sign-in landed - it is now profile
 * data. But two things still need it, so it has to be collected somewhere: CAS
 * statements are password-protected with the investor's own PAN, and AIS matching
 * keys on it.
 *
 * Opens by itself once, for an account that has none, and is otherwise reachable
 * from the account menu. Dismissable on purpose: nothing breaks without a PAN, the
 * upload form just asks for the password manually, so blocking the dashboard behind
 * this would be a worse trade than an occasional extra keystroke at upload time.
 */

import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Alert, Button, Dialog, DialogActions, DialogContent, DialogContentText,
  DialogTitle, TextField,
} from '@mui/material'

import { apiClient } from '../api/client'
import { useAppStore } from '../store/appStore'

const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/

interface Props {
  open: boolean
  onClose: () => void
}

export default function ProfilePanDialog({ open, onClose }: Props) {
  const storedPan = useAppStore((s) => s.pan)
  const setIdentity = useAppStore((s) => s.setIdentity)
  const [value, setValue] = useState(storedPan ?? '')
  const [error, setError] = useState<string | null>(null)

  // Re-seed when reopened: the dialog stays mounted, so without this it would show
  // whatever was last typed rather than what is actually saved.
  useEffect(() => {
    if (open) {
      setValue(storedPan ?? '')
      setError(null)
    }
  }, [open, storedPan])

  const save = useMutation({
    mutationFn: (pan: string) => apiClient.setProfilePan(pan),
    onSuccess: (data) => {
      setIdentity({ userId: useAppStore.getState().userId, pan: data.pan })
      onClose()
    },
    onError: (e: any) => {
      setError(e?.response?.data?.detail ?? 'Could not save your PAN.')
    },
  })

  const submit = () => {
    const pan = value.trim().toUpperCase()
    // Validated here as well as on the server so a typo costs no round trip. The
    // server check is the one that matters.
    if (!PAN_PATTERN.test(pan)) {
      setError('That does not look like a PAN. The format is ABCDE1234F.')
      return
    }
    setError(null)
    save.mutate(pan)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 800 }}>
        {storedPan ? 'Update your PAN' : 'Add your PAN'}
      </DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2.5, fontSize: '0.9rem' }}>
          CAS statements are password-protected with your PAN, so saving it here lets
          uploads unlock automatically. It is also used to match your AIS. You can skip
          this and enter the password manually each time instead.
        </DialogContentText>

        <TextField
          autoFocus
          fullWidth
          value={value}
          onChange={(e) => setValue(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="ABCDE1234F"
          inputProps={{ maxLength: 10, style: { letterSpacing: 2, fontWeight: 700 } }}
          autoComplete="off"
        />

        {error && <Alert severity="error" sx={{ mt: 2, borderRadius: '12px' }}>{error}</Alert>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} sx={{ textTransform: 'none' }}>
          Not now
        </Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={save.isPending}
          sx={{ textTransform: 'none', fontWeight: 700 }}
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
