export interface ErrorBody {
  code: string
  what: string
  why: string
  action: string
  details: string[]
  existing_id?: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly what: string
  readonly why: string
  readonly action: string
  readonly details: string[]
  readonly existingId?: string

  constructor(status: number, body: ErrorBody) {
    super(body.what)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.what = body.what
    this.why = body.why
    this.action = body.action
    this.details = body.details ?? []
    this.existingId = body.existing_id
  }
}

const BASE = '/api'

function offlineError(): ApiError {
  return new ApiError(0, {
    code: 'offline',
    what: 'The analysis server is not responding.',
    why: 'The backend process may have stopped or is still starting.',
    action: 'Check the terminal where you started Vibrato, then retry.',
    details: [],
  })
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { error?: ErrorBody }
    if (body.error) return new ApiError(response.status, body.error)
  } catch {
    return new ApiError(response.status, {
      code: 'http_error',
      what: `The server answered with status ${response.status}.`,
      why: response.statusText || 'The response was not in the expected format.',
      action: 'Try again. If it keeps happening, open Diagnostics and export a debug bundle.',
      details: [],
    })
  }
  return new ApiError(response.status, {
    code: 'http_error',
    what: `The server answered with status ${response.status}.`,
    why: response.statusText,
    action: 'Try again.',
    details: [],
  })
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response
  try {
    response = await fetch(BASE + path, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw offlineError()
  }
  if (!response.ok) throw await parseError(response)
  return response
}

function jsonInit(method: string, body?: unknown, signal?: AbortSignal): RequestInit {
  return {
    method,
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const http = {
  async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return (await send(path, { signal })).json() as Promise<T>
  },
  async post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return (await send(path, jsonInit('POST', body ?? {}, signal))).json() as Promise<T>
  },
  async put<T>(path: string, body: unknown): Promise<T> {
    return (await send(path, jsonInit('PUT', body))).json() as Promise<T>
  },
  async patch<T>(path: string, body: unknown): Promise<T> {
    return (await send(path, jsonInit('PATCH', body))).json() as Promise<T>
  },
  async del<T>(path: string): Promise<T> {
    return (await send(path, { method: 'DELETE' })).json() as Promise<T>
  },
  async form<T>(path: string, form: FormData): Promise<T> {
    return (await send(path, { method: 'POST', body: form })).json() as Promise<T>
  },
  async buffer(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
    return (await send(path, { signal })).arrayBuffer()
  },
  async blob(path: string, method = 'GET'): Promise<Blob> {
    return (await send(path, { method })).blob()
  },
  async text(path: string): Promise<string> {
    return (await send(path)).text()
  },
  url(path: string): string {
    return BASE + path
  },
}

export function describeError(error: unknown): { what: string; why: string; action: string } {
  if (error instanceof ApiError) return { what: error.what, why: error.why, action: error.action }
  if (error instanceof Error) {
    return {
      what: 'Something went wrong in the interface.',
      why: error.message,
      action: 'Try again, or reload the page.',
    }
  }
  return { what: 'Something went wrong.', why: String(error), action: 'Try again.' }
}
