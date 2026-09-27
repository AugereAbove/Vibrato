import { useState } from 'react'
import { authApi } from '../../api/endpoints'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/Controls'
import { Icon } from '../../components/ui/Icon'

function initialError(): string | null {
  if (new URLSearchParams(window.location.search).get('invite') !== 'invalid') return null
  return 'That link has already been used or has expired. Ask the project owner for a new one.'
}

export function LoginView() {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(initialError)
  const [submitting, setSubmitting] = useState(false)

  const submit = () => {
    const trimmed = code.trim()
    if (!trimmed) {
      setError('Enter the invite code from your link.')
      return
    }
    setSubmitting(true)
    setError(null)
    window.location.href = authApi.claimUrl(trimmed)
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <Icon name="mic" size={28} />
        <h1>Sign in to Vibrato</h1>
        <p>Use the invite link the project owner sent you, or paste its code below.</p>
        <TextField
          label="Invite code"
          placeholder="e.g. inv_a1b2c3d4"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit()
          }}
          error={error}
          autoFocus
        />
        <Button variant="primary" onClick={submit} loading={submitting} disabled={submitting}>
          Continue
        </Button>
      </div>
    </div>
  )
}
