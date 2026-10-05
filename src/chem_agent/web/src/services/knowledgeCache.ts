import type { KnowledgeDetail } from '../types/api'

/** Knowledge is fixed for a backend lifetime; a successful reconnect invalidates this cache. */
export function createKnowledgeCache(fetchDetail: (id: string) => Promise<KnowledgeDetail>) {
  const entries = new Map<string, Promise<KnowledgeDetail>>()
  return {
    clear: () => entries.clear(),
    load(id: string) {
      const cached = entries.get(id)
      if (cached) return cached
      // Bound memory use even when a larger knowledge corpus is loaded later.
      if (entries.size >= 32) entries.delete(entries.keys().next().value!)
      const pending = fetchDetail(id).catch((error: unknown) => {
        if (entries.get(id) === pending) entries.delete(id)
        throw error
      })
      entries.set(id, pending)
      return pending
    },
  }
}
