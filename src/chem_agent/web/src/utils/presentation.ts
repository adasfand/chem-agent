import type { RunResult } from '../types/api'
import { record } from './retrieval'
export const statusLabels: Record<string, string> = {
  running: '执行中',
  completed: '已完成',
  needs_input: '待补充参数',
  no_evidence: '依据不足',
  failed: '执行未完成',
  out_of_scope: '超出适用范围',
  cancelled: '已取消',
  pending: '待执行',
  succeeded: '已完成',
  skipped: '未执行',
  ready: '就绪',
}
export const toolLabels: Record<string, string> = {
  search_knowledge: '知识检索',
  convert_units: '单位换算',
  calc_heat_duty: '显热负荷',
  calc_mass_balance: '混合衡算',
}
export const numberText = (value: number) =>
  new Intl.NumberFormat('zh-CN', { maximumSignificantDigits: 7 }).format(value)
export function timeText(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
export interface Metric {
  label: string
  value: number
  unit: string
  step: string
}
export function resultMetrics(result: RunResult): Metric[] {
  const calls = result.calls.filter((call) => call.status === 'succeeded')
  const calculations = calls.filter((call) =>
    ['calc_heat_duty', 'calc_mass_balance'].includes(call.tool_name),
  )
  const targets = calculations.length
    ? calculations
    : calls.filter((call) => call.tool_name === 'convert_units')
  const metrics: Metric[] = []
  for (const call of targets) {
    const output = call.output ?? {}
    const add = (label: string, value: unknown, unit: string) => {
      if (typeof value === 'number' && Number.isFinite(value))
        metrics.push({ label, value, unit, step: call.step_id })
    }
    if (call.tool_name === 'calc_heat_duty') add('显热负荷', output.heat_duty_kw, 'kW')
    if (call.tool_name === 'calc_mass_balance') {
      add('出口总流量', output.total_flow_kg_h, 'kg/h')
      add(
        '组分质量分数',
        typeof output.mass_fraction === 'number' ? output.mass_fraction * 100 : null,
        '%',
      )
      add('组分流量', output.component_flow_kg_h, 'kg/h')
    }
    if (call.tool_name === 'convert_units')
      add('单位换算结果', output.value, String(output.unit ?? ''))
  }
  return metrics
}
export function assumptions(result: RunResult): string[] {
  return [
    ...new Set(
      result.calls
        .filter((call) => call.status === 'succeeded')
        .flatMap((call) => (Array.isArray(call.output?.assumptions) ? call.output.assumptions : []))
        .filter((item): item is string => typeof item === 'string'),
    ),
  ]
}
export function calculationInputs(result: RunResult) {
  return result.calls.flatMap((call) => {
    if (call.status !== 'succeeded') return []
    if (!['calc_heat_duty', 'calc_mass_balance', 'convert_units'].includes(call.tool_name))
      return []
    const inputs = call.arguments ?? record(call.output?.inputs)
    const parameters: { label: string; value: number; unit: string; source: string }[] = []
    const add = (key: string, label: string, value: unknown, unit: string, scale = 1) => {
      if (typeof value !== 'number' || !Number.isFinite(value * scale)) return
      const reference = call.input_refs?.find(
        (item) => item.argument === key && item.value === value,
      )
      const supplied = call.input_provenance?.some(
        (item) => item.argument === key && item.source === 'user' && item.value === value,
      )
      parameters.push({
        label,
        value: value * scale,
        unit,
        source: reference
          ? `前序结果 ${reference.ref}`
          : supplied
            ? '用户提供（后端记录）'
            : '工具实际入参',
      })
    }
    if (call.tool_name === 'calc_heat_duty') {
      add('mass_flow_kg_s', '质量流量', inputs.mass_flow_kg_s, 'kg/s')
      add('specific_heat_kj_kg_k', '质量比热容', inputs.specific_heat_kj_kg_k, 'kJ/(kg·K)')
      add('delta_t_k', '温差', inputs.delta_t_k, 'K')
    } else if (call.tool_name === 'calc_mass_balance' && Array.isArray(inputs.streams)) {
      inputs.streams.forEach((item, index) => {
        const stream = record(item)
        add(`streams[${index}].flow_kg_h`, `流股 ${index + 1} · 质量流量`, stream.flow_kg_h, 'kg/h')
        add(
          `streams[${index}].mass_fraction`,
          `流股 ${index + 1} · 质量分数`,
          stream.mass_fraction,
          '%',
          100,
        )
      })
    } else if (call.tool_name === 'convert_units') {
      add(
        'value',
        '换算前数值',
        inputs.value,
        typeof inputs.from_unit === 'string' ? inputs.from_unit : '',
      )
    }
    return parameters.length
      ? [{ id: call.call_id, step: call.step_id, title: toolLabels[call.tool_name]!, parameters }]
      : []
  })
}
