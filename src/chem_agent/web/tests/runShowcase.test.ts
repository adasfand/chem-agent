import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { RunResult, ToolCall } from '../src/types/api'
import type { RetrievalRecord } from '../src/utils/retrieval'
import {
  citationEvidence,
  executionNetwork,
  graphLabelIds,
  runGraph,
  runQueries,
} from '../src/utils/runShowcase'
import { resultMetrics } from '../src/utils/presentation'

function result(calls: ToolCall[] = []): RunResult {
  return {
    status: 'completed',
    question: '验证',
    answer: '999 kW 不作为计算结果',
    started_at: '',
    calls,
    plan: [],
    evidence: [],
    citations: [],
  }
}
function call(step: string, status: ToolCall['status'] = 'succeeded'): ToolCall {
  return {
    call_id: `call-${step}`,
    step_id: step,
    tool_name: 'convert_units',
    status,
    output: { value: 1 },
  }
}

describe('run presentation preserves recorded evidence', () => {
  it('hides colliding labels while preserving the selected label and all nodes', () => {
    const nodes = [
      { id: 'a', name: '重叠实体甲', degree: 10, x: 100, y: 100, radius: 8 },
      { id: 'b', name: '重叠实体乙', degree: 1, x: 105, y: 100, radius: 8 },
      { id: 'c', name: '远处实体', degree: 2, x: 400, y: 100, radius: 8 },
    ]
    const before = JSON.stringify(nodes)
    expect([...graphLabelIds(nodes, 'b', 1, 12, 18)]).toEqual(['b', 'c'])
    expect(JSON.stringify(nodes)).toBe(before)
  })
  it('normalizes aliases, preserves provenance, and draws only returned endpoints', () => {
    const entities: RetrievalRecord[] = [
      { id: 'A', name: '质量流量', source_ids: ['h1'] },
      { id: 'B', entity_name: '热负荷' },
    ]
    const relationships: RetrievalRecord[] = [
      { src_id: '质量流量', tgt_id: 'B', source_ids: ['h1'], description: '真实关系' },
      { source: 'A', target: 'missing' },
    ]
    const before = JSON.stringify({ entities, relationships })
    const graph = runGraph(entities, relationships)
    expect(graph.nodes.map((node) => node.id)).toEqual(['A', 'B'])
    expect(graph.edges).toHaveLength(1)
    expect(graph.edges[0]?.data.source_ids).toEqual(['h1'])
    expect(graph.omitted).toBe(1)
    expect(graph.nodes[0]?.degree).toBe(1)
    expect(JSON.stringify({ entities, relationships })).toBe(before)
    expect(runGraph(entities, relationships)).toEqual(graph)
  })
  it('never creates a knowledge graph for lexical hits or failed retrieval', () => {
    const value = result([
      {
        ...call('s1'),
        tool_name: 'search_knowledge',
        output: { hits: [{ chunk_id: 'h', text: '原文' }], retrieval: { mode: 'lexical' } },
      },
      {
        ...call('s2', 'failed'),
        tool_name: 'search_knowledge',
        output: { retrieval: { entities: [{ id: 'fake' }] } },
      },
    ])
    const queries = runQueries(value)
    expect(queries).toHaveLength(1)
    expect(queries[0]?.mode).toBe('lexical')
    expect(runGraph(queries[0]!.entities, queries[0]!.relationships).nodes).toEqual([])
  })
  it('does not infer sequential edges and separates dependencies from actual references', () => {
    const value = result([
      call('s1'),
      { ...call('s2'), input_refs: [{ ref: 's1.value', argument: 'value', value: 1 }] },
      call('s3'),
    ])
    value.plan = [
      {
        step_id: 's1',
        tool_name: 'convert_units',
        goal: '换算',
        depends_on: [],
        status: 'succeeded',
      },
      {
        step_id: 's2',
        tool_name: 'convert_units',
        goal: '继续换算',
        depends_on: ['s1'],
        status: 'succeeded',
      },
      {
        step_id: 's3',
        tool_name: 'convert_units',
        goal: '独立换算',
        depends_on: [],
        status: 'succeeded',
      },
    ]
    const network = executionNetwork(value)
    expect(network.edges).toHaveLength(1)
    expect(network.edges[0]).toMatchObject({ from: 's1', to: 's2', planned: true })
    expect(network.referenceCount).toBe(1)
    expect(network.nodes[2]?.layer).toBe(0)
    value.calls[1]!.input_refs = []
    expect(executionNetwork(value).edges[0]?.references).toEqual([])
  })
  it('does not draw references to future, failed, or unknown calls', () => {
    const value = result([
      call('s1', 'failed'),
      {
        ...call('s2'),
        input_refs: ['s1.value', 's3.value', 'unknown.value', 's2.value'].map((ref) => ({
          ref,
          argument: 'value',
          value: 1,
        })),
      },
      call('s3'),
    ])
    expect(executionNetwork(value).referenceCount).toBe(0)
    expect(executionNetwork(value).edges).toEqual([])
  })
  it('retains retries and the latest failure without changing the recorded status', () => {
    const value = result([call('s1'), { ...call('s1', 'failed'), call_id: 'retry' }])
    value.status = 'failed'
    value.plan = [
      {
        step_id: 's1',
        tool_name: 'convert_units',
        goal: '换算',
        depends_on: [],
        status: 'succeeded',
      },
    ]
    expect(executionNetwork(value).nodes[0]?.status).toBe('failed')
    expect(executionNetwork(value).nodes[0]?.calls).toHaveLength(2)
  })
  it('stays bounded for malformed cyclic historical plans', () => {
    const value = result()
    value.plan = ['s1', 's2'].map((id, index) => ({
      step_id: id,
      goal: id,
      tool_name: 'convert_units',
      depends_on: [index ? 's1' : 's2', 'unknown'],
      status: 'pending',
    }))
    const graph = executionNetwork(value)
    expect(graph.edges).toHaveLength(2)
    expect(graph.nodes.every((node) => Number.isFinite(node.x) && Number.isFinite(node.y))).toBe(
      true,
    )
  })
  it('keeps actual citations and context matches separate from graph associations', () => {
    const value = result()
    value.evidence = [
      { chunk_id: 'h1', doc_id: 'doc1', title: '原文', text: '证据', source: 'source' },
      { chunk_id: 'h2', doc_id: 'doc2', title: '未引用', text: '', source: '' },
    ]
    value.citations = ['h1', 'graph-only']
    value.context_evidence = [
      { chunk_id: 'h1', title: '原文', request_indices: [] },
      { chunk_id: 'h2', title: '未引用', request_indices: [2] },
    ]
    expect(citationEvidence(value).map(({ cited, inContext }) => ({ cited, inContext }))).toEqual([
      { cited: true, inContext: false },
      { cited: false, inContext: true },
    ])
    value.mode = 'offline_smoke'
    expect(citationEvidence(value).every((item) => !item.inContext)).toBe(true)
  })
  it('shows nine steps, seven references, and unchanged values from the saved real nine-tool run', () => {
    const path = new URL(
      '../../../../docs/validation/acceptance-20261015/20261015T151626-b1dd6937d3.json',
      import.meta.url,
    )
    const value = JSON.parse(readFileSync(path, 'utf8')) as RunResult
    const before = JSON.stringify(value)
    const network = executionNetwork(value)
    const queries = runQueries(value)
    expect(network.nodes).toHaveLength(9)
    expect(network.referenceCount).toBe(7)
    expect(network.nodes.every((node) => node.status === 'succeeded')).toBe(true)
    expect(queries).toHaveLength(1)
    expect(queries[0]?.entities).toHaveLength(5)
    expect(resultMetrics(value).find((metric) => metric.unit === 'kW')?.value).toBeCloseTo(
      23.22222222222222,
      10,
    )
    expect(citationEvidence(value).filter((item) => item.cited)).toHaveLength(3)
    expect(JSON.stringify(value)).toBe(before)
  })
})
