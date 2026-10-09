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
  it('keeps all returned entities in non-overlapping lanes, including disconnected groups', () => {
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
  })
  it('deduplicates SDK source sets and rejects unsafe external links', () => {
    expect(sourceIds({ source_ids: ['a<SEP>b', 'a'], source_id: 'b' })).toEqual(['a', 'b'])
    expect(safeUrl('javascript:alert(1)')).toBe('')
    expect(safeUrl('https://example.com/reference')).toBe('https://example.com/reference')
  })
})
