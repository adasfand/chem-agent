<script setup lang="ts">
import { computed } from 'vue'
import { BrainCircuit, Wrench, ArrowDownRight } from '@lucide/vue'
import type { RunResult } from '../types/api'
import {
  auditMetrics,
  auditStages,
  auditTimeline,
  durationText,
  emptyPlanText,
} from '../utils/audit'
import { toolLabels } from '../utils/presentation'
import StatusBadge from './StatusBadge.vue'
import ExecutionTrace from './ExecutionTrace.vue'

const props = defineProps<{ result: RunResult }>()
const metrics = computed(() => auditMetrics(props.result))
const timeline = computed(() => auditTimeline(props.result))
const contextEvidence = computed(() => props.result.context_evidence ?? [])
const stages = computed(() => auditStages(props.result))
const labels: Record<string, string> = {
  ...toolLabels,
  set_plan: '登记执行计划',
  final_answer: '生成答复',
}
const modeLabels: Record<string, string> = {
  offline_demo: '离线固定流程：工具实际执行，未调用模型。',
  offline_test: '离线测试：模型响应使用测试数据。',
  not_started: '任务未发起模型请求。',
}
const json = (value: unknown) => JSON.stringify(value ?? {}, null, 2)
function dependencyLabel(id: string) {
  const index = props.result.plan.findIndex((step) => step.step_id === id)
  const step = props.result.plan[index]
  return step ? `第 ${index + 1} 步 ${labels[step.tool_name] || step.tool_name}` : id
}
const clock = (value?: string) =>
  value && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
    : '时间未记录'
</script>
<template>
  <section class="execution-audit" aria-label="执行审计">
    <div class="audit-title">
      <div>
        <h3>执行审计</h3>
        <p>问题输入、知识检索、工具选择与结果回用</p>
      </div>
      <StatusBadge :status="result.status" />
    </div>
    <p v-if="result.mode && result.mode !== 'live'" class="audit-notice">
      {{ modeLabels[result.mode] || '记录回放：展示已保存的执行数据。' }}
    </p>
    <section class="audit-stages" aria-label="任务处理阶段">
      <h4>任务处理阶段</h4>
      <ol>
        <li v-for="stage in stages" :key="stage.title" :class="`stage-${stage.state}`">
          <span class="audit-stage-marker" aria-hidden="true" />
          <div>
            <strong>{{ stage.title }}</strong>
            <small>{{ stage.detail }}</small>
          </div>
          <span>{{ stage.label }}</span>
        </li>
      </ol>
      <details v-if="contextEvidence.length" class="audit-context-evidence">
        <summary>查看进入模型上下文的知识来源</summary>
        <ul>
          <li v-for="item in contextEvidence" :key="item.chunk_id">
            <strong>{{ item.title }}</strong>
            <span>匹配模型请求 {{ item.request_indices.join('、') }}</span>
          </li>
        </ul>
      </details>
    </section>
    <dl class="audit-metrics">
      <div>
        <dt>任务耗时</dt>
        <dd>{{ durationText(result.latency_ms) }}</dd>
        <small>{{ result.status === 'running' ? '任务结束后记录' : '从开始到结束' }}</small>
      </div>
      <div>
        <dt>工具成功调用</dt>
        <dd>
          {{ metrics.succeeded }}
          <span>/ {{ metrics.callCount }}</span>
        </dd>
        <small>按实际调用统计</small>
      </div>
      <div>
        <dt>Agent 模型请求</dt>
        <dd>
          {{ metrics.modelCount ?? '未记录' }}
          <span v-if="metrics.modelCount !== null">次</span>
        </dd>
        <small>
          {{
            metrics.tokens === null
              ? 'Token 用量未记录'
              : `${metrics.usagePartial ? '已记录用量' : 'Token 用量'} ${metrics.tokens.toLocaleString()}`
          }}
        </small>
      </div>
      <div>
        <dt>回答引用</dt>
        <dd>
          {{ metrics.citations }}
          <span>/ {{ metrics.evidenceCount }}</span>
        </dd>
        <small>已引用 / 检索命中片段</small>
      </div>
    </dl>
    <section class="audit-plan" aria-label="工具选择计划">
      <h4>
        工具选择计划
        <span>{{ result.plan.length }} 步</span>
      </h4>
      <p v-if="!result.plan.length" class="section-help">{{ emptyPlanText(result) }}</p>
      <ol v-else>
        <li v-for="(step, index) in result.plan" :key="step.step_id">
          <span class="audit-plan-index">{{ index + 1 }}</span>
          <div>
            <strong>{{ step.goal }}</strong>
            <p>{{ labels[step.tool_name] || step.tool_name }}</p>
            <small v-if="step.depends_on.length">
              <ArrowDownRight :size="12" />
              接续 {{ step.depends_on.map(dependencyLabel).join('、') }}
            </small>
          </div>
          <StatusBadge :status="step.status" />
        </li>
      </ol>
    </section>
    <h4 class="audit-timeline-heading">
      执行时间线
      <span>{{ timeline.length }} 条记录</span>
    </h4>
    <p v-if="!timeline.length" class="section-help">
      {{
        result.status === 'running'
          ? '等待模型请求与工具调用记录。'
          : '本轮没有保存模型与工具调用时间线。'
      }}
    </p>
    <ol class="audit-timeline">
      <li v-for="entry in timeline" :key="entry.id" :class="entry.kind">
        <span class="audit-event-icon">
          <BrainCircuit v-if="entry.kind === 'model'" :size="14" />
          <Wrench v-else :size="14" />
        </span>
        <details>
          <summary>
            <div>
              <strong>
                {{
                  entry.kind === 'model'
                    ? `模型请求 ${entry.index + 1}`
                    : labels[entry.call.tool_name] || entry.call.tool_name
                }}
              </strong>
              <span
                v-if="entry.kind === 'model' && entry.model.selected_tools?.length"
                class="audit-action-hint"
              >
                {{ entry.model.selected_tools.map((name) => labels[name] || name).join('、') }}
              </span>
              <small>
                {{ clock(entry.timestamp) }}
                <span>
                  {{
                    durationText(
                      entry.kind === 'model' ? entry.model.latency_ms : entry.call.latency_ms,
                    )
                  }}
                </span>
              </small>
            </div>
            <StatusBadge
              :status="entry.kind === 'model' ? entry.model.status || 'pending' : entry.call.status"
            />
          </summary>
          <template v-if="entry.kind === 'model'">
            <h5>模型返回的动作</h5>
            <p v-if="entry.model.status === 'failed'">本次请求失败，未返回可执行动作。</p>
            <p v-else-if="entry.model.status === 'pending'">等待模型响应。</p>
            <p v-else-if="entry.model.selected_tools === undefined">此记录未保存工具选择信息。</p>
            <p v-else-if="!entry.model.selected_tools.length">返回文本答复</p>
            <div v-else class="audit-tool-tags">
              <span v-for="(name, index) in entry.model.selected_tools" :key="`${name}-${index}`">
                {{ labels[name] || name }}
              </span>
            </div>
            <p class="audit-event-note">
              输入 {{ entry.model.usage?.input_tokens ?? '未记录' }} / 输出
              {{ entry.model.usage?.output_tokens ?? '未记录' }} tokens
            </p>
          </template>
          <template v-else>
            <p>
              {{
                result.plan.find((step) => step.step_id === entry.call.step_id)?.goal ||
                '实际工具调用'
              }}
            </p>
            <h5>输入参数</h5>
            <pre v-if="entry.call.arguments != null">{{ json(entry.call.arguments) }}</pre>
            <p v-else>本次调用尚未形成实际输入参数。</p>
            <div v-if="entry.call.input_refs?.length" class="audit-result-reuse">
              <h5>前序结果回用</h5>
              <dl v-for="(reference, index) in entry.call.input_refs" :key="index">
                <dt>{{ dependencyLabel(reference.ref.split('.')[0] || reference.ref) }}</dt>
                <dd>
                  <code>{{ reference.argument }}</code>
                  = {{ json(reference.value) }} {{ reference.unit || '' }}
                </dd>
                <dd
                  v-if="
                    reference.source_value !== undefined &&
                    (reference.source_value !== reference.value ||
                      reference.source_unit !== reference.unit)
                  "
                  class="audit-reuse-source"
                >
                  原结果：{{ json(reference.source_value) }} {{ reference.source_unit || '' }}
                </dd>
              </dl>
            </div>
            <h5>{{ entry.call.error ? '执行提示' : '返回结果' }}</h5>
            <pre v-if="entry.call.error != null || entry.call.output != null">{{
              json(entry.call.error ?? entry.call.output)
            }}</pre>
            <p v-else>
              {{
                entry.call.status === 'running' || entry.call.status === 'pending'
                  ? '等待工具返回结果。'
                  : '本次调用未保存返回结果。'
              }}
            </p>
          </template>
        </details>
      </li>
    </ol>
    <details class="audit-full-record">
      <summary>查看完整参数与来源记录</summary>
      <ExecutionTrace :result="result" />
    </details>
    <p class="audit-footnote">
      统计范围为 Agent 主流程的模型与业务工具记录。点击时间线条目查看参数和返回值。
    </p>
  </section>
</template>
