<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { Network, Maximize2, X } from '@lucide/vue'
import { defaultEntityIndex, text, type RetrievalRecord } from '../utils/retrieval'
import RunKnowledgeGraph from './RunKnowledgeGraph.vue'

const props = defineProps<{
  entities: RetrievalRecord[]
  relationships: RetrievalRecord[]
  sources: RetrievalRecord[]
  hits: RetrievalRecord[]
  citations?: string[]
  keywords?: string[]
  query?: string
  selectionKey?: string
}>()
const selected = defineModel<number>('selected', { default: 0 })
const dialog = ref<HTMLDialogElement>()
const opened = ref(false)
const filter = ref('')
const titleId = useId()
const nodes = computed(() =>
  props.entities.map((item, index) => ({
    index,
    id: text(item.id) || text(item.name) || text(item.entity_name),
    name: text(item.name) || text(item.entity_name) || text(item.id),
  })),
)
const selectedId = computed(() => nodes.value[selected.value]?.id || '')
const filtered = computed(() =>
  nodes.value.filter((node) => node.name.toLowerCase().includes(filter.value.trim().toLowerCase())),
)
function select(id: string) {
  const index = nodes.value.findIndex((node) => node.id === id)
  if (index >= 0) selected.value = index
}
function open() {
  opened.value = true
  dialog.value?.showModal()
}
function close() {
  dialog.value?.close()
  opened.value = false
}
watch(
  () => props.selectionKey ?? props.query,
  () => {
    close()
    filter.value = ''
    selected.value = defaultEntityIndex(
      props.entities,
      props.relationships,
      props.hits,
      props.citations,
      props.keywords,
      props.query,
    )
  },
  { immediate: true },
)
</script>

<template>
  <section class="knowledge-graph" aria-label="实体关系概览">
    <div class="graph-heading">
      <h3>
        <Network :size="15" />
        实体与关系
      </h3>
      <button class="graph-expand" @click="open">
        <Maximize2 :size="14" />
        全屏查看
      </button>
    </div>
    <label class="graph-picker">
      查看实体
      <select v-model="selected" aria-label="选择图谱实体">
        <option v-for="node in nodes" :key="node.index" :value="node.index">{{ node.name }}</option>
      </select>
    </label>
    <div class="graph-preview">
      <RunKnowledgeGraph
        :entities="entities"
        :relationships="relationships"
        :sources="sources"
        :hits="hits"
        :selected-id="selectedId"
        compact
        @select="select"
      />
    </div>
    <p class="graph-caption">
      显示本次返回网络，含关系中明确出现的端点。节点较多时自动精简标签，可缩放或全屏查看。
    </p>
  </section>
  <Teleport to="body">
    <dialog
      ref="dialog"
      class="retrieval-graph-dialog"
      :aria-labelledby="titleId"
      @cancel.prevent="close"
      @click="$event.target === dialog && close()"
    >
      <header>
        <h2 :id="titleId">
          <Network :size="20" />
          本轮检索关系图
        </h2>
        <button class="icon-button" aria-label="关闭图谱" @click="close"><X :size="20" /></button>
      </header>
      <label class="graph-search">
        查找实体
        <input
          v-model="filter"
          type="search"
          placeholder="输入实体名称"
          aria-label="查找图谱实体"
        />
      </label>
      <div v-if="filter" class="graph-search-results">
        <button
          v-for="node in filtered"
          :key="node.index"
          :class="{ active: node.index === selected }"
          @click="selected = node.index"
        >
          {{ node.name }}
        </button>
        <p v-if="!filtered.length">未找到匹配实体，请调整关键词。</p>
      </div>
      <div class="graph-full-view">
        <RunKnowledgeGraph
          v-if="opened"
          :entities="entities"
          :relationships="relationships"
          :sources="sources"
          :hits="hits"
          :selected-id="selectedId"
          @select="select"
        />
      </div>
      <footer>
        仅展示本轮返回的实体和关系。关系端点单独标明；关联不表示因果，关联来源不自动成为回答引用。
      </footer>
    </dialog>
  </Teleport>
</template>

<style scoped>
.graph-heading,
.graph-heading h3,
.graph-expand,
.retrieval-graph-dialog header,
.retrieval-graph-dialog h2 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.graph-heading,
.retrieval-graph-dialog header {
  justify-content: space-between;
}
.graph-heading h3 {
  margin: 0;
  font-size: 14px;
}
.graph-expand {
  color: var(--accent);
  font-size: 12px;
}
.graph-picker,
.graph-search {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
  font-size: 12px;
}
.graph-picker select {
  flex: 1;
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
}
.graph-preview {
  height: 400px;
}
.graph-caption {
  margin: 10px 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
}
.retrieval-graph-dialog {
  width: min(1400px, 96vw);
  height: 92vh;
  max-height: 94vh;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: #fff;
  color: var(--ink);
}
.retrieval-graph-dialog[open] {
  display: flex;
  flex-direction: column;
}
.retrieval-graph-dialog::backdrop {
  background: #172a4880;
}
.retrieval-graph-dialog h2 {
  margin: 0;
  font-size: 18px;
}
.graph-search input {
  flex: 1;
  max-width: 380px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.graph-search-results {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 100px;
  overflow: auto;
  padding-bottom: 12px;
}
.graph-search-results button {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.graph-search-results button.active {
  color: var(--accent);
  background: #eff6ff;
}
.graph-full-view {
  flex: 1;
  min-height: 0;
}
.retrieval-graph-dialog footer {
  padding-top: 12px;
  font-size: 12px;
  color: var(--muted);
}
@media (max-width: 650px) {
  .retrieval-graph-dialog {
    padding: 12px;
  }
}
</style>
