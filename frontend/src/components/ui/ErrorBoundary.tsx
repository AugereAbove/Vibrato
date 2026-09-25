import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from './Button'
import { Icon } from './Icon'

interface Props {
  children: ReactNode
  label: string
  resetKey?: unknown
}

interface State {
  error: Error | null
  resetKey: unknown
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: undefined }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (props.resetKey !== state.resetKey) return { resetKey: props.resetKey, error: null }
    return null
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`${this.props.label} failed to render`, error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="error-state boundary" role="alert">
        <Icon name="alert" size={18} />
        <div className="stack" style={{ gap: 4 }}>
          <strong>The {this.props.label} could not be displayed.</strong>
          <span className="muted">{this.state.error.message}</span>
          <span className="faint">
            The rest of the app keeps working. Try again, or reload the page if it keeps happening.
          </span>
          <div>
            <Button size="sm" icon="refresh" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
          </div>
        </div>
      </div>
    )
  }
}
