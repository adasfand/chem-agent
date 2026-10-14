import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ExecutionAudit from '../src/components/ExecutionAudit.vue'
import { toolLabels } from '../src/utils/presentation'
import {
  auditMetrics,
  auditStages,
  auditTimeline,
  durationText,
  emptyPlanText,
  parseToolArguments,
  auditBatches,
  batchRequestText,
  toolCallBatchText,
  auditBatchMetrics,
  auditErrorText,
} from '../src/utils/audit'
import type { RunResult, ToolBatch } from '../src/types/api'

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
const batch: ToolBatch = {
  batch_id: 'batch-1',
  agent_step: 2,
  model_request_index: 2,
  tool_names: ['search_knowledge', 'calc_mass_balance', 'convert_units', 'calc_heat_duty'],
  call_ids: ['c1', 'c2', 'c3', 'c4'],
  status: 'succeeded',
  execution_mode: 'ordered',
  started_at: '2026-10-14T00:00:00Z',
  latency_ms: 250,
}
describe('execution audit', () => {
  it('renders a ten-step real plan with tool algorithms, dependencies and recorded status', async () => {
    const tools = [...Object.keys(toolLabels), 'calc_heating_energy']
    const planned: RunResult = {
      ...result,
      status: 'running',
      plan: tools.map((tool_name, index) => ({
        step_id: `s${index + 1}`,
        tool_name,
        goal: `任务目标 ${index + 1}`,
        depends_on: index ? [`s${index}`] : [],
        status: 'pending',
      })),
    }
    const html = await renderToString(
      createSSRApp({ render: () => h(ExecutionAudit, { result: planned }) }),
    )
    expect(html).toContain('Step 10')
    expect(html).toContain('任务目标 10')
    expect(html).toContain('温度差值')
    expect(html).toContain('名义停留时间')
    expect(html).toContain('恒定热负荷积分')
    expect(html).toContain('第 9 步 加热能量')
    expect(html).toContain('待执行')
  })
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
  it('keeps one multi-tool response distinct from four actual business calls and their dependencies', () => {
    const calls: RunResult['calls'] = batch.tool_names.map((tool_name, index) => ({
      call_id: `c${index + 1}`,
      step_id: `s${index + 1}`,
      tool_name,
      status: 'succeeded',
      batch_id: batch.batch_id,
      batch_position: index + 1,
      ...(index === 2
        ? {
            input_refs: [
              { ref: 's2.total_mass_flow_kg_h', argument: 'value', value: 500, unit: 'kg/h' },
            ],
          }
        : {}),
    }))
    const view = auditBatches({ ...result, tool_batches: [batch], calls })!
    expect(view).toHaveLength(1)
    expect(view[0]?.actions.map((action) => action.position)).toEqual([1, 2, 3, 4])
    expect(view[0]?.calls.map((call) => call.call_id)).toEqual(['c1', 'c2', 'c3', 'c4'])
    expect(view[0]?.calls[2]?.input_refs?.[0]?.ref).toBe('s2.total_mass_flow_kg_h')
    expect(view[0]?.businessSelections).toBe(4)
    expect(view[0]?.execution_mode).toBe('ordered')
    expect(auditMetrics({ ...result, tool_batches: [batch], calls }).callCount).toBe(4)
    expect(toolCallBatchText({ ...result, tool_batches: [batch] }, calls[2]!)).toBe(
      '第 1 批 · 动作 3',
    )
  })
  it('shows a plan action and business action in the same response without counting the control as a business call', () => {
    const planned = { ...batch, tool_names: ['set_plan', 'search_knowledge'], call_ids: ['c1'] }
    const call: RunResult['calls'][number] = {
      call_id: 'c1',
      step_id: 's1',
      tool_name: 'search_knowledge',
      status: 'succeeded',
      batch_id: 'batch-1',
      batch_position: 2,
    }
    const view = auditBatches({ ...result, tool_batches: [planned], calls: [call] })![0]!
    expect(view.actions[0]?.control).toBe(true)
    expect(view.actions[1]?.control).toBe(false)
    expect(view.businessSelections).toBe(1)
    expect(view.calls).toHaveLength(1)
    expect(view.calls[0]?.batch_position).toBe(2)
  })
  it('preserves failed or cancelled batch status without inventing calls for selected but unexecuted actions', () => {
    for (const status of ['failed', 'cancelled'] as const) {
      const view = auditBatches({
        ...result,
        tool_batches: [{ ...batch, status, error: '已中止', call_ids: ['c1'] }],
        calls: [
          { call_id: 'c1', step_id: 's1', tool_name: 'search_knowledge', status: 'succeeded' },
        ],
      })![0]!
      expect(view.status).toBe(status)
      expect(view.actions).toHaveLength(4)
      expect(view.calls).toHaveLength(1)
      expect(view.error).toBe('已中止')
    }
  })
  it('does not reconstruct batches for older records or assign a model request number when missing', () => {
    expect(auditBatches(result)).toBeNull()
    expect(auditBatches({ ...result, tool_batches: [] })).toEqual([])
    expect(batchRequestText(3)).toBe('模型请求 3')
    for (const missing of [null, undefined, 0, -1, Number.NaN])
      expect(batchRequestText(missing)).toBe('模型请求编号未记录')
    expect(
      auditBatches({ ...result, tool_batches: [{ ...batch, model_request_index: null }] })![0]
        ?.requestText,
    ).toBe('模型请求编号未记录')
    expect(
      toolCallBatchText(result, {
        call_id: 'c',
        step_id: 's',
        tool_name: 'convert_units',
        status: 'succeeded',
      }),
    ).toBeUndefined()
  })
  it('keeps repeated same-name selections and calls separate and only follows explicit batch associations', () => {
    const repeated = {
      ...batch,
      tool_names: ['convert_units', 'convert_units'],
      call_ids: ['c1', 'c2', 'wrong'],
    }
    const view = auditBatches({
      ...result,
      tool_batches: [repeated],
      calls: [
        {
          call_id: 'c1',
          step_id: 's1',
          tool_name: 'convert_units',
          status: 'succeeded',
          batch_id: 'batch-1',
          batch_position: 1,
        },
        {
          call_id: 'c2',
          step_id: 's2',
          tool_name: 'convert_units',
          status: 'succeeded',
          batch_id: 'batch-1',
          batch_position: 2,
        },
        {
          call_id: 'wrong',
          step_id: 's3',
          tool_name: 'convert_units',
          status: 'succeeded',
          batch_id: 'another-batch',
          batch_position: 1,
        },
        { call_id: 'manual', step_id: 's4', tool_name: 'convert_units', status: 'succeeded' },
      ],
    })![0]!
    expect(new Set(view.actions.map((action) => action.key)).size).toBe(2)
    expect(view.calls.map((call) => call.call_id)).toEqual(['c1', 'c2'])
    expect(view.businessSelections).toBe(2)
  })
  it('keeps a failed plan and skipped later actions distinct from successful batch execution', () => {
    const failed: ToolBatch = {
      ...batch,
      status: 'failed',
      tool_names: ['set_plan', 'search_knowledge', 'convert_units', 'calc_heat_duty'],
      call_ids: [],
      error: '计划登记失败，后序动作已跳过。',
      actions: [
        { position: 1, tool_name: 'set_plan', status: 'failed', error: '缺少检索前序依赖。' },
        { position: 2, tool_name: 'search_knowledge', status: 'skipped' },
        { position: 3, tool_name: 'convert_units', status: 'skipped' },
        { position: 4, tool_name: 'calc_heat_duty', status: 'skipped' },
      ],
    }
    const run = { ...result, tool_batches: [failed] }
    expect(auditBatches(run)![0]?.actions.map((action) => action.status)).toEqual([
      'failed',
      'skipped',
      'skipped',
      'skipped',
    ])
    expect(auditBatches(run)![0]?.calls).toEqual([])
    expect(auditBatches(run)![0]?.actions[0]?.error).toBe('缺少检索前序依赖。')
    expect(auditBatchMetrics(run)).toEqual({ selectedMultiple: 1, succeededMultiple: 0 })
  })
  it('shows only recorded dependency adjustments and matches repeated actions by position', () => {
    const updated: ToolBatch = {
      ...batch,
      tool_names: ['set_plan', 'convert_units', 'convert_units'],
      actions: [
        {
          position: 1,
          tool_name: 'set_plan',
          status: 'succeeded',
          dependency_adjustments: [{ step_id: 's2', depends_on_added: ['s1'] }],
        },
        { position: 2, tool_name: 'convert_units', status: 'failed', error: '参数无效。' },
        { position: 3, tool_name: 'convert_units', status: 'cancelled' },
      ],
    }
    const actions = auditBatches({ ...result, tool_batches: [updated] })![0]!.actions
    expect(actions[0]?.dependencyAdjustments).toEqual([{ step_id: 's2', depends_on_added: ['s1'] }])
    expect(actions[1]?.dependencyAdjustments).toEqual([])
    expect(actions.map((action) => action.status)).toEqual(['succeeded', 'failed', 'cancelled'])
    expect(actions[2]?.error).toBeUndefined()
  })
  it('does not infer historical action status from a successful batch or business calls', () => {
    const run = {
      ...result,
      tool_batches: [batch],
      calls: [
        {
          call_id: 'c1',
          step_id: 's1',
          tool_name: 'search_knowledge',
          status: 'succeeded' as const,
        },
      ],
    }
    expect(auditBatches(run)![0]?.actions.every((action) => action.status === undefined)).toBe(true)
    expect(auditBatchMetrics(result)).toBeNull()
    expect(auditBatchMetrics({ ...result, tool_batches: [] })).toEqual({
      selectedMultiple: 0,
      succeededMultiple: 0,
    })
  })
  it('counts completed multi-call batches separately from selection attempts and partial failures', () => {
    const calls: RunResult['calls'] = batch.call_ids.map((call_id, index) => ({
      call_id,
      step_id: `s${index + 1}`,
      tool_name: batch.tool_names[index]!,
      status: 'succeeded',
    }))
    expect(auditBatchMetrics({ ...result, tool_batches: [batch], calls })).toEqual({
      selectedMultiple: 1,
      succeededMultiple: 1,
    })
    for (const status of ['failed', 'cancelled'] as const)
      expect(auditBatchMetrics({ ...result, tool_batches: [{ ...batch, status }], calls })).toEqual(
        { selectedMultiple: 1, succeededMultiple: 0 },
      )
    expect(auditBatchMetrics({ ...result, tool_batches: [batch], calls: [calls[0]!] })).toEqual({
      selectedMultiple: 1,
      succeededMultiple: 0,
    })
  })
  it('formats failure details as readable text without quoted JSON strings', () => {
    expect(auditErrorText('计划登记失败。\n请核对依赖。')).toBe('计划登记失败。\n请核对依赖。')
    expect(auditErrorText({ message: '参数无效。', detail: '需要正数。' })).toBe(
      'message：参数无效。\ndetail：需要正数。',
    )
    expect(auditErrorText(undefined)).toBe('')
  })
})
