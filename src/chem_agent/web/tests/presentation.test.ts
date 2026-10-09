import { describe, expect, it } from 'vitest'
import { assumptions, calculationInputs, resultMetrics } from '../src/utils/presentation'
import { inlineTokens, markdownBlocks } from '../src/utils/markdown'
import type { RunResult, ToolCall } from '../src/types/api'

function result(calls: ToolCall[], answer = '模型文字中的数字不是工具输出：999 kW'): RunResult {
  return {
    status: 'completed',
    question: '计算',
    answer,
    started_at: '2026-10-03T00:00:00Z',
    plan: [],
    calls,
    evidence: [],
    citations: [],
  }
}

function call(
  tool: string,
  output: ToolCall['output'],
  status: ToolCall['status'] = 'succeeded',
): ToolCall {
  return { call_id: `call-${tool}`, step_id: 's2', tool_name: tool, status, output }
}

describe('observable calculation results', () => {
  it('uses the backend heat result rather than extracting numbers from the answer', () => {
    const value = (1000 / 3600) * 4.18 * 40
    const metrics = resultMetrics(
      result([
        call('convert_units', { value: 1000 / 3600, unit: 'kg/s' }),
        call('calc_heat_duty', { heat_duty_kw: value }),
      ]),
    )
    expect(metrics).toEqual([{ label: '显热负荷', value, unit: 'kW', step: 's2' }])
  })

  it('matches the real mass-balance output keys and displays fractions as percent', () => {
    const metrics = resultMetrics(
      result([
        call('calc_mass_balance', {
          total_flow_kg_h: 500,
          component_flow_kg_h: 5,
          mass_fraction: 0.01,
        }),
      ]),
    )
    expect(metrics.map(({ value, unit }) => ({ value, unit }))).toEqual([
      { value: 500, unit: 'kg/h' },
      { value: 1, unit: '%' },
      { value: 5, unit: 'kg/h' },
    ])
  })

  it('retains successful partial results without promoting a failed call to success', () => {
    const output = result([
      call('convert_units', { value: 0.5, unit: 'kg/s' }),
      call('calc_heat_duty', { heat_duty_kw: 999 }, 'failed'),
    ])
    output.status = 'failed'
    expect(resultMetrics(output)).toEqual([
      { label: '单位换算结果', value: 0.5, unit: 'kg/s', step: 's2' },
    ])
    expect(output.status).toBe('failed')
  })

  it('does not invent metrics from numeric strings or non-finite values', () => {
    expect(
      resultMetrics(
        result([
          call('calc_heat_duty', { heat_duty_kw: '46.44' }),
          call('calc_heat_duty', { heat_duty_kw: Number.NaN }),
          call('calc_heat_duty', { heat_duty_kw: Number.POSITIVE_INFINITY }),
        ]),
      ),
    ).toEqual([])
  })

  it('keeps valid zero and cooling values', () => {
    const metrics = resultMetrics(
      result([
        call('calc_heat_duty', { heat_duty_kw: 0 }),
        call('calc_heat_duty', { heat_duty_kw: -46.44 }),
      ]),
    )
    expect(metrics.map((metric) => metric.value)).toEqual([0, -46.44])
  })

  it('deduplicates assumptions from successful calls only', () => {
    expect(
      assumptions(
        result([
          call('calc_heat_duty', { assumptions: ['单相', '恒比热', 3] }),
          call('calc_heat_duty', { assumptions: ['单相', '无热损失'] }),
          call('calc_heat_duty', { assumptions: ['失败记录中的假设'] }, 'failed'),
        ]),
      ),
    ).toEqual(['单相', '恒比热', '无热损失'])
  })
  it('displays resolved calculation inputs and only recorded matching provenance', () => {
    const heat = call('calc_heat_duty', { heat_duty_kw: 46.444 })
    heat.arguments = { mass_flow_kg_s: 1000 / 3600, specific_heat_kj_kg_k: 4.18, delta_t_k: 40 }
    heat.input_refs = [
      { argument: 'mass_flow_kg_s', ref: 's1.value', value: 1000 / 3600, unit: 'kg/s' },
    ]
    heat.input_provenance = [{ argument: 'specific_heat_kj_kg_k', source: 'user', value: 4.18 }]
    const parameters = calculationInputs(result([heat]))[0]!.parameters
    expect(parameters).toEqual([
      { label: '质量流量', value: 1000 / 3600, unit: 'kg/s', source: '前序结果 s1.value' },
      { label: '质量比热容', value: 4.18, unit: 'kJ/(kg·K)', source: '用户提供（后端记录）' },
      { label: '温差', value: 40, unit: 'K', source: '工具实际入参' },
    ])
    heat.input_provenance[0]!.value = 3
    heat.input_refs[0]!.value = 99
    expect(calculationInputs(result([heat]))[0]!.parameters.map((item) => item.source)).toEqual([
      '工具实际入参',
      '工具实际入参',
      '工具实际入参',
    ])
  })
  it('retains stream order and zero fractions while displaying mass fractions as percent', () => {
    const balance = call('calc_mass_balance', { total_flow_kg_h: 500 })
    balance.arguments = {
      streams: [
        { flow_kg_h: 100, mass_fraction: 0.05 },
        { flow_kg_h: 400, mass_fraction: 0 },
      ],
    }
    const parameters = calculationInputs(result([balance]))[0]!.parameters
    expect(parameters.map(({ value, unit }) => ({ value, unit }))).toEqual([
      { value: 100, unit: 'kg/h' },
      { value: 5, unit: '%' },
      { value: 400, unit: 'kg/h' },
      { value: 0, unit: '%' },
    ])
  })
  it('does not promote requested parameters or failed calls to actual inputs', () => {
    const requested = call('calc_heat_duty', { heat_duty_kw: 999 })
    requested.requested_arguments = {
      mass_flow_kg_s: 1,
      specific_heat_kj_kg_k: 4.18,
      delta_t_k: 40,
    }
    const failed = {
      ...requested,
      status: 'failed' as const,
      arguments: requested.requested_arguments,
    }
    expect(calculationInputs(result([requested, failed]))).toEqual([])
    requested.output = {
      inputs: { mass_flow_kg_s: 0, specific_heat_kj_kg_k: '4.18', delta_t_k: -40 },
    }
    expect(calculationInputs(result([requested]))[0]!.parameters.map((item) => item.value)).toEqual(
      [0, -40],
    )
  })
})

describe('safe readable knowledge text', () => {
  it('preserves heading hierarchy and promotes known answer section labels only', () => {
    expect(markdownBlocks('# 显热\n## 公式\n\n计算输入与方法：\n- 核对单位\n\n来源：')).toEqual([
      { kind: 'heading', text: '显热', level: 1 },
      { kind: 'heading', text: '公式', level: 2 },
      { kind: 'heading', text: '计算输入与方法', level: 1 },
      { kind: 'list', text: '', items: ['核对单位'], ordered: false },
      { kind: 'paragraph', text: '来源：' },
    ])
  })

  it('parses real newlines, headings, lists, quotations and code fences', () => {
    const text =
      '# 显热计算\n\n公式说明\n第二行\n\n- 单相\n- 恒比热\n\n> 来源：自编\n\n```text\nQ = m * cp * dT\n```'
    expect(markdownBlocks(text)).toEqual([
      { kind: 'heading', text: '显热计算', level: 1 },
      { kind: 'paragraph', text: '公式说明\n第二行' },
      { kind: 'list', text: '', items: ['单相', '恒比热'], ordered: false },
      { kind: 'quote', text: '来源：自编' },
      { kind: 'code', text: 'Q = m * cp * dT' },
    ])
  })

  it('supports ordinary bold/code text including letters n and s', () => {
    expect(inlineTokens('结果 **constant** 与 `kg/s`')).toEqual([
      { kind: 'text', text: '结果 ' },
      { kind: 'strong', text: 'constant' },
      { kind: 'text', text: ' 与 ' },
      { kind: 'code', text: 'kg/s' },
    ])
  })

  it('keeps HTML and dangerous links as text tokens rather than executable markup', () => {
    const unsafe = '<script>alert(1)</script> [链接](javascript:alert(1))'
    expect(markdownBlocks(unsafe)).toEqual([{ kind: 'paragraph', text: unsafe }])
    expect(inlineTokens(unsafe)).toEqual([{ kind: 'text', text: unsafe }])
  })

  it('preserves a literal backslash-n inside a formula as text', () => {
    expect(markdownBlocks('符号 \\nu 表示运动黏度')).toEqual([
      { kind: 'paragraph', text: '符号 \\nu 表示运动黏度' },
    ])
  })
})
