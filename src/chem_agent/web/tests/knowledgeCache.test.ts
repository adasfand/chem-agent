import { describe, expect, it, vi } from 'vitest'
import type { KnowledgeDetail } from '../src/types/api'
import { createKnowledgeCache } from '../src/services/knowledgeCache'

const card: KnowledgeDetail = {
  doc_id: 'heat',
  title: '显热',
  source: '教学资料',
  chunk_count: 1,
  text: 'Q = m cp ΔT',
}

describe('knowledge browsing cache', () => {
  it('shares in-flight and completed reads when revisiting a card', async () => {
    const fetchDetail = vi.fn().mockResolvedValue(card)
    const cache = createKnowledgeCache(fetchDetail)
    const first = cache.load('heat')
    const second = cache.load('heat')
    expect(first).toBe(second)
    await expect(first).resolves.toEqual(card)
    await expect(cache.load('heat')).resolves.toEqual(card)
    expect(fetchDetail).toHaveBeenCalledTimes(1)
  })

  it('allows retry after an offline read fails', async () => {
    const fetchDetail = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(card)
    const cache = createKnowledgeCache(fetchDetail)
    await expect(cache.load('heat')).rejects.toThrow('offline')
    await expect(cache.load('heat')).resolves.toEqual(card)
    expect(fetchDetail).toHaveBeenCalledTimes(2)
  })

  it('uses fresh data after reconnect even if an earlier request fails later', async () => {
    let rejectOld!: (error: Error) => void
    const old = new Promise<KnowledgeDetail>((_, reject) => {
      rejectOld = reject
    })
    const fetchDetail = vi.fn().mockReturnValueOnce(old).mockResolvedValue(card)
    const cache = createKnowledgeCache(fetchDetail)
    const first = cache.load('heat')
    const rejected = expect(first).rejects.toThrow('old backend')
    cache.clear()
    const fresh = cache.load('heat')
    rejectOld(new Error('old backend'))
    await rejected
    await fresh
    await expect(cache.load('heat')).resolves.toEqual(card)
    expect(fetchDetail).toHaveBeenCalledTimes(2)
  })
})
