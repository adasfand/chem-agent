<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { FlaskConical, UserRound, Copy, Check, Wrench, FileDown, Braces } from '@lucide/vue'
import type { Example, Job } from '../types/api'
import { resultMetrics, assumptions, numberText } from '../utils/presentation'
import { exportUrl } from '../services/api'
import StatusBadge from './StatusBadge.vue'
import MarkdownText from './MarkdownText.vue'
import CalculationInputs from './CalculationInputs.vue'
const props = defineProps<{
  job: Job | null
  loading: boolean
  examples: Example[]
  busy: boolean
}>()
defineEmits<{ example: [question: string]; knowledge: [] }>()
const copied = ref(false)
const copyError = ref('')
const metrics = computed(() => (props.job ? resultMetrics(props.job.result) : []))
const conditions = computed(() => (props.job ? assumptions(props.job.result) : []))
watch(
  () => props.job?.job_id,
  () => {
    copied.value = false
    copyError.value = ''
  },
)
async function copyAnswer() {
  try {
    await navigator.clipboard.writeText(props.job?.result.answer || '')
    copied.value = true
    copyError.value = ''
  } catch {
    copyError.value = '复制未获允许，请选择答复文字复制。'
  }
}
</script>
<template>
  <div class="conversation" :aria-busy="loading">
    <div v-if="loading" class="empty-message" role="status">正在读取任务记录…</div>
    <div v-else-if="!job" class="welcome">
      <h1>化工问题，从这里开始</h1>
      <p class="welcome-copy">
        查阅专业知识，核对单位，完成基础计算。
        <br />
        每一步工具调用和引用依据，都可以回溯。
      </p>
      <div class="example-heading">
        <h2>从一个问题开始</h2>
        <span>选择后可编辑工况</span>
      </div>
      <div class="example-grid">
        <button
          v-for="example in examples.slice(0, 3)"
          :key="example.title"
          class="example-card"
          :disabled="busy"
          @click="$emit('example', example.question)"
        >
          <strong>{{ example.title }}</strong>
          <p>{{ example.question }}</p>
          <span class="example-action">
            填入问题
            <span aria-hidden="true">↗</span>
          </span>
        </button>
      </div>
      <button class="text-button welcome-library" @click="$emit('knowledge')">
        浏览知识资料库
        <span aria-hidden="true">→</span>
      </button>
    </div>
    <template v-else>
      <article class="user-message">
        <span class="message-avatar user-avatar"><UserRound :size="17" /></span>
        <div>
          <span class="message-label">你的问题</span>
          <p>{{ job.result.question }}</p>
          <small v-if="job.result.parent_run_id" class="muted">已关联前轮上下文</small>
        </div>
      </article>
      <article class="assistant-message">
        <span class="message-avatar assistant-avatar"><FlaskConical :size="18" /></span>
        <div class="answer-main">
          <div class="answer-heading">
            <strong>Chem Agent</strong>
            <StatusBadge
              :status="job.result.status"
              :label="job.cancel_requested && !job.finished ? '正在停止' : undefined"
            />
          </div>
          <p v-if="!job.finished" class="running-note" role="status">
            <span class="pulse-dot" />
            {{
              job.cancel_requested
                ? '正在等待当前调用结束…'
                : '正在检索、规划与计算，请在右侧查看执行进度。'
            }}
          </p>
          <p v-if="job.result.status !== 'completed' && metrics.length" class="inline-note">
            以下数值来自已成功步骤，整个任务尚未完成。
          </p>
          <div v-if="metrics.length" class="metric-grid">
            <article v-for="(metric, index) in metrics" :key="index" class="metric-card">
              <span>{{ metric.label }}</span>
              <strong>
                {{ numberText(metric.value) }}
                <small>{{ metric.unit }}</small>
              </strong>
              <span class="metric-source">
                <Wrench :size="12" />
                工具输出 · {{ metric.step }}
              </span>
            </article>
          </div>
          <CalculationInputs :result="job.result" />
          <MarkdownText v-if="job.result.answer" :text="job.result.answer" />
          <p v-else class="empty-message">最终答复将在任务结束后显示。</p>
          <details v-if="conditions.length" class="assumptions">
            <summary>工具适用前提 · {{ conditions.length }}</summary>
            <p class="section-help">以下条件来自工具定义，请核对实际工况是否满足。</p>
            <ul>
              <li v-for="condition in conditions" :key="condition">{{ condition }}</li>
            </ul>
          </details>
          <p v-if="job.result.record_warning" class="inline-note">
            {{ job.result.record_warning }}
          </p>
          <div v-if="job.finished" class="answer-actions">
            <button :disabled="!job.result.answer" @click="copyAnswer">
              <Check v-if="copied" :size="14" />
              <Copy v-else :size="14" />
              {{ copied ? '已复制' : '复制答复' }}
            </button>
            <a :href="exportUrl(job.job_id, 'report.md')" download>
              <FileDown :size="14" />
              下载报告 (.md)
            </a>
            <a :href="exportUrl(job.job_id, 'trace.json')" download>
              <Braces :size="14" />
              下载执行记录 (.json)
            </a>
          </div>
          <p v-if="copyError" class="muted" role="status">{{ copyError }}</p>
          <p class="run-identifiers">
            运行编号
            <code>{{ job.result.run_id || '生成中' }}</code>
          </p>
        </div>
      </article>
    </template>
  </div>
</template>
