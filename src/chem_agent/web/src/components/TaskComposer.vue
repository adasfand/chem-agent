<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ArrowUpRight, ArrowRight, Square, CornerDownLeft, Info } from '@lucide/vue'
import type { Example, Job } from '../types/api'
const props = defineProps<{
  draft: string
  busy: boolean
  running: boolean
  configured: boolean
  connected: boolean
  canSubmit: boolean
  cancelling: boolean
  job: Job | null
  examples: Example[]
}>()
const body = ref<HTMLElement>()
watch(
  () => props.job?.job_id,
  async () => {
    await nextTick()
    body.value?.scrollTo({ top: 0 })
  },
)
const emit = defineEmits<{
  'update:draft': [value: string]
  submit: []
  cancel: []
  example: [question: string]
}>()
function shortcut(event: KeyboardEvent) {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    emit('submit')
  }
}
</script>
<template>
  <section class="composer panel" aria-labelledby="composer-title">
    <div class="panel-heading">
      <h2 id="composer-title">{{ job ? '补充工况' : '任务输入' }}</h2>
    </div>
    <div ref="body" class="composer-body">
      <div v-if="job" class="context-note">
        <span>当前上下文</span>
        <p>{{ job.result.question }}</p>
        <small>补充信息将生成关联的新运行，原记录保留。</small>
      </div>
      <label class="field-label" for="question">
        {{ job ? '补充参数或提出追问' : '问题与已知条件' }}
      </label>
      <div class="question-field">
        <textarea
          id="question"
          :value="draft"
          maxlength="4000"
          :disabled="busy"
          placeholder="例如：某液体流量为 1000 kg/h，从 25℃ 加热到 65℃，比热为 4.18 kJ/(kg·K)，请检索依据并计算热负荷。"
          @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
          @keydown="shortcut"
        />
        <div class="input-meta">
          <span>请说明数值、单位与适用条件</span>
          <span>{{ draft.length }} / 4000</span>
        </div>
      </div>
      <div v-if="!connected" class="inline-note">
        <Info :size="16" />
        <span>后端未连接，请重新连接后继续。</span>
      </div>
      <div v-else-if="!configured" class="inline-note">
        <Info :size="16" />
        <span>配置模型 API 后可运行任务。知识资料库可直接查阅。</span>
      </div>
      <div class="composer-actions">
        <button
          v-if="running"
          class="button stop-button"
          :disabled="cancelling || job?.cancel_requested"
          @click="emit('cancel')"
        >
          <Square :size="15" />
          {{ cancelling || job?.cancel_requested ? '正在停止…' : '停止任务' }}
        </button>
        <button v-else class="button primary" :disabled="!canSubmit" @click="emit('submit')">
          {{ busy ? '正在提交…' : job ? '提交补充信息' : '运行任务' }}
          <ArrowRight :size="17" />
        </button>
        <span class="keyboard-hint">
          <CornerDownLeft :size="13" />
          Ctrl / ⌘ + Enter
        </span>
      </div>
      <div class="examples-heading">
        <span>示例任务</span>
        <small>点击填入，可继续编辑</small>
      </div>
      <div class="example-grid">
        <button
          v-for="example in examples"
          :key="example.title"
          class="example-card"
          :disabled="busy"
          @click="emit('example', example.question)"
        >
          <strong>{{ example.title }}</strong>
          <ArrowUpRight :size="15" />
          <p>{{ example.question }}</p>
        </button>
      </div>
      <p class="scope-note">
        适用于基础知识查询、单位换算、单相显热与稳态混合衡算。计算结果需结合实际工况复核。
      </p>
    </div>
  </section>
</template>
