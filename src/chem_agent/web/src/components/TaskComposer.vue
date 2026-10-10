<script setup lang="ts">
import { ArrowUp, Square, CornerDownLeft } from '@lucide/vue'
import type { Job } from '../types/api'
defineProps<{
  draft: string
  busy: boolean
  running: boolean
  configured: boolean
  connected: boolean
  canSubmit: boolean
  cancelling: boolean
  job: Job | null
}>()
const emit = defineEmits<{ 'update:draft': [value: string]; submit: []; cancel: [] }>()
function shortcut(event: KeyboardEvent) {
  if (!event.isComposing && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    emit('submit')
  }
}
</script>
<template>
  <form class="composer" @submit.prevent="emit('submit')">
    <label class="sr-only" for="question">
      {{ job ? '补充参数或追问' : '输入化工问题与已知条件' }}
    </label>
    <div class="question-field">
      <textarea
        id="question"
        :value="draft"
        maxlength="4000"
        :disabled="busy"
        :placeholder="job ? '补充参数，或继续追问当前任务…' : '描述你的问题、工况与已知条件…'"
        @input="emit('update:draft', ($event.target as HTMLTextAreaElement).value)"
        @keydown="shortcut"
      />
      <div class="composer-actions">
        <span class="composer-mode">{{ job ? '继续当前对话，沿用已有条件' : '新问答' }}</span>
        <span class="input-count">{{ draft.length }} / 4000 字</span>
        <button
          v-if="running"
          type="button"
          class="send-button stop-button"
          :disabled="cancelling || job?.cancel_requested"
          @click="emit('cancel')"
        >
          <Square :size="15" />
          {{ cancelling || job?.cancel_requested ? '等待停止' : '停止任务' }}
        </button>
        <button
          v-else
          type="submit"
          class="send-button"
          :disabled="!canSubmit"
          :aria-label="busy ? '正在确认提交状态' : job ? '发送追问' : '发送问题'"
        >
          <ArrowUp :size="19" />
          <span>{{ busy ? '确认提交中' : job ? '发送追问' : '发送问题' }}</span>
        </button>
      </div>
    </div>
    <div class="composer-caption">
      <span v-if="!connected">后端未连接，请点击右上角重新连接。</span>
      <span v-else-if="!configured">尚未配置模型 API，可先浏览知识资料。</span>
      <span v-else-if="running">任务执行中，结束后可继续追问，也可点击“停止任务”。</span>
      <span v-else-if="busy">正在确认提交状态，请稍候。</span>
      <span v-else>输入问题和已知条件后可发送；计算参数请注明单位。</span>
      <span class="keyboard-hint">
        <CornerDownLeft :size="12" />
        Ctrl / ⌘ + Enter
      </span>
    </div>
  </form>
</template>
