import { describe, expect, it } from 'vitest'
import { assumptions, resultMetrics } from '../src/utils/presentation'
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
})

describe('safe readable knowledge text', () => {
  it('parses real newlines, headings, lists, quotations and code fences', () => {
    const text =
      '# 显热计算\n\n公式说明\n第二行\n\n- 单相\n- 恒比热\n\n> 来源：自编\n\n```text\nQ = m * cp * dT\n```'
    expect(markdownBlocks(text)).toEqual([
      { kind: 'heading', text: '显热计算' },
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
