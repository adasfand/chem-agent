<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { Search, BookOpen, ChevronRight, FileText } from '@lucide/vue'
import type { Bootstrap, KnowledgeDetail, KnowledgeItem } from '../types/api'
import { api } from '../services/api'
import MarkdownText from './MarkdownText.vue'
const props = defineProps<{
  items: KnowledgeItem[]
  initialId: string | null
  indexStatus?: Bootstrap['index_status']
  busy?: boolean
}>()
defineEmits<{ search: [query: string] }>()
const query = ref('')
const selected = ref('')
const detail = ref<KnowledgeDetail | null>(null)
const error = ref('')
const loading = ref(false)
let generation = 0
const filtered = computed(() =>
  props.items.filter((item) =>
    `${item.title} ${item.source}`.toLowerCase().includes(query.value.trim().toLowerCase()),
  ),
)
const documentBody = computed(() => {
  const document = detail.value
  if (!document) return ''
  const lines = document.text.split(/\r?\n/)
  const heading = lines[0]?.match(/^#\s+(.+)$/)
  if (heading?.[1]?.trim() !== document.title.trim()) return document.text
  lines.shift()
  const firstContent = lines.findIndex((line) => line.trim())
  const source = lines[firstContent]?.match(/^来源[：:]\s*(.+)$/)
  if (source?.[1]?.trim() === document.source.trim()) lines.splice(firstContent, 1)
  return lines.join('\n').replace(/^\s*\n/, '')
})
async function select(id: string) {
  const current = ++generation
  selected.value = id
  detail.value = null
  loading.value = true
  error.value = ''
  try {
    const result = await api.knowledge(id)
    if (current === generation) detail.value = result
  } catch (cause) {
    if (current === generation)
      error.value = cause instanceof Error ? cause.message : '读取失败，请重试。'
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(
  () => [props.initialId, props.items[0]?.doc_id] as const,
  () => {
    const id = props.initialId || props.items[0]?.doc_id
    if (id) void select(id)
  },
  { immediate: true },
)
onUnmounted(() => {
  generation++
})
</script>
<template>
  <div class="knowledge-layout">
    <section class="knowledge-index-status" aria-label="知识处理与索引状态">
      <strong>知识处理与检索索引</strong>
      <span>资料文档 {{ items.length }}</span>
      <span>正文解析片段 {{ items.reduce((sum, item) => sum + item.chunk_count, 0) }}</span>
      <span v-if="indexStatus?.backend === 'lightrag' && indexStatus.state === 'ready'">
        LightRAG 索引片段 {{ indexStatus.chunk_count }}
      </span>
      <span>检索后端 {{ indexStatus?.backend ?? '未记录' }}</span>
      <span>索引状态 {{ indexStatus?.message ?? '等待后端状态' }}</span>
    </section>
    <section class="knowledge-index panel">
      <div class="panel-heading">
        <BookOpen :size="19" />
        <h2>知识目录</h2>
        <span class="count-tag">{{ items.length }}</span>
      </div>
      <label class="search-field">
        <Search :size="16" />
        <input
          v-model="query"
          type="search"
          maxlength="160"
          aria-label="筛选目录标题或来源"
          placeholder="筛选目录标题或来源…"
        />
      </label>
      <button
        class="button secondary library-content-search"
        :disabled="busy || !query.trim()"
        @click="$emit('search', query.trim())"
      >
        在问答中检索内容
      </button>
      <p class="library-note">
        目录筛选按标题与来源匹配。内容检索会将关键词填入问答，由你确认发送。
      </p>
      <div class="knowledge-list">
        <button
          v-for="item in filtered"
          :key="item.doc_id"
          :class="{ selected: selected === item.doc_id }"
          :aria-current="selected === item.doc_id ? 'true' : undefined"
          @click="select(item.doc_id)"
        >
          <FileText :size="17" />
          <span>
            <strong>{{ item.title }}</strong>
            <small>{{ item.chunk_count }} 个知识片段</small>
          </span>
          <ChevronRight :size="16" />
        </button>
        <p v-if="!filtered.length" class="empty-message">没有匹配的知识卡，请调整关键词。</p>
      </div>
      <p class="library-note">含教学卡及官方来源整理卡，不代替实测物性数据。</p>
    </section>
    <section class="knowledge-document panel" :aria-busy="loading">
      <div v-if="loading" class="empty-message">正在读取知识卡…</div>
      <div v-else-if="error" class="empty-message">
        <p>{{ error }}</p>
        <button class="button secondary" @click="select(selected)">重新读取</button>
      </div>
      <template v-else-if="detail">
        <div class="document-heading">
          <span class="document-label">知识卡</span>
          <h2>{{ detail.title }}</h2>
          <p>{{ detail.chunk_count }} 个知识片段</p>
        </div>
        <div class="source-banner">
          <BookOpen :size="17" />
          <span>来源：{{ detail.source }}</span>
        </div>
        <MarkdownText :text="documentBody" />
      </template>
      <p v-else class="empty-message">请选择一张知识卡。</p>
    </section>
  </div>
</template>
