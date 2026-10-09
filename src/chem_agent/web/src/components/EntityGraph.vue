<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { Network, Maximize2, ZoomIn, ZoomOut, RotateCcw, X } from '@lucide/vue'
import {
  graphLayout,
  parts,
  sourceIds,
  entityTypeLabel as typeLabel,
  type RetrievalRecord,
} from '../utils/retrieval'
import GraphSources from './GraphSources.vue'

const props = defineProps<{
  entities: RetrievalRecord[]
  relationships: RetrievalRecord[]
  sources: RetrievalRecord[]
  hits: RetrievalRecord[]
}>()
const selected = defineModel<number>('selected', { default: 0 })
const graph = computed(() => graphLayout(props.entities, props.relationships))
const active = computed(() => graph.value.nodes[selected.value] || graph.value.nodes[0])
const related = computed(() =>
  graph.value.edges.filter(
    (edge) => edge.from.index === active.value?.index || edge.to.index === active.value?.index,
  ),
)
const neighbors = computed(() => [
  ...new Map(
    related.value.map((edge) => {
      const node = edge.from.index === active.value?.index ? edge.to : edge.from
      return [node.index, node] as const
    }),
  ).values(),
])
const lines = (name: string, size = 5, limit = Infinity) => {
  const chars = Array.from(name)
  const count = Math.min(Math.ceil(chars.length / size), limit)
  return Array.from({ length: count }, (_, index) => {
    const line = chars.slice(index * size, index * size + size).join('')
    return index === count - 1 && chars.length > size * count
      ? Array.from(line)
          .slice(0, size - 1)
          .join('') + '…'
      : line
  })
}
const focusNodes = computed(() => {
  if (!active.value) return []
  const candidates = [active.value, ...neighbors.value, ...graph.value.nodes]
  const included = new Set(
    [...new Map(candidates.map((node) => [node.index, node])).keys()].slice(0, 9),
  )
  const order = graph.value.order.filter((id) => included.has(id))
  const start = order.indexOf(active.value.index)
  const nodes = [...order.slice(start), ...order.slice(0, start)].map(
    (id) => graph.value.nodes[id]!,
  )
  return nodes.map((node, index) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / nodes.length
    const orbit = nodes.length === 1 ? 0 : 110
    return {
      ...node,
      x: 160 + orbit * Math.cos(angle),
      y: 160 + orbit * Math.sin(angle),
      radius: node.index === active.value?.index ? 36 : 32,
    }
  })
})
const focusEdges = computed(() => {
  const nodes = new Map(focusNodes.value.map((node) => [node.index, node]))
  return visibleEdges.value.flatMap((edge) => {
    const from = nodes.get(edge.from.index),
      to = nodes.get(edge.to.index)
    return from && to ? [{ ...edge, from, to }] : []
  })
})
const visibleEdges = computed(() => [
  ...new Map(
    graph.value.edges.map(
      (edge) => [[edge.from.index, edge.to.index].sort((a, b) => a - b).join(':'), edge] as const,
    ),
  ).values(),
])
const path = (edge: (typeof graph.value.edges)[number], radius = graph.value.nodeRadius) => {
  const { from, to } = edge
  const dx = to.x - from.x,
    dy = to.y - from.y
  const distance = Math.hypot(dx, dy) || 1
  return `M ${from.x + (dx * radius) / distance} ${from.y + (dy * radius) / distance} L ${to.x - (dx * radius) / distance} ${to.y - (dy * radius) / distance}`
}
const dialog = ref<HTMLDialogElement>()
const canvas = ref<HTMLDivElement>()
const titleId = useId()
const zoom = ref(1)
const filter = ref('')
const filtered = computed(() =>
  graph.value.nodes.filter((node) => node.name.toLowerCase().includes(filter.value.toLowerCase())),
)
const entity = computed(() => props.entities[active.value?.index ?? 0])
async function open() {
  zoom.value = 1
  dialog.value?.showModal()
  await nextTick()
  fit()
}
function fit() {
  if (!canvas.value) return
  zoom.value = Math.max(
    0.3,
    Math.min(
      1,
      (canvas.value.clientWidth - 36) / graph.value.width,
      (canvas.value.clientHeight - 36) / graph.value.height,
    ),
  )
  canvas.value.scrollTo(0, 0)
}
function close() {
  dialog.value?.close()
}
function changeZoom(delta: number) {
  zoom.value = Math.max(0.3, Math.min(2, Number((zoom.value + delta).toFixed(1))))
}
watch(
  () => props.entities,
  () => {
    close()
    selected.value = graph.value.nodes.reduce((best, node) => {
      const degree = (index: number) =>
        graph.value.edges.filter((edge) => edge.from.index === index || edge.to.index === index)
          .length
      return degree(node.index) > degree(best) ? node.index : best
    }, 0)
    filter.value = ''
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
        <Maximize2 :size="13" />
        展开图谱
      </button>
    </div>
    <p class="graph-stats">
      {{ graph.nodes.length }} 个实体
      <span />
      {{ graph.edges.length }} 条图内关系
    </p>
    <label class="graph-picker">
      查看实体
      <select v-model="selected" aria-label="选择图谱实体">
        <option v-for="node in graph.nodes" :key="node.index" :value="node.index">
          {{ node.name }}
        </option>
      </select>
    </label>
    <div class="graph-focus">
      <svg viewBox="0 0 320 320" role="group" aria-label="本轮实体关系预览">
        <path
          v-for="edge in focusEdges"
          :key="`link-${edge.index}`"
          :d="path(edge, 34)"
          :class="{ active: edge.from.index === selected || edge.to.index === selected }"
        />
        <g
          v-for="node in focusNodes"
          :key="node.index"
          role="button"
          tabindex="0"
          :class="{ active: node.index === active?.index }"
          :aria-label="`查看实体 ${node.name}`"
          :aria-current="node.index === active?.index ? 'true' : undefined"
          @click="selected = node.index"
          @keydown.enter.prevent="selected = node.index"
          @keydown.space.prevent="selected = node.index"
        >
          <circle :cx="node.x" :cy="node.y" :r="node.radius" />
          <text
            :x="node.x"
            :y="node.y - (lines(node.name, 5, 3).length - 1) * 7"
            text-anchor="middle"
            dominant-baseline="middle"
          >
            <tspan
              v-for="(line, index) in lines(node.name, 5, 3)"
              :key="index"
              :x="node.x"
              :dy="index ? 14 : 0"
            >
              {{ line }}
            </tspan>
          </text>
          <title>{{ node.name }}</title>
        </g>
      </svg>
      <p v-if="!neighbors.length" class="graph-empty">本轮未返回该实体的关联关系。</p>
    </div>
    <p class="graph-caption">
      预览 {{ focusNodes.length }} /
      {{ graph.nodes.length }} 个本轮实体。点击圆形节点查看详情；仅连接返回数据中端点匹配的关系。
    </p>
    <p v-if="relationships.length > graph.edges.length" class="graph-caption">
      另有
      {{ relationships.length - graph.edges.length }}
      条关系的端点未包含在返回实体中，可在下方“全部返回关系”查看。
    </p>
  </section>
  <Teleport to="body">
    <dialog
      ref="dialog"
      class="graph-dialog"
      :aria-labelledby="titleId"
      @click="$event.target === dialog && close()"
    >
      <header class="graph-modal-heading">
        <div>
          <h2 :id="titleId">
            <Network :size="18" />
            本轮检索关系图
          </h2>
          <p>
            {{ graph.nodes.length }} 个实体，{{ graph.edges.length }} 条图内关系；共返回
            {{ relationships.length }} 条关系
          </p>
        </div>
        <button class="icon-button" aria-label="关闭图谱" @click="close"><X :size="20" /></button>
      </header>
      <div class="graph-modal-body">
        <section class="graph-stage" aria-label="完整关系图">
          <div class="graph-toolbar">
            <label>
              查找实体
              <input
                v-model="filter"
                type="search"
                placeholder="输入实体名称"
                aria-label="查找图谱实体"
              />
            </label>
            <div class="graph-zoom">
              <button
                class="icon-button"
                aria-label="缩小图谱"
                title="缩小图谱"
                :disabled="zoom <= 0.3"
                @click="changeZoom(-0.1)"
              >
                <ZoomOut :size="17" />
              </button>
              <span>缩放 {{ Math.round(zoom * 100) }}%</span>
              <button
                class="icon-button"
                aria-label="放大图谱"
                title="放大图谱"
                :disabled="zoom >= 2"
                @click="changeZoom(0.1)"
              >
                <ZoomIn :size="17" />
              </button>
              <button
                class="graph-fit-button"
                aria-label="适应画布"
                title="调整比例以显示全部返回实体"
                @click="fit"
              >
                <RotateCcw :size="16" />
                适应画布
              </button>
            </div>
          </div>
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
            <p v-else class="graph-search-help">点击实体名称查看关系与原文。</p>
          </div>
          <div ref="canvas" class="graph-scroll" tabindex="0" aria-label="关系图画布，可滚动查看">
            <svg
              :width="graph.width * zoom"
              :height="graph.height * zoom"
              :viewBox="`0 0 ${graph.width} ${graph.height}`"
              class="graph-full"
              role="group"
              aria-label="所有返回实体与可匹配关系"
            >
              <path
                v-for="edge in visibleEdges"
                :key="edge.index"
                :d="path(edge)"
                :class="{ active: edge.from.index === selected || edge.to.index === selected }"
              >
                <title>{{ edge.description || `${edge.from.name} 与 ${edge.to.name}` }}</title>
              </path>
              <g
                v-for="node in graph.nodes"
                :key="node.index"
                role="button"
                tabindex="0"
                :class="{
                  active: node.index === selected,
                  neighbor: neighbors.some((item) => item.index === node.index),
                }"
                :aria-label="`查看实体 ${node.name}`"
                :aria-current="node.index === selected ? 'true' : undefined"
                @click="selected = node.index"
                @keydown.enter.prevent="selected = node.index"
                @keydown.space.prevent="selected = node.index"
              >
                <circle :cx="node.x" :cy="node.y" :r="graph.nodeRadius" />
                <text
                  :x="node.x"
                  :y="node.y - (lines(node.name).length - 1) * 11"
                  text-anchor="middle"
                  dominant-baseline="middle"
                >
                  <tspan
                    v-for="(line, index) in lines(node.name)"
                    :key="index"
                    :x="node.x"
                    :dy="index ? 22 : 0"
                  >
                    {{ line }}
                  </tspan>
                </text>
                <title>{{ node.name }}</title>
              </g>
            </svg>
          </div>
          <div class="graph-legend" role="note" aria-label="图谱颜色说明">
            <strong>颜色说明</strong>
            <span class="legend-item">
              <i aria-hidden="true" />
              当前查看的实体
            </span>
            <span class="legend-item">
              <i class="neighbor" aria-hidden="true" />
              与它直接关联的实体
            </span>
            <p>点击图中的圆形节点切换查看。颜色标记仅用于说明。</p>
            <p>同一对实体的多条关系合并为一条线，详情逐条展示。</p>
          </div>
        </section>
        <aside v-if="active" class="graph-detail" aria-label="选中实体与关系详情">
          <span class="graph-type-badge">{{ typeLabel(active.type) }}</span>
          <h3>{{ active.name }}</h3>
          <p v-for="part in parts(entity?.description)" :key="part">{{ part }}</p>
          <h4>
            关联关系
            <span>{{ related.length }}</span>
          </h4>
          <p v-if="!related.length">本轮未返回关联关系。</p>
          <article v-for="edge in related" :key="edge.index" class="graph-relation">
            <button
              @click="selected = edge.from.index === selected ? edge.to.index : edge.from.index"
            >
              {{ edge.from.index === selected ? edge.to.name : edge.from.name }}
            </button>
            <p>{{ edge.description || '未提供关系说明。' }}</p>
          </article>
          <h4>关联原文</h4>
          <GraphSources :ids="sourceIds(entity || {})" :sources="sources" :hits="hits" />
        </aside>
      </div>
      <footer class="graph-modal-footer">
        此图展示本轮返回的检索数据，不代表整个知识库。实体之间的关联不表示因果关系。
      </footer>
    </dialog>
  </Teleport>
</template>

<style scoped>
.graph-heading,
.graph-heading h3,
.graph-expand,
.graph-modal-heading h2,
.graph-toolbar,
.graph-zoom,
.graph-legend {
  display: flex;
  align-items: center;
  gap: 7px;
}
.graph-heading {
  justify-content: space-between;
  margin: 12px 0 8px;
}
.graph-heading h3 {
  font-size: 13px;
  font-weight: 600;
}
.graph-expand {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 5px;
  color: #475467;
  font-size: 11px;
  padding: 5px 7px;
}
.graph-stats {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--muted);
  font-size: 10px;
  margin-bottom: 14px;
}
.graph-stats span {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #98a2b3;
}
.graph-picker {
  display: grid;
  gap: 6px;
  font-size: 11px;
  color: #667085;
  margin-bottom: 10px;
}
.graph-picker select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  background: #fff;
  color: var(--ink);
}
.graph-focus {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 8px;
  max-height: 440px;
  overflow: auto;
}
.graph-focus svg {
  width: 100%;
  display: block;
}
svg path {
  fill: none;
  stroke: #b7c9e2;
  stroke-width: 1.5;
}
svg circle {
  fill: #fff;
  stroke: #a9bed8;
  stroke-width: 1.7;
}
svg text {
  fill: #344054;
  font-size: 12px;
  font-weight: 500;
  pointer-events: none;
}
svg path.active {
  stroke: #7da0d1;
  stroke-width: 2;
}
.graph-focus text {
  font-size: 11px;
}
svg g {
  cursor: pointer;
}
svg g.active circle {
  fill: #eff6ff;
  stroke: #2563eb;
  stroke-width: 2.5;
}
svg g.active text {
  fill: #1d4ed8;
}
svg g:focus {
  outline: none;
}
svg g:focus-visible circle {
  stroke: #1d4ed8;
  stroke-width: 3;
}
.graph-empty {
  font-size: 11px;
  text-align: center;
  color: #667085;
  margin: 0 12px 18px;
}
.graph-dialog {
  width: min(1240px, calc(100vw - 40px));
  max-width: none;
  height: min(820px, calc(100dvh - 40px));
  max-height: none;
  margin: auto;
  padding: 0;
  border: 1px solid #d0d5dd;
  border-radius: 12px;
  background: #fff;
  color: var(--ink);
  box-shadow: 0 24px 80px #10182833;
}
.graph-dialog::backdrop {
  background: #10182866;
}
.graph-dialog[open] {
  display: flex;
  flex-direction: column;
}
.graph-modal-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid var(--border);
}
.graph-modal-heading h2 {
  font-size: 17px;
  font-weight: 600;
}
.graph-modal-heading p {
  font-size: 12px;
  color: #667085;
  margin-top: 6px;
}
.graph-modal-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  flex: 1;
  min-height: 0;
}
.graph-stage {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: #f8fafc;
}
.graph-toolbar {
  justify-content: space-between;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.graph-toolbar label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #667085;
}
.graph-toolbar input {
  min-width: 0;
  width: 170px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 5px;
  font-size: 12px;
}
.graph-zoom {
  font-size: 11px;
  color: #667085;
}
.graph-zoom button:disabled {
  opacity: 0.4;
}
.graph-scroll {
  overflow: auto;
  flex: 1;
  min-height: 220px;
}
.graph-full {
  display: block;
  margin: 18px auto;
}
.graph-full text {
  font-size: 18px;
}
.graph-full path {
  stroke: #d0d8e4;
  stroke-width: 1.3;
}
.graph-full path.active {
  stroke: #4d83d9;
  stroke-width: 2;
}
.graph-full g.neighbor circle {
  stroke: #93b4e7;
  fill: #fbfdff;
}
.graph-full g.active circle {
  fill: #eff6ff;
  stroke: #2563eb;
}
.graph-legend {
  flex-wrap: wrap;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: #fff;
  font-size: 10px;
  color: #667085;
}
.graph-legend i {
  width: 8px;
  height: 8px;
  background: #2563eb;
  border-radius: 50%;
  display: inline-block;
}
.graph-legend i.neighbor {
  background: #93b4e7;
}
.graph-legend p {
  flex-basis: 100%;
  line-height: 1.7;
}
.graph-detail {
  border-left: 1px solid var(--border);
  padding: 20px;
  overflow: auto;
  min-width: 0;
}
.graph-type-badge {
  display: inline-block;
  font-size: 10px;
  color: #1d4ed8;
  background: #eff6ff;
  border-radius: 4px;
  padding: 3px 6px;
}
.graph-detail h3 {
  font-size: 17px;
  margin: 10px 0 15px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.graph-detail > p {
  font-size: 12px;
  line-height: 1.9;
  margin: 9px 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.graph-detail h4 {
  font-size: 12px;
  margin: 23px 0 12px;
}
.graph-detail h4 span {
  color: #667085;
  font-weight: 400;
  margin-left: 5px;
}
.graph-relation {
  border: 1px solid #e8edf3;
  border-radius: 6px;
  margin: 9px 0;
  padding: 10px 12px;
  background: #fcfdff;
}
.graph-relation button {
  border: 0;
  background: none;
  color: #1d4ed8;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  padding: 0;
  overflow-wrap: anywhere;
}
.graph-relation p {
  font-size: 11px;
  line-height: 1.8;
  color: #667085;
  margin: 7px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.graph-search-results {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.graph-search-results button {
  font-size: 11px;
  border: 1px solid #d0d5dd;
  border-radius: 5px;
  background: #fff;
  padding: 5px 7px;
}
.graph-search-results button.active {
  border-color: #2563eb;
  color: #1d4ed8;
}
.graph-search-results p {
  font-size: 12px;
  color: #667085;
}
.graph-modal-footer {
  padding: 11px 22px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: #667085;
  line-height: 1.7;
}
@media (max-width: 700px) {
  .graph-dialog {
    width: calc(100vw - 16px);
    height: calc(100dvh - 16px);
  }
  .graph-modal-body {
    grid-template-columns: 1fr;
    overflow: auto;
    display: block;
  }
  .graph-stage {
    height: 460px;
  }
  .graph-detail {
    border-left: 0;
    border-top: 1px solid var(--border);
    overflow: visible;
  }
  .graph-toolbar label {
    flex: 1 0 100%;
    white-space: nowrap;
  }
  .graph-toolbar input {
    flex: 1;
    width: auto;
  }
  .graph-zoom {
    margin-left: auto;
  }
  .graph-modal-heading {
    padding: 14px;
  }
  .graph-modal-heading h2 {
    font-size: 15px;
  }
}
.graph-legend strong {
  font-size: 10px;
  font-weight: 500;
  color: #667085;
}
.graph-legend .legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #475467;
  cursor: default;
}
.graph-fit-button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  padding: 6px 8px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: #475467;
}
.graph-search-help {
  flex-basis: 100%;
  font-size: 11px;
  color: #667085;
}
</style>
