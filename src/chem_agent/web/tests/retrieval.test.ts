import { describe, expect, it } from 'vitest'
import {
  defaultEntityIndex,
  graphLayout,
  retrievalFor,
  sourceIds,
  safeUrl,
  completeRetrievalGraph,
  retrievalNotices,
} from '../src/utils/retrieval'
describe('retrieval provenance', () => {
  it('keeps 24 entities visible and completes only explicitly returned relation endpoints', () => {
    const entities = Array.from({ length: 24 }, (_, i) => ({ id: `E${i}`, name: `实体${i}` }))
    const relationships = [
      { source: '实体0', target: '端点', source_ids: ['edge-source'] },
      { source: 'E1', target: '端点', source_ids: ['second-source'] },
    ]
    const before = JSON.stringify({ entities, relationships })
    const graph = completeRetrievalGraph(entities, relationships)
    expect(graph.entities).toHaveLength(25)
    expect(graph.endpointCount).toBe(1)
    expect(graph.entities.at(-1)).toMatchObject({
      id: '端点',
      relationship_endpoint: true,
      source_ids: ['edge-source', 'second-source'],
    })
    expect(graphLayout(graph.entities, graph.relationships).edges).toHaveLength(2)
    expect(JSON.stringify({ entities, relationships })).toBe(before)
  })
  it('bounds oversized imported graphs and reports missing endpoints instead of inventing links', () => {
    const entities = Array.from({ length: 90 }, (_, i) => ({ id: `E${i}` }))
    const relationships = Array.from({ length: 200 }, (_, i) => ({ source: 'E0', target: `E${i}` }))
    const graph = completeRetrievalGraph(entities, relationships)
    expect(graph.entities).toHaveLength(80)
    expect(graph.relationships).toHaveLength(160)
    expect(graph.limited).toBe(true)
    expect(graphLayout(graph.entities, graph.relationships).edges).toHaveLength(79)
    expect(retrievalNotices({}, entities, relationships, graph).join('')).toContain('80 个实体')
    const endpointBounded = completeRetrievalGraph(entities.slice(0, 79), [
      { source: 'E0', target: 'extra-1' },
      { source: 'E0', target: 'extra-2' },
    ])
    expect(endpointBounded.entities).toHaveLength(80)
    expect(endpointBounded.limited).toBe(true)
  })
  it('distinguishes historical clipping, upstream budgets, and text-only truncation', () => {
    const entities = [{ id: 'E' }]
    const graph = completeRetrievalGraph(entities, [])
    expect(
      retrievalNotices(
        { original_counts: { entities: 20 }, truncated: true },
        entities,
        [],
        graph,
      ).join(''),
    ).toContain('旧记录')
    expect(
      retrievalNotices(
        { graph_limits: { entities: 80 }, original_counts: { entities: 90 } },
        entities,
        [],
        graph,
      ).join(''),
    ).toContain('保存上限')
    expect(
      retrievalNotices(
        { processing_info: { total_entities_found: 40, entities_after_truncation: 20 } },
        entities,
        [],
        graph,
      ).join(''),
    ).toContain('文本预算')
    expect(retrievalNotices({ truncated: true }, entities, [], graph).join('')).toContain(
      '不代表图中实体被隐藏',
    )
  })
  it('focuses a cited hit entity over an unrelated node with more connections', () => {
    const entities = [
      { id: 'separator', name: '稳态无反应分离器', source_ids: ['unselected'] },
      { id: 'energy', name: '稳态能量守恒', source_ids: ['heat-hit'] },
      { id: 'fraction', name: '质量分数', source_ids: ['mix-hit'] },
      { id: 'heat', name: '简化热负荷', source_ids: [] },
    ]
    const relationships = [
      { source: 'separator', target: 'energy' },
      { source: 'separator', target: 'fraction' },
      { source: 'separator', target: 'heat' },
    ]
    const before = graphLayout(entities, relationships)
    expect(
      defaultEntityIndex(
        entities,
        relationships,
        [{ chunk_id: 'heat-hit' }, { chunk_id: 'mix-hit' }],
        ['heat-hit'],
        ['能量守恒'],
      ),
    ).toBe(1)
    expect(graphLayout(entities, relationships)).toEqual(before)
  })
  it('prefers visible real connections and does not treat unrelated graph sources as query hits', () => {
    const entities = [
      { id: 'unlinked', name: '知识孤点', source_ids: ['hit'] },
      { id: 'A', name: '质量分数', source_ids: ['graph-only'] },
      { id: 'B', name: '稳态能量守恒', source_ids: [] },
    ]
    const relationships = [{ source: 'A', target: 'B' }]
    expect(
      defaultEntityIndex(
        entities,
        relationships,
        [{ chunk_id: 'hit' }],
        ['hit', 'graph-only'],
        ['能量守恒'],
      ),
    ).toBe(2)
    expect(defaultEntityIndex(entities, [], [{ chunk_id: 'hit' }], ['hit'])).toBe(0)
  })
  it('uses actual keywords and deterministic tie breaking when no source overlap exists', () => {
    const entities = [
      { id: 'a', name: '分离器' },
      { id: 'b', name: '质量分数' },
    ]
    const relationships = [
      { source: 'a', target: 'b' },
      { source: 'a', target: 'missing' },
    ]
    expect(defaultEntityIndex(entities, relationships, [], [], ['质量分数'])).toBe(1)
    expect(defaultEntityIndex(entities, relationships, [], [], [], '请检索质量分数定义')).toBe(1)
    expect(defaultEntityIndex(entities, relationships, [])).toBe(0)
    expect(defaultEntityIndex([], [], [])).toBe(0)
  })
  it('does not promote graph-associated sources to query hits or invent scores', () => {
    const value = retrievalFor({
      call_id: 'c1',
      step_id: 's1',
      tool_name: 'search_knowledge',
      status: 'succeeded',
      output: {
        hits: [{ chunk_id: 'hit', text: '命中原文' }],
        retrieval: {
          mode: 'mix',
          entities: [{ id: 'E', source_ids: ['indexed'] }],
          graph_sources: [{ chunk_id: 'indexed', text: '索引关联原文' }],
        },
      },
    })
    expect(value.hits.map((item) => item.chunk_id)).toEqual(['hit'])
    expect(value.sources.map((item) => item.chunk_id)).toEqual(['indexed'])
    expect(value.hits[0]?.score).toBeUndefined()
  })
  it('only draws relationships with real returned endpoints', () => {
    const result = graphLayout(
      [
        { id: 'A', name: '流量' },
        { id: 'B', name: '热负荷' },
      ],
      [
        { source: 'A', target: 'B' },
        { source: 'A', target: 'missing' },
        { target: 'A' },
        { source: 'B', target: 'B' },
      ],
    )
    expect(result.nodes).toHaveLength(2)
    expect(result.edges).toHaveLength(1)
    expect(result.edges[0]?.from.id).toBe('A')
  })
  it('keeps circles apart and preserves every returned entity and relationship', () => {
    const entities = Array.from({ length: 14 }, (_, index) => ({
      id: String(index),
      name: `完整实体名称${index}`,
    }))
    const edges = [
      { source: '0', target: '1' },
      { source: '0', target: '2' },
      { source: '1', target: '2' },
      { source: '10', target: '11' },
    ]
    const graph = graphLayout(entities, edges)
    expect(graph.nodes).toHaveLength(14)
    expect(graph.edges).toHaveLength(4)
    expect(new Set(graph.nodes.map(({ x, y }) => `${x},${y}`)).size).toBe(14)
    expect(
      graph.nodes.every(({ x, y }) => x > 0 && x < graph.width && y > 0 && y < graph.height),
    ).toBe(true)
    expect(graphLayout(entities, edges)).toEqual(graph)
    for (const a of graph.nodes)
      for (const b of graph.nodes) {
        if (a.index !== b.index)
          expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(2 * graph.nodeRadius)
      }
  })
  it('separates high-level and low-level keywords without guessing their categories', () => {
    const value = retrievalFor({
      call_id: 'c',
      step_id: 's1',
      tool_name: 'search_knowledge',
      status: 'succeeded',
      output: {
        retrieval: { keywords: { high_level: ['能量守恒'], low_level: ['盐水', '比热容'] } },
      },
    })
    expect(value.highLevel).toEqual(['能量守恒'])
    expect(value.lowLevel).toEqual(['盐水', '比热容'])
    expect(value.keywords).toEqual(['能量守恒', '盐水', '比热容'])
  })
  it('avoids chord crossings for the reference graph without removing any relationships', () => {
    const graph = graphLayout(
      Array.from({ length: 9 }, (_, index) => ({ id: String(index), name: `实体${index}` })),
      [
        [2, 0],
        [0, 4],
        [4, 2],
        [1, 3],
        [7, 8],
        [6, 5],
      ].map(([a, b]) => ({ source: String(a), target: String(b) })),
    )
    expect(graph.edges).toHaveLength(6)
    const orientation = (
      a: { x: number; y: number },
      b: { x: number; y: number },
      c: { x: number; y: number },
    ) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
    for (const a of graph.edges)
      for (const b of graph.edges) {
        if (
          a === b ||
          [a.from.index, a.to.index].some((id) => id === b.from.index || id === b.to.index)
        )
          continue
        const crossing =
          orientation(a.from, a.to, b.from) * orientation(a.from, a.to, b.to) < 0 &&
          orientation(b.from, b.to, a.from) * orientation(b.from, b.to, a.to) < 0
        expect(crossing).toBe(false)
      }
  })
  it('deduplicates SDK source sets and rejects unsafe external links', () => {
    expect(sourceIds({ source_ids: ['a<SEP>b', 'a'], source_id: 'b' })).toEqual(['a', 'b'])
    expect(safeUrl('javascript:alert(1)')).toBe('')
    expect(safeUrl('https://example.com/reference')).toBe('https://example.com/reference')
  })
})
