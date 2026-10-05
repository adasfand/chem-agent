import { afterEach, describe, expect, it, vi } from 'vitest'
import { request } from '../src/services/api'

afterEach(() => vi.unstubAllGlobals())

describe('malformed response recovery', () => {
  it('keeps an accepted POST with unreadable JSON ambiguous so the session can recover it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('truncated-json', { status: 202 })),
    )
    await expect(request('/api/jobs', { method: 'POST', body: '{}' })).rejects.toMatchObject({
      name: 'ApiError',
      status: undefined,
    })
  })

  it('preserves a rejected HTTP status even when its response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Forbidden', { status: 403 })))
    await expect(request('/api/jobs', { method: 'POST', body: '{}' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 403,
    })
  })
})
