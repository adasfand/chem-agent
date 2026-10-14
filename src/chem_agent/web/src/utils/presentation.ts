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
  calc_temperature_change: '温差计算',
  calc_volume_flow: '体积流量',
  calc_split_flow: '流量分配',
  calc_residence_time: '停留时间',
  calc_heating_energy: '加热能量',
}
export const toolAlgorithms: Record<string, string> = {
  search_knowledge: '专业知识相关检索',
  convert_units: '物理量单位换算',
  calc_heat_duty: '显热计算（Q̇ = ṁ cₚ ΔT）',
  calc_mass_balance: '稳态混合质量与组分守恒',
  calc_temperature_change: '温度差值（ΔT = T出口 − T入口）',
  calc_volume_flow: '质量流量与密度换算（V̇ = ṁ / ρ）',
  calc_split_flow: '按比例分流（F支流 = F总 α）',
  calc_residence_time: '名义停留时间（τ = V / V̇）',
  calc_heating_energy: '恒定热负荷积分（E = Q̇ t）',
}
export const numberText = (value: number) =>
  new Intl.NumberFormat('zh-CN', { maximumSignificantDigits: 7 }).format(value)
export const summaryNumberText = (value: number) =>
  new Intl.NumberFormat('zh-CN', { maximumSignificantDigits: 4 }).format(value)
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
  valueLabel?: string
  details?: { label: string; value: number; unit: string }[]
}
export function resultMetrics(result: RunResult): Metric[] {
  const calls = result.calls.filter((call) => call.status === 'succeeded')
  const calculations = calls.filter(
    (call) => Object.hasOwn(toolAlgorithms, call.tool_name) && call.tool_name.startsWith('calc_'),
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
    const addGroup = (label: string, values: { label: string; value: unknown; unit: string }[]) => {
      const valid = values.filter(
        (item): item is { label: string; value: number; unit: string } =>
          typeof item.value === 'number' && Number.isFinite(item.value),
      )
      const [primary, ...details] = valid
      if (!primary) return
      metrics.push({
        label,
        value: primary.value,
        unit: primary.unit,
        step: call.step_id,
        ...(primary.label ? { valueLabel: primary.label } : {}),
        ...(details.length ? { details } : {}),
      })
    }
    if (call.tool_name === 'calc_heat_duty') add('显热负荷', output.heat_duty_kw, 'kW')
    if (call.tool_name === 'calc_mass_balance') {
      addGroup('混合结果', [
        { label: '总流量', value: output.total_flow_kg_h, unit: 'kg/h' },
        {
          label: '组分质量分数',
          value: typeof output.mass_fraction === 'number' ? output.mass_fraction * 100 : null,
          unit: '%',
        },
        { label: '组分流量', value: output.component_flow_kg_h, unit: 'kg/h' },
      ])
    }
    if (call.tool_name === 'convert_units')
      add('单位换算结果', output.value, String(output.unit ?? ''))
    if (call.tool_name === 'calc_temperature_change') add('温差', output.delta_t_k, 'K')
    if (call.tool_name === 'calc_volume_flow') add('体积流量', output.volume_flow_m3_h, 'm³/h')
    if (call.tool_name === 'calc_split_flow') {
      addGroup('两路分流', [
        { label: '第一支路', value: output.branch_flow_kg_h, unit: 'kg/h' },
        { label: '第二支路', value: output.remainder_flow_kg_h, unit: 'kg/h' },
      ])
    }
    if (call.tool_name === 'calc_residence_time') {
      addGroup('名义停留时间', [
        { label: '', value: output.residence_time_h, unit: 'h' },
        { label: '', value: output.residence_time_min, unit: 'min' },
      ])
    }
    if (call.tool_name === 'calc_heating_energy') {
      addGroup('传热量', [
        { label: '', value: output.energy_kwh, unit: 'kWh' },
        { label: '', value: output.energy_kj, unit: 'kJ' },
      ])
    }
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
    if (!Object.hasOwn(toolAlgorithms, call.tool_name) || call.tool_name === 'search_knowledge')
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
    } else if (call.tool_name === 'calc_temperature_change') {
      add('inlet_temperature_c', '入口温度', inputs.inlet_temperature_c, '℃')
      add('outlet_temperature_c', '出口温度', inputs.outlet_temperature_c, '℃')
    } else if (call.tool_name === 'calc_volume_flow') {
      add('mass_flow_kg_h', '质量流量', inputs.mass_flow_kg_h, 'kg/h')
      add('density_kg_m3', '密度', inputs.density_kg_m3, 'kg/m³')
    } else if (call.tool_name === 'calc_split_flow') {
      add('total_flow_kg_h', '总质量流量', inputs.total_flow_kg_h, 'kg/h')
      add('split_fraction', '分流比例', inputs.split_fraction, '%', 100)
    } else if (call.tool_name === 'calc_residence_time') {
      add('vessel_volume_m3', '容器有效体积', inputs.vessel_volume_m3, 'm³')
      add('volume_flow_m3_h', '体积流量', inputs.volume_flow_m3_h, 'm³/h')
    } else if (call.tool_name === 'calc_heating_energy') {
      add('heat_duty_kw', '热负荷', inputs.heat_duty_kw, 'kW')
      add('duration_h', '持续时间', inputs.duration_h, 'h')
    }
    return parameters.length
      ? [{ id: call.call_id, step: call.step_id, title: toolLabels[call.tool_name]!, parameters }]
      : []
  })
}
