import { describe, expect, it } from 'vitest'
import {
  assumptions,
  calculationInputs,
  resultMetrics,
  toolAlgorithms,
  toolLabels,
  summaryNumberText,
} from '../src/utils/presentation'
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
    expect(metrics).toEqual([
      {
        label: '混合结果',
        valueLabel: '总流量',
        value: 500,
        unit: 'kg/h',
        step: 's2',
        details: [
          { label: '组分质量分数', value: 1, unit: '%' },
          { label: '组分流量', value: 5, unit: 'kg/h' },
        ],
      },
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
  it('formats compact summaries without rounding the recorded values or losing tiny results', () => {
    const value = (500 / 3600) * 4.18 * 40
    const metrics = resultMetrics(result([call('calc_heat_duty', { heat_duty_kw: value })]))
    expect(summaryNumberText(metrics[0]!.value)).toBe('23.22')
    expect(metrics[0]!.value).toBe(value)
    expect(summaryNumberText(0)).toBe('0')
    expect(summaryNumberText(-46.44444444444444)).toBe('-46.44')
    expect(summaryNumberText(0.00000123456)).toBe('0.000001235')
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
  it('covers nine business tool titles and algorithms without treating control actions as tools', () => {
    expect(Object.keys(toolLabels)).toHaveLength(9)
    expect(Object.keys(toolAlgorithms)).toEqual(Object.keys(toolLabels))
    expect(toolLabels.set_plan).toBeUndefined()
    expect(toolAlgorithms.final_answer).toBeUndefined()
    for (const title of Object.values(toolLabels)) expect(title).not.toMatch(/^calc_/)
  })
  it('renders the five new tool outputs using only their recorded numbers and units', () => {
    const metrics = resultMetrics(
      result([
        call('calc_temperature_change', { delta_t_k: 40 }),
        call('calc_volume_flow', { volume_flow_m3_h: 0.5 }),
        call('calc_split_flow', { branch_flow_kg_h: 150, remainder_flow_kg_h: 350 }),
        call('calc_residence_time', { residence_time_h: 2, residence_time_min: 120 }),
        call('calc_heating_energy', { energy_kwh: 90, energy_kj: 324000 }),
      ]),
    )
    expect(metrics.map(({ value, unit }) => ({ value, unit }))).toEqual([
      { value: 40, unit: 'K' },
      { value: 0.5, unit: 'm³/h' },
      { value: 150, unit: 'kg/h' },
      { value: 2, unit: 'h' },
      { value: 90, unit: 'kWh' },
    ])
    expect(metrics[2]?.details).toEqual([{ label: '第二支路', value: 350, unit: 'kg/h' }])
    expect(metrics[3]?.details).toEqual([{ label: '', value: 120, unit: 'min' }])
    expect(metrics[4]?.details).toEqual([{ label: '', value: 324000, unit: 'kJ' }])
  })
  it('shows actual new-tool inputs and preserves dependency provenance while displaying ratios as percent', () => {
    const temperature = call('calc_temperature_change', { delta_t_k: 40 })
    temperature.arguments = { inlet_temperature_c: 25, outlet_temperature_c: 65 }
    const volume = call('calc_volume_flow', { volume_flow_m3_h: 0.5 })
    volume.arguments = { mass_flow_kg_h: 500, density_kg_m3: 1000 }
    const split = call('calc_split_flow', { branch_flow_kg_h: 150 })
    split.arguments = { total_flow_kg_h: 500, split_fraction: 0.3 }
    split.input_provenance = [{ argument: 'split_fraction', value: 0.3, source: 'user' }]
    const residence = call('calc_residence_time', { residence_time_h: 2 })
    residence.arguments = { vessel_volume_m3: 1, volume_flow_m3_h: 0.5 }
    residence.input_refs = [
      { argument: 'volume_flow_m3_h', value: 0.5, ref: 's4.volume_flow_m3_h', unit: 'm³/h' },
    ]
    const energy = call('calc_heating_energy', { energy_kwh: 90 })
    energy.arguments = { heat_duty_kw: 45, duration_h: 2 }
    const groups = calculationInputs(result([temperature, volume, split, residence, energy]))
    expect(
      groups.map((group) => group.parameters.map(({ value, unit }) => ({ value, unit }))),
    ).toEqual([
      [
        { value: 25, unit: '℃' },
        { value: 65, unit: '℃' },
      ],
      [
        { value: 500, unit: 'kg/h' },
        { value: 1000, unit: 'kg/m³' },
      ],
      [
        { value: 500, unit: 'kg/h' },
        { value: 30, unit: '%' },
      ],
      [
        { value: 1, unit: 'm³' },
        { value: 0.5, unit: 'm³/h' },
      ],
      [
        { value: 45, unit: 'kW' },
        { value: 2, unit: 'h' },
      ],
    ])
    expect(groups[2]?.parameters[1]?.source).toBe('用户提供（后端记录）')
    expect(groups[3]?.parameters[1]?.source).toBe('前序结果 s4.volume_flow_m3_h')
  })
  it('does not calculate missing outputs locally or promote failed new-tool records', () => {
    const energy = call('calc_heating_energy', {})
    energy.arguments = { heat_duty_kw: 45, duration_h: 2 }
    const badVolume = call('calc_volume_flow', { volume_flow_m3_h: 0.5 }, 'failed')
    expect(resultMetrics(result([energy, badVolume]))).toEqual([])
    expect(
      resultMetrics(
        result([
          call('calc_heating_energy', { energy_kwh: '90', energy_kj: Number.POSITIVE_INFINITY }),
        ]),
      ),
    ).toEqual([])
    expect(
      resultMetrics(
        result([
          call('calc_temperature_change', { delta_t_k: -40 }),
          call('calc_split_flow', { branch_flow_kg_h: 0, remainder_flow_kg_h: 500 }),
        ]),
      ).map((metric) => metric.value),
    ).toEqual([-40, 0])
  })
  it('keeps distinct calls separate even when their output numbers are equal', () => {
    const first = call('calc_residence_time', { residence_time_h: 2, residence_time_min: 120 })
    const second = { ...first, call_id: 'another-call', step_id: 's3' }
    const failed = { ...first, call_id: 'failed-call', status: 'failed' as const }
    const metrics = resultMetrics(result([first, second, failed]))
    expect(metrics).toHaveLength(2)
    expect(metrics.map((metric) => metric.step)).toEqual(['s2', 's3'])
    expect(metrics.every((metric) => metric.details?.[0]?.value === 120)).toBe(true)
  })
  it('retains available units and branch identities in incomplete older records', () => {
    const metrics = resultMetrics(
      result([
        call('calc_residence_time', { residence_time_h: Number.NaN, residence_time_min: 120 }),
        call('calc_heating_energy', { energy_kj: -167200 }),
        call('calc_split_flow', { branch_flow_kg_h: '0', remainder_flow_kg_h: 500 }),
        call('calc_mass_balance', { mass_fraction: 0 }),
      ]),
    )
    expect(metrics.map(({ value, unit, valueLabel }) => ({ value, unit, valueLabel }))).toEqual([
      { value: 120, unit: 'min', valueLabel: undefined },
      { value: -167200, unit: 'kJ', valueLabel: undefined },
      { value: 500, unit: 'kg/h', valueLabel: '第二支路' },
      { value: 0, unit: '%', valueLabel: '组分质量分数' },
    ])
    expect(metrics.every((metric) => metric.details === undefined)).toBe(true)
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
