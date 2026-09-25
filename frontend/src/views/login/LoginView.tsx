import { useState } from 'react'
import { authApi } from '../../api/endpoints'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/Controls'
import { Icon } from '../../components/ui/Icon'

export function LoginView() {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = () => {
    const trimmed = code.trim()
    if (!trimmed) {
      setError('Enter the invite code from your link.')
      return
    }
    setSubmitting(true)
    setError(null)
    // The claim endpoint sets the session cookie and redirects - a full
    // navigation, not a fetch, so the browser stores the cookie normally.
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
