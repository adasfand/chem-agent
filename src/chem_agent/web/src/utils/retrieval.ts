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
  ({ data: '物理量', concept: '概念', method: '方法', process: '过程', material: '物质' })[
    value.toLowerCase()
  ] ||
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
  return {
    query: text(data.query) || text(call.arguments?.query) || text(call.requested_arguments?.query),
    mode: text(data.mode),
    keywords: [
      ...parts(record(data.keywords).high_level),
      ...parts(record(data.keywords).low_level),
    ],
    entities: records(data.entities),
    relationships: records(data.relationships),
    hits: records(call.output?.hits),
    sources: records(data.graph_sources),
    references: records(data.references),
    metadata: record(data.metadata),
  }
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
  // Undirected graph distances establish columns; fixed lanes keep labels apart.
  // Components remain separate and no relationship is inferred from proximity.
  const adjacent = nodes.map(() => new Set<number>())
  for (const edge of edges) {
    adjacent[edge.from.index]!.add(edge.to.index)
    adjacent[edge.to.index]!.add(edge.from.index)
  }
  const unseen = new Set(nodes.map((node) => node.index))
  let offset = 0
  const components: { indices: number[]; offset: number; width: number; height: number }[] = []
  const lane = Math.max(
    105,
    ...nodes.map((node) => Math.ceil(Array.from(node.name).length / 11) * 14 + 55),
  )
  while (unseen.size) {
    const root = [...unseen].sort((a, b) => adjacent[b]!.size - adjacent[a]!.size || a - b)[0]!
    const levels: number[][] = [[root]]
    unseen.delete(root)
    for (let depth = 0; depth < levels.length; depth++) {
      const next: number[] = []
      for (const index of levels[depth]!) {
        for (const neighbor of adjacent[index]!) {
          if (unseen.delete(neighbor)) next.push(neighbor)
        }
      }
      if (next.length) levels.push(next)
    }
    const rows = Math.max(...levels.map((level) => level.length))
    for (const [depth, level] of levels.entries()) {
      level.forEach((index, row) => {
        nodes[index]!.x = 110 + depth * 245
        nodes[index]!.y = offset + lane / 2 + 20 + ((rows - level.length) / 2 + row) * lane
      })
    }
    components.push({
      indices: levels.flat(),
      offset,
      width: 220 + (levels.length - 1) * 245,
      height: rows * lane + 55,
    })
    offset += rows * lane + 55
  }
  // Pack disconnected components into two lanes rather than a tall strip.
  const columns = [
    { width: 0, height: 0 },
    { width: 0, height: 0 },
  ]
  const placements = components.map((component) => {
    const column = columns[0]!.height <= columns[1]!.height ? 0 : 1
    const y = columns[column]!.height
    columns[column]!.height += component.height
    columns[column]!.width = Math.max(columns[column]!.width, component.width)
    return { component, column, y }
  })
  for (const { component, column, y } of placements) {
    for (const index of component.indices) {
      nodes[index]!.x += column ? columns[0]!.width + 40 : 0
      nodes[index]!.y += y - component.offset
    }
  }
  return {
    nodes,
    edges,
    width: Math.max(480, columns[0]!.width + columns[1]!.width + (columns[1]!.width ? 40 : 0)),
    height: Math.max(230, columns[0]!.height, columns[1]!.height),
  }
}
