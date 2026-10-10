<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { Example, Job } from '../types/api'
import ResultPanel from './ResultPanel.vue'
import MarkdownText from './MarkdownText.vue'

const props = defineProps<{
  job: Job | null
  turns: Job[]
  loading: boolean
  examples: Example[]
  busy: boolean
}>()
defineEmits<{ example: [question: string]; knowledge: []; inspect: [id: string] }>()
const viewport = ref<HTMLElement>()
const visibleTurns = computed(() =>
  props.turns.length ? props.turns : props.job ? [props.job] : [],
)
// If the server has expired older records, retained context still explains the follow-up.
const earlierContext = computed(() => visibleTurns.value[0]?.result.history ?? [])
watch(
  () => visibleTurns.value.at(-1)?.job_id,
  async () => {
    await nextTick()
    viewport.value?.scrollTo({ top: viewport.value.scrollHeight, behavior: 'instant' })
  },
)
</script>
<template>
  <ResultPanel
    v-if="!job"
    :job="null"
    :loading="loading"
    :examples="examples"
    :busy="busy"
    @example="$emit('example', $event)"
    @knowledge="$emit('knowledge')"
  />
  <div v-else ref="viewport" class="conversation" aria-label="当前对话">
    <p v-if="loading" class="empty-message" role="status">正在读取本轮记录…</p>
    <details v-if="earlierContext.length" class="earlier-context">
      <summary>更早的对话上下文（完整执行记录暂不可用）</summary>
      <div v-for="(message, index) in earlierContext" :key="index">
        <strong>{{ message.role === 'user' ? '你的问题' : 'Chem Agent' }}</strong>
        <MarkdownText :text="message.content" />
      </div>
    </details>
    <section v-for="(turn, index) in visibleTurns" :key="turn.job_id" class="conversation-round">
      <div class="round-caption">
        <span>{{ index === 0 && !earlierContext.length ? '首次提问' : '补充与追问' }}</span>
        <button
          type="button"
          class="text-button"
          :disabled="busy && turn.job_id !== job.job_id"
          :aria-pressed="turn.job_id === job.job_id"
          @click="$emit('inspect', turn.job_id)"
        >
          {{ turn.job_id === job.job_id ? '正在查看本轮依据' : '查看本轮依据' }}
        </button>
      </div>
      <ResultPanel :job="turn" :loading="false" :examples="[]" :busy="busy" embedded />
    </section>
    <p class="conversation-help">补充参数会继续当前对话；点击“新建问答”才会开启独立对话。</p>
  </div>
</template>
