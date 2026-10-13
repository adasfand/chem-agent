import { describe, expect, it } from 'vitest'
import {
  auditMetrics,
  auditStages,
  auditTimeline,
  durationText,
  emptyPlanText,
  parseToolArguments,
} from '../src/utils/audit'
import type { RunResult } from '../src/types/api'

const result: RunResult = {
  status: 'completed',
  question: 'test',
  answer: '',
  started_at: '2026-10-12T00:00:00Z',
  plan: [],
  calls: [],
  evidence: [],
  citations: [],
}
describe('execution audit', () => {
  it('keeps missing provider usage distinct from measured zero', () => {
    expect(auditMetrics(result).tokens).toBeNull()
    expect(auditMetrics(result).modelCount).toBeNull()
    expect(durationText(undefined)).toBe('未记录')
    expect(durationText(0)).toBe('0 ms')
    expect(
      auditMetrics({ ...result, model_events: [{ usage: { input_tokens: 0, output_tokens: 0 } }] })
        .tokens,
    ).toBe(0)
  })
  it('reports partial usage and only citations backed by returned evidence', () => {
    const metrics = auditMetrics({
      ...result,
      model_events: [{ usage: { input_tokens: 10, output_tokens: 5 } }, { status: 'failed' }],
      evidence: [{ doc_id: 'a', chunk_id: 'hit', title: 'a', text: '', source: '' }],
      citations: ['hit', 'hit', 'unknown'],
    })
    expect(metrics.tokens).toBe(15)
    expect(metrics.usagePartial).toBe(true)
    expect(metrics.citations).toBe(1)
  })
  it('orders observed model and tool events and puts undated records last', () => {
    const entries = auditTimeline({
      ...result,
      model_events: [
        { requested_at: '2026-10-12T00:00:00Z', selected_tools: ['convert_units'] },
        {},
      ],
      calls: [
        {
          call_id: 'c1',
          step_id: 's1',
          tool_name: 'convert_units',
          status: 'succeeded',
          started_at: '2026-10-12T00:00:01Z',
        },
      ],
    })
    expect(entries.map((entry) => entry.id)).toEqual(['model-0', 'c1', 'model-1'])
  })
  it('accepts parameter objects and rejects arrays, scalars and malformed JSON', () => {
    expect(parseToolArguments('{"from_unit":"kg/h"}')).toEqual({ from_unit: 'kg/h' })
    for (const input of ['[]', 'null', '12', '{oops'])
      expect(() => parseToolArguments(input)).toThrow()
  })
  it('describes completed knowledge answers without suggesting missing numerical functionality', () => {
    const stages = auditStages({
      ...result,
      answer: '质量分数为组分质量与总质量之比。',
      plan: [
        {
          step_id: 's1',
          goal: '检索质量分数定义',
          tool_name: 'search_knowledge',
          depends_on: [],
          status: 'succeeded',
        },
      ],
      calls: [{ call_id: 'c1', step_id: 's1', tool_name: 'search_knowledge', status: 'succeeded' }],
      evidence: [
        { doc_id: 'a', chunk_id: 'hit', title: '质量分数', text: '定义原文', source: '本地知识卡' },
      ],
      context_evidence: [{ chunk_id: 'hit', title: '质量分数', request_indices: [2] }],
    })
    expect(stages.find((stage) => stage.title === '计算与工具执行')).toMatchObject({
      label: '本轮未调用',
      state: 'neutral',
    })
    expect(stages.find((stage) => stage.title === '知识进入模型上下文')).toMatchObject({
      label: '已匹配输入',
      state: 'done',
    })
    expect(stages.at(-1)?.label).toBe('已完成')
  })
  it('shows missing parameters as same-conversation continuation rather than missing implementation', () => {
    const waiting = { ...result, status: 'needs_input' as const, answer: '请补充比热。' }
    const stages = auditStages(waiting)
    expect(stages.find((stage) => stage.title === '任务规划')?.label).toBe('待补参')
    expect(stages.find((stage) => stage.title === '计算与工具执行')?.label).toBe('待补参')
    expect(stages.at(-1)?.detail).toContain('当前对话')
    expect(emptyPlanText(waiting)).toContain('同一对话')
  })
  it('does not turn retrieval success or selected tool names into proof of model context', () => {
    const stages = auditStages({
      ...result,
      model_events: [{ selected_tools: ['search_knowledge'], status: 'succeeded' }],
      evidence: [{ doc_id: 'a', chunk_id: 'hit', title: 'a', text: 'text', source: '' }],
    })
    expect(stages.find((stage) => stage.title === '知识进入模型上下文')).toMatchObject({
      state: 'neutral',
      label: '证据未保存',
    })
  })
  it('distinguishes successful retrieval without hits from a failing tool', () => {
    const search = {
      call_id: 'c1',
      step_id: 's1',
      tool_name: 'search_knowledge',
      status: 'succeeded' as const,
    }
    expect(
      auditStages({ ...result, status: 'no_evidence', calls: [search] }).find(
        (stage) => stage.title === '知识检索',
      ),
    ).toMatchObject({ state: 'neutral', label: '未命中' })
    expect(
      auditStages({ ...result, status: 'failed', calls: [{ ...search, status: 'failed' }] }).find(
        (stage) => stage.title === '知识检索',
      ),
    ).toMatchObject({ state: 'failed', label: '调用异常' })
  })
  it('marks offline execution clearly instead of claiming a live model input', () => {
    expect(
      auditStages({
        ...result,
        mode: 'offline_test',
        context_evidence: [{ chunk_id: 'hit', title: '模拟知识', request_indices: [1] }],
      }).find((stage) => stage.title === '知识进入模型上下文'),
    ).toMatchObject({ state: 'neutral', label: '离线流程' })
  })
  it('uses a successful retry for the current stage while preserving failed attempts in the timeline', () => {
    const calls: RunResult['calls'] = [
      { call_id: 'first', step_id: 's1', tool_name: 'convert_units', status: 'failed' },
      { call_id: 'retry', step_id: 's1', tool_name: 'convert_units', status: 'succeeded' },
    ]
    expect(
      auditStages({ ...result, calls }).find((stage) => stage.title === '计算与工具执行'),
    ).toMatchObject({ label: '已执行', state: 'done' })
    expect(auditTimeline({ ...result, calls })).toHaveLength(2)
  })
})
