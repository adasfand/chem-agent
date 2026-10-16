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
    content: '知识内容',
    event: '事件',
    naturalobject: '自然物质',
    organization: '机构',
    relationship_endpoint: '关系端点',
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

export const retrievalGraphLimits = { entities: 80, relationships: 160 }

export function completeRetrievalGraph(
  entities: RetrievalRecord[],
  relationships: RetrievalRecord[],
) {
  const nodes = entities.slice(0, retrievalGraphLimits.entities).map((item) => ({ ...item }))
  const links = relationships.slice(0, retrievalGraphLimits.relationships)
  const byAlias = new Map<string, RetrievalRecord>()
  const normalize = (value: string) => value.trim().toLowerCase()
  for (const node of nodes)
    for (const alias of [node.id, node.name, node.entity_name])
      if (text(alias).trim()) byAlias.set(normalize(text(alias)), node)
  let endpointCount = 0
  let endpointsLimited = false
  for (const edge of links) {
    for (const name of [
      text(edge.source) || text(edge.src_id),
      text(edge.target) || text(edge.tgt_id),
    ]) {
      const key = normalize(name)
      if (!key) continue
      let node = byAlias.get(key)
      if (!node && nodes.length >= retrievalGraphLimits.entities) endpointsLimited = true
      if (!node && nodes.length < retrievalGraphLimits.entities) {
        node = {
          id: name.trim(),
          name: name.trim(),
          type: 'relationship_endpoint',
          description: '该名称来自本轮返回关系的端点，未返回独立实体说明；请核对关联关系原文。',
          source_ids: [],
          relationship_endpoint: true,
        }
        nodes.push(node)
        byAlias.set(key, node)
        endpointCount++
      }
      if (node?.relationship_endpoint)
        node.source_ids = [...new Set([...sourceIds(node), ...sourceIds(edge)])]
    }
  }
  return {
    entities: nodes,
    relationships: links,
    endpointCount,
    limited:
      endpointsLimited || entities.length > nodes.length || relationships.length > links.length,
  }
}

export function retrievalNotices(
  metadata: RetrievalRecord,
  entities: RetrievalRecord[],
  relationships: RetrievalRecord[],
  graph: ReturnType<typeof completeRetrievalGraph>,
) {
  const notices: string[] = []
  const original = record(metadata.original_counts)
  const processing = record(metadata.processing_info)
  const count = (value: unknown) =>
    typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : undefined
  const lostEntities = Math.max(0, (count(original.entities) ?? entities.length) - entities.length)
  const lostRelations = Math.max(
    0,
    (count(original.relationships) ?? relationships.length) - relationships.length,
  )
  if (lostEntities || lostRelations) {
    const counts = `保存了 ${entities.length} / ${count(original.entities) ?? entities.length} 个检索实体、${relationships.length} / ${count(original.relationships) ?? relationships.length} 条关系。`
    notices.push(
      counts +
        (metadata.graph_limits
          ? '超出保存上限的部分未保留。'
          : '旧记录已按原上限截断；重新提问后使用新的检索范围。'),
    )
  }
  if (graph.endpointCount)
    notices.push(
      `另显示 ${graph.endpointCount} 个本轮关系中的端点，以保留真实连线；端点未提供独立实体说明。`,
    )
  if (graph.limited)
    notices.push(
      '图谱最多显示 80 个实体、160 条关系，按返回顺序保留；其余已保存数据可在执行记录中查看。',
    )
  const upstreamEntities = count(processing.total_entities_found)
  const upstreamRelations = count(processing.total_relations_found)
  const finalEntities = count(processing.entities_after_truncation)
  const finalRelations = count(processing.relations_after_truncation)
  if (
    (upstreamEntities !== undefined &&
      finalEntities !== undefined &&
      upstreamEntities > finalEntities) ||
    (upstreamRelations !== undefined &&
      finalRelations !== undefined &&
      upstreamRelations > finalRelations)
  )
    notices.push('检索器已按相关性与文本预算筛选候选，本图展示筛选后的返回结果。')
  if (metadata.sources_truncated) notices.push('关联原文数量已达上限，未载入的来源会单独标明。')
  if (metadata.truncated && !notices.length)
    notices.push('部分描述或原文可能按长度截断；这不代表图中实体被隐藏。')
  return notices
}

export function retrievalFor(call: ToolCall) {
  const data = record(call.output?.retrieval)
  const highLevel = parts(record(data.keywords).high_level)
  const lowLevel = parts(record(data.keywords).low_level)
  const entities = records(data.entities)
  const relationships = records(data.relationships)
  const graph = completeRetrievalGraph(entities, relationships)
  const metadata = record(data.metadata)
  return {
    query: text(data.query) || text(call.arguments?.query) || text(call.requested_arguments?.query),
    mode: text(data.mode),
    keywords: [...highLevel, ...lowLevel],
    highLevel,
    lowLevel,
    entities: graph.entities,
    relationships: graph.relationships,
    hits: records(call.output?.hits),
    sources: records(data.graph_sources),
    references: records(data.references),
    metadata,
    notices: retrievalNotices(metadata, entities, relationships, graph),
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

export function defaultEntityIndex(
  entities: RetrievalRecord[],
  relationships: RetrievalRecord[],
  hits: RetrievalRecord[],
  citations: string[] = [],
  keywords: string[] = [],
  query = '',
): number {
  const graph = graphLayout(entities, relationships)
  if (!graph.nodes.length) return 0
  const hitIds = new Set(hits.map((hit) => text(hit.chunk_id)).filter(Boolean))
  const citedHitIds = new Set(citations.filter((id) => hitIds.has(id)))
  const normalize = (value: string) => value.trim().toLowerCase()
  const terms = [...new Set(keywords.map(normalize).filter(Boolean))]
  const queryText = normalize(query)
  const degree = graph.nodes.map(
    (node) =>
      graph.edges.filter((edge) => edge.from.index === node.index || edge.to.index === node.index)
        .length,
  )
  // Initial focus is a display preference based on returned data, not model confidence.
  // Prefer a node with an actual visible relationship when any are available.
  const candidates = graph.nodes.filter((node) => !graph.edges.length || degree[node.index])
  const priorities = (index: number): number[] => {
    const ids = sourceIds(entities[index]!)
    const name = normalize(graph.nodes[index]!.name)
    return [
      ids.filter((id) => citedHitIds.has(id)).length,
      ids.filter((id) => hitIds.has(id)).length,
      terms.filter((term) => name.includes(term) || term.includes(name)).length,
      queryText && queryText.includes(name) ? 1 : 0,
      degree[index]!,
      -index,
    ]
  }
  return candidates.reduce((best, node) => {
    const candidate = priorities(node.index)
    const previous = priorities(best)
    const difference = candidate.findIndex((value, index) => value !== previous[index])
    return difference >= 0 && candidate[difference]! > previous[difference]! ? node.index : best
  }, candidates[0]!.index)
}
