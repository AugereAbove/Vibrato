import { useState } from 'react'
import { authApi } from '../../api/endpoints'
import { ApiError } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/Controls'
import { Icon } from '../../components/ui/Icon'
import { checkAuth } from '../../state/auth'

const USED_MESSAGE = 'That link has already been used or has expired. Ask the project owner for a new one.'

function params(): URLSearchParams {
  return new URLSearchParams(window.location.search)
}

function initialError(): string | null {
  return params().get('invite') === 'invalid' ? USED_MESSAGE : null
}

export function LoginView() {
  const [invite] = useState(() => params().get('claim'))
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(initialError)
  const [submitting, setSubmitting] = useState(false)

  const signIn = async (value: string) => {
    setSubmitting(true)
    setError(null)
    try {
      await authApi.claim(value)
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === 'invalid_invite'
          ? USED_MESSAGE
          : 'Could not sign in. Check your connection and try again.',
      )
      setSubmitting(false)
      return
    }
    window.history.replaceState(null, '', window.location.pathname)
    await checkAuth()
  }

  const submit = () => {
    const trimmed = code.trim()
    if (!trimmed) {
      setError('Enter the invite code from your link.')
      return
    }
    void signIn(trimmed)
  }

  if (invite) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <Icon name="mic" size={28} />
          <h1>You’re invited to Vibrato</h1>
          <p>Press the button to sign in. This link only works once, so open it on the device you’ll use.</p>
          {error ? <p className="login-error">{error}</p> : null}
          <Button
            variant="primary"
            onClick={() => void signIn(invite)}
            loading={submitting}
            disabled={submitting}
          >
            Sign in
          </Button>
        </div>
      </div>
    )
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
