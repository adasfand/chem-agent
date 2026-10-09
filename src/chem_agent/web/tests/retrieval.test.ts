import { describe, expect, it } from 'vitest'
import { graphLayout, retrievalFor, sourceIds, safeUrl } from '../src/utils/retrieval'
describe('retrieval provenance', () => {
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
