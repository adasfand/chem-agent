<script setup lang="ts">
import { ref, watch } from 'vue'
import { GitBranch, Wrench, BookOpen, ScanText, Search as SearchIcon } from '@lucide/vue'
import type { Bootstrap, Job } from '../types/api'
import ExecutionTrace from './ExecutionTrace.vue'
import EvidencePanel from './EvidencePanel.vue'
import RetrievalPath from './RetrievalPath.vue'
const props = defineProps<{
  job: Job | null
  indexStatus?: Bootstrap['index_status']
  knowledgeCount: number
}>()
defineEmits<{ knowledge: [id: string] }>()
const tab = ref('path')
const tabs = [
  { id: 'path', label: '检索路径', icon: GitBranch },
  { id: 'tools', label: '工具调用', icon: Wrench },
  { id: 'sources', label: '引用依据', icon: BookOpen },
]
watch(
  () => props.job?.job_id,
  () => {
    tab.value = 'path'
  },
)
function key(event: KeyboardEvent, index: number) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? tabs.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
  tab.value = tabs[next]!.id
  ;(event.currentTarget as HTMLElement).parentElement?.querySelectorAll('button')[next]?.focus()
}
</script>
<template>
  <aside class="inspector" aria-label="依据与过程">
    <div class="inspector-heading">
      <ScanText :size="17" />
      <h2>依据与过程</h2>
    </div>
    <div class="inspector-tabs" role="tablist" aria-label="追溯视图">
      <button
        v-for="(item, index) in tabs"
        :id="`tab-${item.id}`"
        :key="item.id"
        role="tab"
        :aria-selected="tab === item.id"
        :aria-controls="`panel-${item.id}`"
        :tabindex="tab === item.id ? 0 : -1"
        :class="{ active: tab === item.id }"
        @click="tab = item.id"
        @keydown="key($event, index)"
      >
        <component :is="item.icon" :size="14" />
        {{ item.label }}
      </button>
    </div>
    <div
      :id="`panel-${tab}`"
      class="inspector-body"
      role="tabpanel"
      :aria-labelledby="`tab-${tab}`"
    >
      <template v-if="!job">
        <div class="inspector-empty">
          <GitBranch :size="22" />
          <h3>让每个结论都有依据</h3>
          <p>任务开始后，这里会展示实际检索记录与工具执行过程。</p>
        </div>
        <div class="workflow-guide">
          <div>
            <SearchIcon />
            <span>
              检索知识
              <small>查询、实体关系与原文</small>
            </span>
          </div>
          <div>
            <Wrench :size="17" />
            <span>
              调用工具
              <small>输入参数与前序结果引用</small>
            </span>
          </div>
          <div>
            <BookOpen :size="17" />
            <span>
              核对来源
              <small>区分检索命中与回答引用</small>
            </span>
          </div>
        </div>
      </template>
      <RetrievalPath v-else-if="tab === 'path'" :result="job.result" />
      <ExecutionTrace v-else-if="tab === 'tools'" :result="job.result" />
      <EvidencePanel
        v-else
        :evidence="job.result.evidence"
        :citations="job.result.citations"
        @open="$emit('knowledge', $event)"
      />
    </div>
    <div class="index-status">
      <div>
        <i :class="{ ready: indexStatus?.state === 'ready' }" />
        <strong>
          {{
            indexStatus?.state === 'ready'
              ? '索引状态：LightRAG 已就绪'
              : indexStatus
                ? '索引未就绪，可用词法检索'
                : '等待索引状态'
          }}
        </strong>
        <span>{{ knowledgeCount }} 张资料</span>
      </div>
      <p>{{ indexStatus?.message || '连接后端后读取知识索引状态。' }}</p>
    </div>
  </aside>
</template>
