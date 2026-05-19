import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface Props {
  children: ReactNode
  // Used as the screen heading; falls back to "Something went wrong".
  title?: string
}

interface State {
  error: Error | null
  info: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info })
    // Surface to the dev console as well — the inline UI may be scrolled away.
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info)
  }

  private reset = () => this.setState({ error: null, info: null })

  render() {
    const { error, info } = this.state
    if (!error) return this.props.children

    return (
      <div className="mx-auto max-w-3xl py-8">
        <Card className="border-destructive/40">
          <CardHeader className="border-b bg-destructive/[0.04]">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <CardTitle className="text-lg">{this.props.title || 'Something went wrong'}</CardTitle>
                <CardDescription className="mt-1">
                  This page hit a runtime error and couldn't finish rendering. The details below
                  should help pinpoint the cause.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={this.reset} className="shrink-0">
                <RefreshCw className="mr-2 h-3.5 w-3.5" />
                Retry
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 p-6">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Error
              </p>
              <p className="mt-1 break-words font-mono text-sm text-destructive">
                {error.name}: {error.message}
              </p>
            </div>
            {error.stack ? (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Stack
                </p>
                <pre className="mt-1 max-h-64 overflow-auto rounded-md border bg-muted/40 p-3 text-[11px] leading-5 text-muted-foreground">
                  {error.stack}
                </pre>
              </div>
            ) : null}
            {info?.componentStack ? (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Component stack
                </p>
                <pre className="mt-1 max-h-64 overflow-auto rounded-md border bg-muted/40 p-3 text-[11px] leading-5 text-muted-foreground">
                  {info.componentStack}
                </pre>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    )
  }
}
