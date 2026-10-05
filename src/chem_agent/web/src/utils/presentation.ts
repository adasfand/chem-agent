import type { RunResult } from '../types/api'
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
