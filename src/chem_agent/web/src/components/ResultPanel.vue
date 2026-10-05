<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { FileDown, Braces, Check, Layers3, BookOpen } from '@lucide/vue'
import type { Job } from '../types/api'
import { resultMetrics, assumptions, numberText } from '../utils/presentation'
import { exportUrl } from '../services/api'
import StatusBadge from './StatusBadge.vue'
import MarkdownText from './MarkdownText.vue'
import ExecutionTrace from './ExecutionTrace.vue'
import EvidencePanel from './EvidencePanel.vue'
const props = defineProps<{ job: Job | null; loading: boolean }>()
defineEmits<{ knowledge: [id: string] }>()
const tab = ref('answer')
const body = ref<HTMLElement>()
watch([() => props.job?.job_id, tab], async () => {
  await nextTick()
  body.value?.scrollTo({ top: 0 })
})
const tabs = [
  { id: 'answer', label: '计算与结论', icon: Check },
  { id: 'process', label: '执行过程', icon: Layers3 },
  { id: 'evidence', label: '知识依据', icon: BookOpen },
]
const metrics = computed(() => (props.job ? resultMetrics(props.job.result) : []))
const conditions = computed(() => (props.job ? assumptions(props.job.result) : []))
watch(
  () => props.job?.job_id,
  () => {
    tab.value = 'answer'
  },
)
function tabKey(event: KeyboardEvent, index: number) {
  const key = event.key
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(key)) return
  event.preventDefault()
  const next =
    key === 'Home'
      ? 0
      : key === 'End'
        ? tabs.length - 1
        : (index + (key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
  tab.value = tabs[next]!.id
  ;(event.currentTarget as HTMLElement).parentElement?.querySelectorAll('button')[next]?.focus()
}
</script>
<template>
  <section class="result-panel panel" aria-labelledby="result-title">
    <div class="panel-heading">
      <h2 id="result-title">计算记录</h2>
      <StatusBadge
        :status="job?.result.status || 'ready'"
        :label="job?.cancel_requested && !job.finished ? '正在停止' : undefined"
      />
    </div>
    <div class="result-tabs" role="tablist" aria-label="结果视图">
      <button
        v-for="(item, index) in tabs"
        :id="`tab-${item.id}`"
        :key="item.id"
        role="tab"
        :aria-selected="tab === item.id"
        :tabindex="tab === item.id ? 0 : -1"
        @keydown="tabKey($event, index)"
        :aria-controls="`panel-${item.id}`"
        :class="{ active: tab === item.id }"
        @click="tab = item.id"
      >
        <component :is="item.icon" :size="15" />
        {{ item.label }}
        <span v-if="job && item.id === 'evidence'">{{ job.result.evidence.length }}</span>
      </button>
    </div>
    <div
      :id="`panel-${tab}`"
      ref="body"
      class="result-body"
      role="tabpanel"
      :aria-labelledby="`tab-${tab}`"
      :aria-busy="loading || (!!job && !job.finished)"
    >
      <div v-if="loading" class="empty-message">正在读取任务记录…</div>
      <div v-else-if="!job" class="result-empty">
        <div class="empty-introduction">
          <h3>等待任务输入</h3>
          <p>运行任务后，在这里核对数值、计算步骤与知识来源。</p>
        </div>
        <figure class="engineering-example" aria-labelledby="example-caption">
          <figcaption id="example-caption">
            <span>单相显热计算</span>
            <span class="example-label">公式示例</span>
          </figcaption>
          <svg
            class="heat-schematic"
            viewBox="0 0 440 150"
            role="img"
            aria-label="稳态物料进入加热单元，由入口温度 T₁ 加热至出口温度 T₂，热量 Q 输入"
          >
            <path class="process-pipe" d="M35 85H155M285 85H405" />
            <path class="process-arrow" d="m148 80 8 5-8 5m249-10 8 5-8 5" />
            <rect class="heater-vessel" x="156" y="49" width="129" height="72" rx="4" />
            <path class="heater-coil" d="M179 99V71h15v28h15V71h15v28h15V71h15v28h10" />
            <path class="heat-input" d="M220 12V46m-5-7 5 8 5-8" />
            <text x="35" y="66" class="diagram-label">入口 T₁</text>
            <text x="342" y="66" class="diagram-label">出口 T₂</text>
            <text x="236" y="28" class="diagram-heat">Q̇</text>
            <text x="35" y="112" class="diagram-variable">质量流量 ṁ</text>
          </svg>
          <div class="heat-equation" aria-label="热负荷等于质量流量乘以定压比热乘以温差">
            <span>Q̇</span>
            <span class="equation-operator">=</span>
            <span>ṁ</span>
            <span>
              c
              <sub>p</sub>
            </span>
            <span>
              (T
              <sub>2</sub>
              − T
              <sub>1</sub>
              )
            </span>
          </div>
          <dl class="formula-variables">
            <div>
              <dt>ṁ</dt>
              <dd>
                质量流量
                <small>kg/s</small>
              </dd>
            </div>
            <div>
              <dt>
                c
                <sub>p</sub>
              </dt>
              <dd>
                定压比热
                <small>kJ/(kg·K)</small>
              </dd>
            </div>
            <div>
              <dt>ΔT</dt>
              <dd>
                温差
                <small>K 或 ℃</small>
              </dd>
            </div>
          </dl>
          <p class="formula-condition">适用条件：稳态、无相变、忽略热损失，定压比热按常数取值。</p>
        </figure>
        <p class="empty-instruction">填写工况，或选择示例任务。</p>
      </div>
      <template v-else-if="tab === 'answer'">
        <div v-if="!job.finished" class="running-note">
          <span class="pulse-dot" />
          {{
            job.cancel_requested
              ? '已请求停止，正在等待当前调用结束…'
              : '正在规划并执行任务，可切换到执行过程查看进度。'
          }}
        </div>
        <p v-if="job.result.status !== 'completed' && metrics.length" class="inline-note">
          以下是已成功步骤的数值，不代表整个任务已完成。
        </p>
        <div v-if="metrics.length" class="metric-grid">
          <article v-for="(metric, index) in metrics" :key="index" class="metric-card">
            <span>{{ metric.label }}</span>
            <strong>
              {{ numberText(metric.value) }}
              <small>{{ metric.unit }}</small>
            </strong>
            <span class="metric-source">
              <Check :size="12" />
              成功工具输出 · {{ metric.step }}
            </span>
          </article>
        </div>
        <div v-if="job.result.answer" class="answer-content">
          <div class="subheading">任务结论</div>
          <MarkdownText :text="job.result.answer" />
        </div>
        <div v-else class="empty-message">最终答复将在任务结束后显示。</div>
        <div v-if="conditions.length" class="assumptions">
          <h3>计算适用条件</h3>
          <ul>
            <li v-for="condition in conditions" :key="condition">{{ condition }}</li>
          </ul>
        </div>
        <p v-if="job.result.record_warning" class="inline-note">{{ job.result.record_warning }}</p>
        <div class="run-identifiers">
          <span>
            运行编号
            <code>{{ job.result.run_id || '生成中' }}</code>
          </span>
          <span v-if="job.result.parent_run_id">
            关联前轮
            <code>{{ job.result.parent_run_id }}</code>
          </span>
        </div>
      </template>
      <ExecutionTrace v-else-if="tab === 'process'" :result="job.result" />
      <EvidencePanel
        v-else
        :evidence="job.result.evidence"
        :citations="job.result.citations"
        @open="$emit('knowledge', $event)"
      />
    </div>
    <div class="result-footer">
      <span>保留输入、步骤与来源，便于复核</span>
      <div v-if="job?.finished" class="export-actions">
        <a :href="exportUrl(job.job_id, 'report.md')" download>
          <FileDown :size="15" />
          报告
        </a>
        <a :href="exportUrl(job.job_id, 'trace.json')" download>
          <Braces :size="15" />
          记录
        </a>
      </div>
      <span v-else class="export-muted">
        <FileDown :size="14" />
        任务结束后可导出
      </span>
    </div>
  </section>
</template>
