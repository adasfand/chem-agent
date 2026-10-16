<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import {
  Network,
  Search,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  ArrowUpRight,
  Layers3,
  Minimize2,
  PanelRightClose,
} from '@lucide/vue'
import { request } from '../services/api'
import {
  explorerLayout,
  adjacentIds,
  fitGraphView,
  nodeColor,
  type GraphOverview,
} from '../utils/graphExplorer'
import { entityTypeLabel, parts, sourceIds, text } from '../utils/retrieval'
import MarkdownText from './MarkdownText.vue'

const emit = defineEmits<{ knowledge: [id: string]; ask: [query: string] }>()
const data = ref<GraphOverview>()
const query = ref('')
const limit = ref(72)
const loading = ref(false)
const error = ref('')
const selected = ref('')
const selectedEdge = ref<number | null>(null)
const allLabels = ref(false)
const fullScreen = ref(false)
const detailOpen = ref(false)
const canvas = ref<HTMLDivElement>()
const viewport = ref({ width: 1100, height: 720 })
const svg = ref<SVGSVGElement>()
const zoom = ref(1)
const pan = ref({ x: 0, y: 0 })
const drag = ref<{ x: number; y: number; px: number; py: number }>()
let requestId = 0
const layout = computed(() => explorerLayout(data.value || { entities: [], relationships: [] }))
const fitted = computed(() =>
  fitGraphView(layout.value.nodes, viewport.value.width, viewport.value.height),
)
const neighbors = computed(() => adjacentIds(layout.value, selected.value))
const active = computed(() => data.value?.entities.find((entity) => entity.id === selected.value))
const edge = computed(() =>
  selectedEdge.value === null ? undefined : data.value?.relationships[selectedEdge.value],
)
const detail = computed(() => edge.value || active.value)
const detailSources = computed(() => {
  const ids = sourceIds(detail.value || {})
  return data.value?.sources.filter((source) => ids.includes(text(source.chunk_id))) || []
})
const related = computed(() =>
  layout.value.edges.filter(
    ({ from, to }) => from.id === selected.value || to.id === selected.value,
  ),
)
const types = computed(() => [...new Set(layout.value.nodes.map((node) => node.type))].sort())
const labelIds = computed(
  () =>
    new Set(
      [...layout.value.nodes]
        .sort((a, b) => b.degree - a.degree)
        .slice(0, 18)
        .map((node) => node.id),
    ),
)
const focusTitle = computed(() =>
  edge.value ? `${text(edge.value.source)} ↔ ${text(edge.value.target)}` : text(active.value?.name),
)
function selectNode(id: string, showDetail = true) {
  selected.value = id
  selectedEdge.value = null
  if (showDetail) detailOpen.value = true
}
function selectEdge(index: number) {
  selectedEdge.value = index
  detailOpen.value = true
}
async function load(topic = query.value) {
  const id = ++requestId
  query.value = topic
  loading.value = true
  error.value = ''
  try {
    const result = await request<GraphOverview>(
      `/api/knowledge-graph?query=${encodeURIComponent(topic)}&limit=${limit.value}`,
    )
    if (id !== requestId) return
    data.value = result
    const first = [...result.entities].sort(
      (a, b) => Number(b.seed) - Number(a.seed) || Number(b.degree) - Number(a.degree),
    )[0]
    selectNode(text(first?.id), false)
    fit()
  } catch (cause) {
    if (id === requestId) error.value = cause instanceof Error ? cause.message : '图谱读取失败。'
  } finally {
    if (id === requestId) loading.value = false
  }
}
function fit() {
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
}
function closeDetails() {
  detailOpen.value = false
  fit()
}
async function toggleFullScreen() {
  fullScreen.value = !fullScreen.value
  detailOpen.value = false
  await nextTick()
  fit()
}
function changeZoom(delta: number) {
  zoom.value = Math.max(0.6, Math.min(3, zoom.value + delta))
}
function pointerDown(event: PointerEvent) {
  if ((event.target as Element).closest('[data-interactive]')) return
  drag.value = { x: event.clientX, y: event.clientY, px: pan.value.x, py: pan.value.y }
  svg.value?.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!drag.value || !svg.value) return
  const bounds = svg.value.getBoundingClientRect()
  const scale = viewport.value.width / bounds.width
  pan.value = {
    x: drag.value.px + (event.clientX - drag.value.x) * scale,
    y: drag.value.py + (event.clientY - drag.value.y) * scale,
  }
}
function label(name: string) {
  return name.length > 12 ? name.slice(0, 11) + '…' : name
}
let observer: ResizeObserver | undefined
function escapeFocus(event: KeyboardEvent) {
  if (event.key === 'Escape' && fullScreen.value) void toggleFullScreen()
}
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) viewport.value = { width: entry.contentRect.width, height: entry.contentRect.height }
  })
  if (canvas.value) observer.observe(canvas.value)
  window.addEventListener('keydown', escapeFocus)
  void load('')
})
onUnmounted(() => {
  observer?.disconnect()
  window.removeEventListener('keydown', escapeFocus)
})
</script>

<template>
  <section class="graph-explorer" :class="{ 'focus-mode': fullScreen }" aria-label="知识图谱探索">
    <header class="explorer-heading">
      <div>
        <span class="eyebrow">KNOWLEDGE ATLAS / 化工知识网络</span>
        <h1>
          <Network :size="24" />
          知识图谱探索
        </h1>
        <p>沿真实实体与关系展开，追溯知识原文，再进入问答与计算。</p>
      </div>
      <div class="atlas-heading-actions">
        <div class="atlas-totals">
          <div>
            <strong>{{ data?.stats.total_entities ?? '—' }}</strong>
            <span>全库实体</span>
          </div>
          <div>
            <strong>{{ data?.stats.total_relationships ?? '—' }}</strong>
            <span>全库关系</span>
          </div>
          <div>
            <strong>{{ data?.stats.documents ?? '—' }}</strong>
            <span>知识文档</span>
          </div>
        </div>
        <button class="atlas-focus-toggle" :aria-pressed="fullScreen" @click="toggleFullScreen">
          <Minimize2 v-if="fullScreen" :size="16" />
          <Maximize2 v-else :size="16" />
          {{ fullScreen ? '退出全屏' : '全屏展示' }}
        </button>
      </div>
    </header>
    <form class="atlas-search" @submit.prevent="load()">
      <label>
        <Search :size="17" />
        <input
          v-model="query"
          maxlength="100"
          placeholder="搜索实体，例如：质量分数、热负荷、相变"
          aria-label="搜索知识图谱实体"
        />
      </label>
      <select v-model="limit" aria-label="子图实体上限" @change="load()">
        <option :value="48">48 个实体</option>
        <option :value="72">72 个实体</option>
        <option :value="100">100 个实体</option>
      </select>
      <button type="submit" class="button primary" :disabled="loading">
        {{ loading ? '载入中…' : '探索关联' }}
      </button>
      <button type="button" class="button secondary" :disabled="loading" @click="load('')">
        <RotateCcw :size="15" />
        全库概览
      </button>
    </form>
    <div class="atlas-topics">
      <span>连接枢纽</span>
      <button
        v-for="topic in data?.topics.slice(0, 7)"
        :key="topic"
        :class="{ active: data?.query === topic }"
        @click="load(topic)"
      >
        {{ topic }}
      </button>
    </div>
    <p v-if="error" class="atlas-error" role="alert">{{ error }}</p>
    <p v-if="data && data.state !== 'ready'" class="atlas-error">{{ data.message }}</p>
    <div class="atlas-workspace" :class="{ 'details-open': detailOpen }">
      <div ref="canvas" class="atlas-canvas">
        <div class="atlas-caption">
          <span>
            <i />
            {{ data?.query ? `${data.query} · 关联子图` : '全库 · 高连接子图' }}
          </span>
          <small>
            {{ layout.nodes.length }} 个实体 / {{ layout.edges.length }} 条真实关系 /
            {{ data?.stats.source_documents || 0 }} 篇来源
          </small>
        </div>
        <svg
          ref="svg"
          :viewBox="`0 0 ${viewport.width} ${viewport.height}`"
          role="group"
          aria-label="LightRAG 真实索引关系网络"
          @pointerdown="pointerDown"
          @pointermove="pointerMove"
          @pointerup="drag = undefined"
          @pointercancel="drag = undefined"
          @wheel.prevent="changeZoom($event.deltaY < 0 ? 0.1 : -0.1)"
        >
          <defs>
            <radialGradient id="atlas-glow">
              <stop offset="0%" stop-color="#d9ecfa" stop-opacity="0.7" />
              <stop offset="100%" stop-color="#eef7fc" stop-opacity="0" />
            </radialGradient>
            <pattern id="atlas-grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r="0.65" fill="#c9dcea" />
            </pattern>
          </defs>
          <rect :width="viewport.width" :height="viewport.height" fill="url(#atlas-grid)" />
          <ellipse
            :cx="viewport.width / 2"
            :cy="viewport.height / 2"
            :rx="viewport.width / 2"
            :ry="viewport.height / 2"
            fill="url(#atlas-glow)"
          />
          <g
            :transform="`translate(${fitted.offsetX + pan.x} ${fitted.offsetY + pan.y}) scale(${fitted.scale * zoom}) translate(${-fitted.centerX} ${-fitted.centerY})`"
          >
            <g class="atlas-edges">
              <g
                v-for="link in layout.edges"
                :key="link.index"
                :class="{
                  highlighted: link.from.id === selected || link.to.id === selected,
                  chosen: selectedEdge === link.index,
                }"
              >
                <line :x1="link.from.x" :y1="link.from.y" :x2="link.to.x" :y2="link.to.y" />
                <line
                  data-interactive="edge"
                  class="edge-hit"
                  :x1="link.from.x"
                  :y1="link.from.y"
                  :x2="link.to.x"
                  :y2="link.to.y"
                  role="button"
                  tabindex="0"
                  :aria-label="`查看关系 ${link.from.name} 与 ${link.to.name}`"
                  @click="selectEdge(link.index)"
                  @keydown.enter="selectEdge(link.index)"
                  @keydown.space.prevent="selectEdge(link.index)"
                >
                  <title>{{ link.from.name }} ↔ {{ link.to.name }} · 点击查看来源</title>
                </line>
              </g>
            </g>
            <g
              v-for="node in layout.nodes"
              :key="node.id"
              data-interactive="node"
              class="atlas-node"
              :class="{ selected: selected === node.id }"
              role="button"
              tabindex="0"
              :aria-label="`探索实体 ${node.name}`"
              :aria-pressed="selected === node.id"
              @click="selectNode(node.id)"
              @keydown.enter="selectNode(node.id)"
              @keydown.space.prevent="selectNode(node.id)"
            >
              <circle
                v-if="node.degree >= 12 || selected === node.id"
                :cx="node.x"
                :cy="node.y"
                :r="node.radius + 7"
                :fill="nodeColor(node.type)"
                opacity="0.09"
              />
              <circle
                class="node-core"
                :cx="node.x"
                :cy="node.y"
                :r="node.radius"
                :fill="nodeColor(node.type)"
                :stroke="nodeColor(node.type)"
              />
              <circle
                v-if="selected === node.id"
                class="selection-ring"
                :cx="node.x"
                :cy="node.y"
                :r="node.radius + 6"
              />
              <text
                v-if="
                  allLabels ||
                  labelIds.has(node.id) ||
                  selected === node.id ||
                  (detailOpen && neighbors.has(node.id))
                "
                :x="node.x"
                :y="node.y + node.radius + 17"
                text-anchor="middle"
                :class="{ 'hub-label': node.degree >= 12 }"
                :style="{
                  fontSize: `${(node.degree >= 12 ? 13 : 12) / Math.min(1, fitted.scale)}px`,
                }"
              >
                {{ label(node.name) }}
              </text>
              <title>
                {{ node.name }} · {{ entityTypeLabel(node.type) }} · 全库连接 {{ node.degree }}
              </title>
            </g>
          </g>
          <text
            v-if="!loading && data?.state === 'ready' && !layout.nodes.length"
            :x="viewport.width / 2"
            :y="viewport.height / 2"
            text-anchor="middle"
            class="empty-graph"
          >
            没有匹配实体，请输入其他关键词
          </text>
        </svg>
        <div class="atlas-tools">
          <button aria-label="缩小知识网络" @click="changeZoom(-0.15)">
            <ZoomOut :size="17" />
          </button>
          <span>{{ Math.round(zoom * 100) }}%</span>
          <button aria-label="放大知识网络" @click="changeZoom(0.15)"><ZoomIn :size="17" /></button>
          <button aria-label="重置知识网络视图" @click="fit"><Maximize2 :size="17" /></button>
          <label>
            <input v-model="allLabels" type="checkbox" />
            全部标签
          </label>
        </div>
        <div class="atlas-legend">
          <span v-for="type in types" :key="type">
            <i :style="{ background: nodeColor(type) }" />
            {{ entityTypeLabel(type) }}
          </span>
          <small>节点大小：全库连接数 · 拖动画布 / 滚轮缩放</small>
        </div>
      </div>
      <aside v-if="detailOpen" class="atlas-detail" aria-label="图谱实体与原文">
        <button class="atlas-close-detail" @click="closeDetails">
          <PanelRightClose :size="15" />
          收起详情
        </button>
        <template v-if="detail">
          <div class="detail-kicker">
            <Layers3 :size="14" />
            {{ edge ? '索引关系' : entityTypeLabel(text(active?.type)) }}
            <span>可追溯</span>
          </div>
          <h2>{{ focusTitle }}</h2>
          <div v-if="!edge" class="detail-metrics">
            <span>
              <strong>{{ active?.degree }}</strong>
              全库连接
            </span>
            <span>
              <strong>{{ related.length }}</strong>
              图内关系
            </span>
            <span>
              <strong>{{ detailSources.length }}</strong>
              来源片段
            </span>
          </div>
          <p v-for="part in parts(detail.description)" :key="part" class="detail-description">
            {{ part }}
          </p>
          <div v-if="edge && text(edge.keywords)" class="edge-keywords">
            关系标签：{{ text(edge.keywords) }}
          </div>
          <div v-if="!edge" class="detail-actions">
            <button @click="load(selected)">
              以此实体展开
              <Network :size="13" />
            </button>
            <button
              @click="
                emit(
                  'ask',
                  `请检索知识库，说明${selected}的定义、相关公式和适用条件，引用知识来源。`,
                )
              "
            >
              发起知识问答
              <ArrowUpRight :size="14" />
            </button>
          </div>
          <h3>
            关联原文
            <span>{{ detailSources.length }}</span>
          </h3>
          <p class="source-scope">以下为索引来源；仅在实际问答检索命中后才可作为本轮回答依据。</p>
          <details
            v-for="source in detailSources"
            :key="text(source.chunk_id)"
            class="atlas-source"
          >
            <summary>{{ text(source.title) }}</summary>
            <MarkdownText :text="text(source.text)" />
            <button @click="emit('knowledge', text(source.doc_id))">
              打开完整知识卡
              <ArrowUpRight :size="12" />
            </button>
          </details>
          <p v-if="!detailSources.length" class="source-scope">
            当前关系的原文未解析，不能据此核验。
          </p>
          <template v-if="!edge">
            <h3>
              直接关系
              <span>{{ related.length }}</span>
            </h3>
            <button
              v-for="link in related"
              :key="link.index"
              class="relation-row"
              @click="selectEdge(link.index)"
            >
              <span>{{ link.from.id === selected ? link.to.name : link.from.name }}</span>
              <small>{{ text(link.data.keywords) || '查看关系与来源' }}</small>
              <ArrowUpRight :size="13" />
            </button>
          </template>
          <button v-else class="back-entity" @click="selectedEdge = null">返回选中实体</button>
        </template>
        <p v-else class="source-scope">点击图中实体或关系，查看定义、连接与来源原文。</p>
      </aside>
    </div>
    <footer class="atlas-footnote">
      <span>LightRAG · 索引探索</span>
      当前展示全库的真实子图；布局与邻域展开仅用于浏览，不增加检索命中或回答引用。连线表示抽取关联，不等同因果或已验证结论。
    </footer>
  </section>
</template>

<style scoped>
.graph-explorer {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 26px 30px 18px;
  background: #f6f8fc;
}
.explorer-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 21px;
}
.eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.4px;
  color: #7d8da9;
}
.explorer-heading h1 {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 24px;
  color: #172943;
  letter-spacing: -0.6px;
  margin: 7px 0;
}
.explorer-heading p {
  font-size: 12px;
  color: #77869c;
}
.atlas-totals {
  display: flex;
  gap: 30px;
}
.atlas-totals div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.atlas-totals strong {
  font-size: 29px;
  font-weight: 600;
  color: #223e63;
  font-variant-numeric: tabular-nums;
}
.atlas-totals span {
  font-size: 11px;
  color: #8491a4;
}
.atlas-search {
  display: flex;
  gap: 10px;
  align-items: center;
}
.atlas-search > label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 13px;
  height: 40px;
  background: white;
  border: 1px solid #dfe5ee;
  border-radius: 8px;
  color: #8c99ac;
}
.atlas-search input {
  border: 0;
  outline: none;
  width: 100%;
  background: transparent;
  font-size: 12px;
}
.atlas-search select {
  height: 39px;
  border: 1px solid #dfe5ee;
  border-radius: 7px;
  background: white;
  color: #61718a;
  font-size: 12px;
  padding: 0 10px;
}
.atlas-search .button {
  height: 39px;
  font-size: 12px;
}
.atlas-topics {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  padding: 12px 0 17px;
}
.atlas-topics > span {
  font-size: 10px;
  color: #8c99ac;
  margin-right: 4px;
}
.atlas-topics button {
  background: #fff;
  border: 1px solid #e3e8f0;
  border-radius: 20px;
  color: #62738c;
  padding: 4px 10px;
  font-size: 11px;
}
.atlas-topics button.active {
  border-color: #99b5db;
  background: #eaf2ff;
  color: #345f94;
}
.atlas-error {
  font-size: 12px;
  padding: 10px;
  color: #9d3e32;
}
.atlas-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  min-height: 560px;
  height: calc(100dvh - 310px);
  border-radius: 13px;
  overflow: hidden;
  border: 1px solid #dce4f0;
  box-shadow: 0 7px 30px #223b6010;
}
.atlas-canvas {
  background: #f3f8fd;
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.atlas-caption {
  position: absolute;
  top: 20px;
  left: 22px;
  right: 20px;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  pointer-events: none;
}
.atlas-caption > span {
  font-size: 12px;
  font-weight: 600;
  color: #203b56;
  display: flex;
  align-items: center;
  gap: 8px;
}
.atlas-caption i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #248d6b;
  box-shadow: 0 0 10px #248d6b33;
}
.atlas-caption small {
  font-size: 10px;
  color: #60758f;
  max-width: 200px;
  text-align: right;
}
.atlas-canvas > svg {
  width: 100%;
  height: 100%;
  min-height: 0;
  cursor: grab;
  touch-action: none;
}
.atlas-canvas > svg:active {
  cursor: grabbing;
}
.atlas-edges line {
  stroke: #8da9bf;
  stroke-width: 1.15;
  opacity: 0.58;
  vector-effect: non-scaling-stroke;
}
.atlas-edges .highlighted line {
  stroke: #278ba5;
  stroke-width: 1.7;
  opacity: 0.75;
}
.atlas-edges .chosen line {
  stroke: #b27b21;
  stroke-width: 3;
  opacity: 1;
}
.atlas-edges .edge-hit {
  stroke: transparent !important;
  stroke-width: 12;
  opacity: 1;
  cursor: pointer;
}
.atlas-edges .edge-hit:focus-visible {
  stroke: #b27b21 !important;
  stroke-width: 3;
  outline: none;
}
.atlas-node {
  cursor: pointer;
  outline: none;
}
.node-core {
  stroke-width: 1.6;
  fill-opacity: 0.96;
}
.atlas-node text {
  fill: #35516d;
  font-size: 12px;
  font-weight: 400;
  paint-order: stroke;
  stroke: #f3f8fd;
  stroke-width: 4px;
  stroke-linejoin: round;
  pointer-events: none;
}
.atlas-node .hub-label {
  font-size: 13px;
  font-weight: 600;
  fill: #203b56;
}
.atlas-node.selected text {
  fill: #173853;
  font-weight: 600;
}
.atlas-node.selected .node-core {
  fill-opacity: 1;
  stroke: #356c9b;
  stroke-width: 2;
}
.selection-ring {
  fill: none;
  stroke: #2e6da2;
  stroke-width: 1;
  opacity: 0.85;
}
.atlas-node:focus-visible .node-core {
  stroke: #356c9b;
  stroke-width: 4;
}
.atlas-tools {
  position: absolute;
  bottom: 56px;
  left: 18px;
  display: flex;
  align-items: center;
  gap: 2px;
  background: #ffffffef;
  border: 1px solid #c8d9e8;
  border-radius: 8px;
  padding: 5px;
  color: #42678d;
}
.atlas-tools button {
  background: transparent;
  border: 0;
  color: #42678d;
  display: grid;
  place-items: center;
  padding: 5px;
  border-radius: 4px;
}
.atlas-tools button:hover {
  background: #e5effa;
}
.atlas-tools span {
  font-size: 10px;
  min-width: 37px;
  text-align: center;
}
.atlas-tools label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  border-left: 1px solid #c8d9e8;
  margin-left: 5px;
  padding: 0 7px;
}
.atlas-tools input {
  accent-color: #2563eb;
}
.atlas-legend {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 13px;
  flex-wrap: wrap;
  padding: 13px 20px;
  background: #ffffffd9;
  border-top: 1px solid #dbe5ef;
}
.atlas-legend > span {
  font-size: 10px;
  color: #536b87;
  display: flex;
  gap: 5px;
  align-items: center;
}
.atlas-legend i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.atlas-legend small {
  font-size: 9px;
  color: #627e9f;
  margin-left: auto;
}
.atlas-detail {
  background: #fff;
  border-left: 1px solid #e1e8f2;
  overflow: auto;
  padding: 22px 20px;
}
.detail-kicker {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: #7187a6;
}
.detail-kicker span {
  margin-left: auto;
  color: #518d78;
  background: #eef8f3;
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 9px;
}
.atlas-detail h2 {
  font-size: 21px;
  color: #1c3658;
  margin: 13px 0 15px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.detail-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 17px;
}
.detail-metrics span {
  color: #8190a5;
  font-size: 9px;
  background: #f4f7fb;
  padding: 6px 7px;
  border-radius: 4px;
}
.detail-metrics strong {
  font-size: 12px;
  color: #46678e;
  margin-right: 2px;
}
.detail-description {
  font-size: 12px;
  line-height: 1.85;
  color: #697c96;
  margin-bottom: 10px;
}
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 15px 0 20px;
}
.detail-actions button,
.atlas-source button,
.back-entity {
  display: flex;
  align-items: center;
  gap: 5px;
  background: #f5f8fd;
  color: #4971a5;
  border: 1px solid #e2eaf5;
  border-radius: 6px;
  padding: 8px;
  font-size: 10px;
}
.atlas-detail h3 {
  font-size: 12px;
  color: #3b5473;
  margin: 23px 0 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.atlas-detail h3 span {
  font-size: 10px;
  color: #8b9cb2;
  font-weight: 400;
}
.source-scope {
  font-size: 10px;
  line-height: 1.8;
  color: #8a98ad;
  margin-bottom: 12px;
}
.atlas-source {
  border: 1px solid #e4ebf4;
  border-radius: 7px;
  margin: 8px 0;
  background: #fafcff;
}
.atlas-source summary {
  font-size: 11px;
  color: #58769b;
  padding: 10px;
  cursor: pointer;
  line-height: 1.6;
}
.atlas-source :deep(.markdown-text) {
  font-size: 11px;
  line-height: 1.8;
  padding: 0 10px;
  color: #6a7c96;
}
.atlas-source :deep(.markdown-heading) {
  font-size: 12px;
}
.atlas-source :deep(pre) {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.atlas-source button {
  margin: 10px;
}
.relation-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px;
  text-align: left;
  width: 100%;
  background: #fff;
  border: 0;
  border-bottom: 1px solid #edf1f7;
  padding: 10px 0;
  color: #577395;
}
.relation-row span {
  font-size: 11px;
}
.relation-row small {
  font-size: 9px;
  color: #99a7b9;
  grid-column: 1;
  line-height: 1.6;
}
.relation-row svg {
  grid-column: 2;
  grid-row: 1/3;
  align-self: center;
}
.edge-keywords {
  font-size: 10px;
  color: #9a8055;
  padding: 9px;
  background: #fffbf3;
  line-height: 1.7;
  border-radius: 5px;
}
.back-entity {
  margin-top: 15px;
}
.atlas-footnote {
  font-size: 10px;
  color: #8a98ac;
  line-height: 1.8;
  padding: 12px 0;
}
.atlas-footnote > span {
  color: #57779e;
  margin-right: 12px;
  font-weight: 600;
}
.empty-graph {
  fill: #60758f;
  font-size: 16px;
}
.atlas-heading-actions {
  display: flex;
  align-items: center;
  gap: 20px;
}
.atlas-focus-toggle,
.atlas-close-detail {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  border: 1px solid #cad9ec;
  border-radius: 7px;
  padding: 9px 11px;
  background: #edf4ff;
  color: #345f93;
  font-size: 12px;
}
.atlas-close-detail {
  margin: -7px 0 16px auto;
  padding: 6px 9px;
  background: #f6f9fd;
  font-size: 11px;
}
@media (min-width: 1600px) {
  .atlas-workspace {
    grid-template-columns: minmax(0, 1fr) 340px;
  }
  .atlas-detail {
    padding: 25px;
  }
  .atlas-caption small {
    max-width: none;
  }
}
@media (max-width: 1100px) {
  .graph-explorer {
    padding: 20px;
  }
  .atlas-workspace {
    grid-template-columns: minmax(0, 1fr) 260px;
  }
  .atlas-totals {
    gap: 17px;
  }
  .atlas-heading-actions {
    gap: 12px;
  }
  .explorer-heading {
    flex-wrap: wrap;
  }
  .atlas-totals strong {
    font-size: 24px;
  }
  .atlas-caption {
    flex-direction: column;
  }
  .atlas-caption small {
    text-align: left;
  }
  .atlas-legend {
    gap: 8px;
  }
  .atlas-legend small {
    display: none;
  }
}
@media (max-width: 760px) {
  .explorer-heading {
    align-items: flex-start;
  }
  .atlas-totals {
    gap: 10px;
  }
  .atlas-totals strong {
    font-size: 19px;
  }
  .atlas-totals span {
    font-size: 9px;
  }
  .explorer-heading h1 {
    font-size: 20px;
  }
  .eyebrow,
  .explorer-heading p {
    display: none;
  }
  .atlas-search {
    flex-wrap: wrap;
  }
  .atlas-search > label {
    flex-basis: 100%;
  }
  .atlas-workspace {
    display: flex;
    flex-direction: column;
    height: auto;
  }
  .atlas-canvas {
    height: 520px;
  }
  .atlas-detail {
    max-height: 400px;
    border-left: 0;
  }
  .graph-explorer {
    padding: 16px;
  }
  .atlas-caption small {
    max-width: none;
  }
}
.atlas-workspace:not(.details-open) {
  grid-template-columns: minmax(0, 1fr);
}
.graph-explorer.focus-mode {
  position: fixed;
  inset: 0;
  z-index: 1000;
  width: 100vw;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 14px;
}
.focus-mode .explorer-heading {
  flex-shrink: 0;
  margin-bottom: 12px;
  gap: 12px;
}
.focus-mode .explorer-heading h1 {
  font-size: 18px;
  margin: 0;
}
.focus-mode .eyebrow,
.focus-mode .explorer-heading p {
  display: none;
}
.focus-mode .atlas-totals strong {
  font-size: 20px;
}
.focus-mode .atlas-totals span {
  font-size: 9px;
}
.focus-mode .atlas-search,
.focus-mode .atlas-topics,
.focus-mode .atlas-footnote {
  flex-shrink: 0;
}
.focus-mode .atlas-search > label {
  flex-basis: auto;
}
.focus-mode .atlas-topics {
  padding: 10px 0;
}
.focus-mode .atlas-workspace {
  display: grid;
  position: relative;
  flex: 1;
  min-height: 0;
  height: auto;
}
.focus-mode .atlas-workspace.details-open {
  grid-template-columns: minmax(0, 1fr) 285px;
}
.focus-mode .atlas-canvas {
  min-height: 0;
  height: 100%;
}
.focus-mode .atlas-detail {
  max-height: none;
}
.focus-mode .atlas-footnote {
  padding: 7px 0 0;
  font-size: 9px;
}
@media (max-width: 600px) {
  .focus-mode .atlas-heading-actions {
    flex: 1;
    justify-content: space-between;
  }
  .focus-mode .atlas-workspace.details-open {
    grid-template-columns: minmax(0, 1fr);
  }
  .focus-mode .atlas-detail {
    position: absolute;
    inset: 0 0 0 auto;
    width: min(90%, 300px);
    z-index: 2;
    box-shadow: -8px 0 25px #07132150;
  }
}
</style>
