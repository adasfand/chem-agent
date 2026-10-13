import type { ModelEvent, RunResult, ToolCall } from '../types/api'

export interface AuditStage {
  title: string
  label: string
  state: 'done' | 'running' | 'waiting' | 'failed' | 'neutral'
  detail: string
}

export function auditStages(result: RunResult): AuditStage[] {
  const running = result.status === 'running'
  const needsInput = result.status === 'needs_input'
  const searchCalls = result.calls.filter((call) => call.tool_name === 'search_knowledge')
  const computationCalls = result.calls.filter((call) => call.tool_name !== 'search_knowledge')
  const context = result.context_evidence?.filter((item) => item.request_indices.length > 0) ?? []
  const stageForCalls = (title: string, calls: ToolCall[], detail: string): AuditStage => {
    if (calls.some((call) => call.status === 'running' || call.status === 'pending'))
      return { title, label: '处理中', state: 'running', detail }
    if (
      calls.some(
        (call, index) =>
          call.status === 'failed' &&
          !calls
            .slice(index + 1)
            .some((later) => later.step_id === call.step_id && later.status === 'succeeded'),
      )
    )
      return { title, label: '调用异常', state: 'failed', detail }
    if (calls.some((call) => call.status === 'succeeded'))
      return { title, label: '已执行', state: 'done', detail }
    return {
      title,
      label: running ? '待执行' : '本轮未调用',
      state: running ? 'waiting' : 'neutral',
      detail,
    }
  }
  const searchStage = stageForCalls('知识检索', searchCalls, `${result.evidence.length} 个返回片段`)
  if (searchStage.state === 'done' && !result.evidence.length) {
    searchStage.label = '未命中'
    searchStage.state = 'neutral'
    searchStage.detail = '检索已执行，本轮未返回匹配知识片段。'
  } else if (!searchCalls.length) {
    searchStage.detail = running ? '检索调用发起后展示实际返回片段。' : '本轮没有知识检索调用记录。'
  }
  const succeededComputations = computationCalls.filter(
    (call) => call.status === 'succeeded',
  ).length
  const computationStage = stageForCalls(
    '计算与工具执行',
    computationCalls,
    `${succeededComputations} 次成功调用`,
  )
  const plannedComputations = result.plan.filter((step) => step.tool_name !== 'search_knowledge')
  if (!computationCalls.length && needsInput) {
    computationStage.label = '待补参'
    computationStage.state = 'waiting'
    computationStage.detail = '补充必要条件后，在同一对话继续计算。'
  } else if (
    !computationCalls.length &&
    !plannedComputations.length &&
    result.status === 'completed'
  ) {
    computationStage.label = '本轮未调用'
    computationStage.detail = '本轮已完成答复，执行记录中没有数值计算步骤。'
  } else if (!computationCalls.length && plannedComputations.length) {
    computationStage.detail = `${plannedComputations.length} 个已规划计算步骤，以实际调用记录为准。`
  }
  const offline = result.mode === 'offline_demo' || result.mode === 'offline_test'
  const contextStage: AuditStage = offline
    ? {
        title: '知识进入模型上下文',
        label: '离线流程',
        state: 'neutral',
        detail: '本轮使用离线流程，不展示真实模型入模结论。',
      }
    : context.length
      ? {
          title: '知识进入模型上下文',
          label: '已匹配输入',
          state: 'done',
          detail: `${context.length} 个原文片段匹配实际模型请求`,
        }
      : !result.evidence.length
        ? {
            title: '知识进入模型上下文',
            label: running ? '待检索' : '无检索片段',
            state: running ? 'waiting' : 'neutral',
            detail: '检索返回原文后核对模型输入。',
          }
        : {
            title: '知识进入模型上下文',
            label: running ? '待匹配' : '证据未保存',
            state: running ? 'waiting' : 'neutral',
            detail: '已有检索片段，本记录未保存原文与模型请求的匹配证据。',
          }
  const planStage: AuditStage = result.plan.length
    ? {
        title: '任务规划',
        label: '已登记',
        state: 'done',
        detail: `${result.plan.length} 个步骤，展示目标、工具及依赖`,
      }
    : {
        title: '任务规划',
        label: needsInput ? '待补参' : running ? '规划中' : '未登记',
        state: needsInput ? 'waiting' : running ? 'running' : 'neutral',
        detail: emptyPlanText(result),
      }
  const answerStage: AuditStage = {
    title: '答复与任务状态',
    label:
      result.status === 'completed'
        ? '已完成'
        : needsInput
          ? '待补参'
          : running
            ? '处理中'
            : result.status === 'no_evidence'
              ? '需补充依据'
              : result.status === 'out_of_scope'
                ? '超出范围'
                : result.status === 'cancelled'
                  ? '已取消'
                  : '执行未完成',
    state:
      result.status === 'completed'
        ? 'done'
        : needsInput || result.status === 'no_evidence'
          ? 'waiting'
          : running
            ? 'running'
            : result.status === 'failed'
              ? 'failed'
              : 'neutral',
    detail: needsInput
      ? '已给出补充参数提示；在当前对话继续提问。'
      : result.status === 'completed'
        ? '查看答复、引用来源及工具结果。'
        : running
          ? '最终状态随实际执行进度更新。'
          : '查看本轮答复中的处理结果与提示。',
  }
  return [
    {
      title: '任务输入',
      label: result.question.trim() ? '已接收' : '待输入',
      state: result.question.trim() ? 'done' : 'waiting',
      detail: '本轮问题与已知条件',
    },
    planStage,
    searchStage,
    contextStage,
    computationStage,
    answerStage,
  ]
}

export function emptyPlanText(result: RunResult): string {
  if (result.status === 'needs_input') return '本轮等待必要条件；在同一对话补充后继续处理。'
  if (result.status === 'running') return '等待登记步骤；实际发起的动作会显示在执行时间线。'
  if (result.status === 'cancelled') return '本轮已取消，没有登记分步计划。'
  return '本轮没有登记分步计划，实际操作见执行时间线。'
}

export function durationText(ms: number | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '未记录'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`
}
export function auditMetrics(result: RunResult) {
  const events = result.model_events
  const knownUsage = (events ?? []).filter((event) =>
    [event.usage?.input_tokens, event.usage?.output_tokens].every(
      (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0,
    ),
  )
  const tokens = knownUsage.length
    ? knownUsage.reduce(
        (sum, event) => sum + event.usage!.input_tokens! + event.usage!.output_tokens!,
        0,
      )
    : null
  const evidenceIds = new Set(result.evidence.map((hit) => hit.chunk_id))
  return {
    modelCount: events?.length ?? null,
    tokens,
    usagePartial: knownUsage.length < (events?.length ?? 0),
    succeeded: result.calls.filter((call) => call.status === 'succeeded').length,
    callCount: result.calls.length,
    citations: new Set(result.citations.filter((id) => evidenceIds.has(id))).size,
    evidenceCount: evidenceIds.size,
  }
}
export type AuditEntry =
  | { id: string; kind: 'model'; timestamp?: string; model: ModelEvent; index: number }
  | { id: string; kind: 'tool'; timestamp?: string; call: ToolCall; index: number }
export function auditTimeline(result: RunResult): AuditEntry[] {
  const entries: AuditEntry[] = [
    ...(result.model_events ?? []).map((model, index) => ({
      id: `model-${index}`,
      kind: 'model' as const,
      timestamp: model.requested_at,
      model,
      index,
    })),
    ...result.calls.map((call, index) => ({
      id: call.call_id,
      kind: 'tool' as const,
      timestamp: call.started_at,
      call,
      index,
    })),
  ]
  const time = (entry: AuditEntry) => {
    const timestamp = Date.parse(entry.timestamp ?? '')
    return Number.isFinite(timestamp) ? timestamp : Infinity
  }
  return entries.sort((a, b) => time(a) - time(b))
}
export function parseToolArguments(text: string): Record<string, import('../types/api').JsonValue> {
  const value: unknown = JSON.parse(text)
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('请输入 JSON 参数对象。')
  if (text.length > 12_000) throw new Error('参数过长，请控制在 12000 字以内。')
  return value as Record<string, import('../types/api').JsonValue>
}
