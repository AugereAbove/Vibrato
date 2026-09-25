import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, describeError, http, query } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('query', () => {
  it('skips empty values', () => {
    expect(query({ a: 1, b: null, c: '', d: true, e: undefined })).toBe('?a=1&d=true')
    expect(query({})).toBe('')
  })
})

describe('http', () => {
  it('prefixes the api path and parses json', async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(http.get('/health')).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.anything())
  })

  it('sends json bodies', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => Response.json({ id: 'p1' }))
    vi.stubGlobal('fetch', fetchMock)
    await http.post('/projects', { name: 'Song' })
    const init = fetchMock.mock.calls[0][1]
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe('{"name":"Song"}')
    expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json')
  })

  it('turns structured errors into ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json(
          {
            error: {
              code: 'duplicate',
              what: 'This file was already imported.',
              why: 'Same content hash.',
              action: 'Open the existing recording.',
              details: ['hash abc'],
              existing_id: 'rec-9',
            },
          },
          { status: 409 },
        ),
      ),
    )
    const error = await http.get('/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      code: 'duplicate',
      existingId: 'rec-9',
      details: ['hash abc'],
    })
  })

  it('explains unstructured and network failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>', { status: 502, statusText: 'Bad Gateway' })),
    )
    await expect(http.get('/x')).rejects.toMatchObject({ status: 502, code: 'http_error' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))),
    )
    await expect(http.get('/x')).rejects.toMatchObject({ status: 0, code: 'offline' })
  })

  it('lets aborts through untouched', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new DOMException('aborted', 'AbortError'))),
    )
    await expect(http.get('/x')).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('describeError', () => {
  it('describes each kind of failure', () => {
    expect(describeError(new Error('boom'))).toMatchObject({ why: 'boom' })
    expect(describeError('nope')).toMatchObject({ what: 'Something went wrong.', why: 'nope' })
    const api = new ApiError(400, { code: 'bad', what: 'W', why: 'Y', action: 'A', details: [] })
    expect(describeError(api)).toEqual({ what: 'W', why: 'Y', action: 'A' })
  })
})
