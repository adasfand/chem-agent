import type { JsonValue, ToolCall } from '../types/api'
export type RetrievalRecord = Record<string, JsonValue>
export const record = (value: unknown): RetrievalRecord =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as RetrievalRecord)
    : {}
export const records = (value: unknown): RetrievalRecord[] =>
  Array.isArray(value)
    ? value
        .filter((item) => item !== null && typeof item === 'object' && !Array.isArray(item))
        .map(record)
    : []
export const text = (value: unknown): string => (typeof value === 'string' ? value : '')
export const entityTypeLabel = (value: string) =>
  ({
    data: '物理量',
    concept: '概念',
    method: '方法',
    process: '过程',
    material: '物质',
    artifact: '对象',
  })[value.toLowerCase()] ||
  value ||
  '实体'
export function parts(value: unknown): string[] {
  const values = Array.isArray(value) ? value : [value]
  return [
    ...new Set(
      values
        .flatMap((item) => text(item).split(/<SEP>/i))
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ]
}
export const sourceIds = (item: RetrievalRecord) => [
  ...new Set([...parts(item.source_ids), ...parts(item.source_id)]),
]
export const safeUrl = (value: unknown) =>
  typeof value === 'string' && /^https?:\/\/[^\s<>"']+$/i.test(value) ? value : ''
export function retrievalFor(call: ToolCall) {
  const data = record(call.output?.retrieval)
  const highLevel = parts(record(data.keywords).high_level)
  const lowLevel = parts(record(data.keywords).low_level)
  return {
    query: text(data.query) || text(call.arguments?.query) || text(call.requested_arguments?.query),
    mode: text(data.mode),
    keywords: [...highLevel, ...lowLevel],
    highLevel,
    lowLevel,
    entities: records(data.entities),
    relationships: records(data.relationships),
    hits: records(call.output?.hits),
    sources: records(data.graph_sources),
    references: records(data.references),
    metadata: record(data.metadata),
  }
}
function arrangeRing(count: number, links: [number, number][]) {
  const adjacent = Array.from({ length: count }, () => new Set<number>())
  for (const [a, b] of links) {
    adjacent[a]!.add(b)
    adjacent[b]!.add(a)
  }
  const unseen = new Set(Array.from({ length: count }, (_, index) => index))
  const order: number[] = []
  // Keep connected groups together, with depth-first chains occupying neighboring slots.
  while (unseen.size) {
    const start = [...unseen].sort((a, b) => adjacent[b]!.size - adjacent[a]!.size || a - b)[0]!
    const stack = [start]
    while (stack.length) {
      const node = stack.pop()!
      if (!unseen.delete(node)) continue
      order.push(node)
      stack.push(
        ...[...adjacent[node]!]
          .filter((id) => unseen.has(id))
          .sort((a, b) => adjacent[a]!.size - adjacent[b]!.size || b - a),
      )
    }
  }
  const score = (candidate: number[]) => {
    const position = new Map(candidate.map((id, index) => [id, index]))
    const intervals = links.map(([a, b]) =>
      [position.get(a)!, position.get(b)!].sort((a, b) => a - b),
    )
    let crossings = 0,
      span = 0
    intervals.forEach(([a, b], index) => {
      span += Math.min(b! - a!, count - (b! - a!))
      for (const [c, d] of intervals.slice(index + 1)) {
        if (a === c || a === d || b === c || b === d) continue
        if ((a! < c! && c! < b! && b! < d!) || (c! < a! && a! < d! && d! < b!)) crossings++
      }
    })
    // Crossing reduction always takes priority over shortening chords.
    return crossings * (links.length * count + 1) + span
  }
  if (count > 32 || links.length > 96) return order
  let best = score(order)
  // Bounded refinement prevents a dense response from causing unbounded UI work.
  for (let pass = 0; pass < 3; pass++) {
    let improved = false
    for (let a = 0; a < count; a++)
      for (let b = a + 1; b < count; b++) {
        const trial = [...order]
        ;[trial[a], trial[b]] = [trial[b]!, trial[a]!]
        const cost = score(trial)
        if (cost < best) {
          order.splice(0, count, ...trial)
          best = cost
          improved = true
        }
      }
    if (!improved) break
  }
  return order
}
export function graphLayout(entities: RetrievalRecord[], relationships: RetrievalRecord[]) {
  const nodes = entities.map((item, index) => {
    const name = text(item.name) || text(item.entity_name) || text(item.id) || '未命名实体'
    return {
      id: text(item.id) || name,
      name,
      index,
      type: text(item.type) || text(item.entity_type),
      x: 0,
      y: 0,
    }
  })
  const byId = new Map<string, (typeof nodes)[number]>()
  for (const node of nodes) {
    for (const alias of [node.id, node.name, text(entities[node.index]?.entity_name)]) {
      if (alias.trim()) byId.set(alias.trim().toLowerCase(), node)
    }
  }
  const edges = relationships.flatMap((item, index) => {
    const from = byId.get((text(item.source) || text(item.src_id)).trim().toLowerCase())
    const to = byId.get((text(item.target) || text(item.tgt_id)).trim().toLowerCase())
    return from && to && from !== to
      ? [{ from, to, index, description: parts(item.description).join('\n') }]
      : []
  })
  // Ring spacing depends on the longest label and node count, so circles cannot overlap.
  // Placement is visual only: edges above still require actual returned endpoints.
  const rows = Math.max(1, ...nodes.map((node) => Math.ceil(Array.from(node.name).length / 5)))
  const nodeRadius = Math.ceil(Math.hypot(45, (rows - 1) * 11) + 12)
  const orbit =
    nodes.length < 2
      ? 0
      : Math.max(160, (2 * nodeRadius + 32) / (2 * Math.sin(Math.PI / nodes.length)))
  const width = Math.max(480, 2 * (orbit + nodeRadius + 26))
  const height = Math.max(360, 2 * (orbit + nodeRadius + 26))
  const links = [
    ...new Map(
      edges.map((edge) => {
        const pair = [edge.from.index, edge.to.index].sort((a, b) => a - b) as [number, number]
        return [pair.join(':'), pair] as const
      }),
    ).values(),
  ]
  const order = arrangeRing(nodes.length, links)
  order.forEach((id, index) => {
    const node = nodes[id]!
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / nodes.length
    node.x = width / 2 + orbit * Math.cos(angle)
    node.y = height / 2 + orbit * Math.sin(angle)
  })
  return { nodes, edges, width, height, nodeRadius, order }
}
