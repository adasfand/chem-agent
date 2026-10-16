<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useId, watch } from 'vue'
import { ZoomIn, ZoomOut, Maximize2, X, Network } from '@lucide/vue'
import { graphLabelIds, runGraph } from '../utils/runShowcase'
import { adjacentIds, fitGraphView, nodeColor } from '../utils/graphExplorer'
import { parts, sourceIds, entityTypeLabel, type RetrievalRecord } from '../utils/retrieval'
import GraphSources from './GraphSources.vue'

const props = defineProps<{
  entities: RetrievalRecord[]
  relationships: RetrievalRecord[]
  sources: RetrievalRecord[]
  hits: RetrievalRecord[]
  highlightIds?: string[]
  expanded?: boolean
  compact?: boolean
  selectedId?: string
}>()
const emit = defineEmits<{ select: [id: string] }>()
const graph = computed(() => runGraph(props.entities, props.relationships))
const canvas = ref<HTMLDivElement>()
const viewport = ref({ width: 900, height: 520 })
const svg = ref<SVGSVGElement>()
const uid = useId()
const selected = ref('')
const edgeIndex = ref<number | null>(null)
const details = ref(false)
const labels = ref(false)
const zoom = ref(1)
const pan = ref({ x: 0, y: 0 })
const drag = ref<{ x: number; y: number; px: number; py: number }>()
const fitted = computed(() =>
  fitGraphView(graph.value.nodes, viewport.value.width, viewport.value.height),
)
const neighbors = computed(() => adjacentIds(graph.value, selected.value))
const activeNode = computed(() => graph.value.nodes.find((node) => node.id === selected.value))
const activeEdge = computed(() => graph.value.edges.find((edge) => edge.index === edgeIndex.value))
const detail = computed(
  () => activeEdge.value?.data || props.entities[activeNode.value?.index ?? -1],
)
const detailTitle = computed(() =>
  activeEdge.value
    ? `${activeEdge.value.from.name} ↔ ${activeEdge.value.to.name}`
    : activeNode.value?.name,
)
const labelIds = computed(() =>
  graphLabelIds(
    graph.value.nodes,
    selected.value,
    fitted.value.scale * zoom.value,
    (props.compact ? 10 : 12) * Math.max(1, fitted.value.scale) * zoom.value,
    props.compact ? 8 : 18,
  ),
)
const endpointCount = computed(
  () => props.entities.filter((item) => item.relationship_endpoint).length,
)
const types = computed(() => [...new Set(graph.value.nodes.map((node) => node.type))])
function reset() {
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
}
function select(id: string) {
  selected.value = id
  edgeIndex.value = null
  details.value = !props.compact
  emit('select', id)
}
function selectEdge(index: number) {
  edgeIndex.value = index
  details.value = !props.compact
  if (props.compact) {
    const edge = graph.value.edges.find((item) => item.index === index)
    if (edge) emit('select', edge.from.id)
  }
}
function changeZoom(value: number) {
  zoom.value = Math.max(0.5, Math.min(3, zoom.value + value))
}
function pointerDown(event: PointerEvent) {
  if ((event.target as Element).closest('[data-interactive]')) return
  drag.value = { x: event.clientX, y: event.clientY, px: pan.value.x, py: pan.value.y }
  svg.value?.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!drag.value || !svg.value) return
  const scale = viewport.value.width / svg.value.getBoundingClientRect().width
  pan.value = {
    x: drag.value.px + (event.clientX - drag.value.x) * scale,
    y: drag.value.py + (event.clientY - drag.value.y) * scale,
  }
}
watch(
  () => props.entities,
  () => {
    selected.value =
      props.selectedId || [...graph.value.nodes].sort((a, b) => b.degree - a.degree)[0]?.id || ''
    edgeIndex.value = null
    details.value = false
    reset()
  },
  { immediate: true },
)
watch(
  () => props.selectedId,
  (id) => {
    if (id !== undefined && id !== selected.value) {
      selected.value = id
      edgeIndex.value = null
      details.value = !props.compact
    }
  },
)
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) viewport.value = { width: entry.contentRect.width, height: entry.contentRect.height }
  })
  if (canvas.value) observer.observe(canvas.value)
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <section class="run-graph" :class="{ 'show-detail': details, compact }" aria-label="演示知识网络">
    <div ref="canvas" class="run-graph-canvas">
      <div class="run-graph-caption">
        <span>
          <i />
          {{ expanded ? '关联知识网络' : '本轮实际检索' }}
        </span>
        <strong>
          {{ graph.nodes.length }}
          <small>实体</small>
          / {{ graph.edges.length }}
          <small>图内关系</small>
        </strong>
        <small v-if="endpointCount">其中 {{ endpointCount }} 个来自本轮关系端点</small>
        <small v-if="graph.omitted">另有 {{ graph.omitted }} 条返回关系的端点未包含在图中</small>
      </div>
      <svg
        ref="svg"
        :viewBox="`0 0 ${viewport.width} ${viewport.height}`"
        role="group"
        aria-label="可交互知识网络"
        @pointerdown="pointerDown"
        @pointermove="pointerMove"
        @pointerup="drag = undefined"
        @pointercancel="drag = undefined"
        @wheel.prevent="changeZoom($event.deltaY > 0 ? -0.1 : 0.1)"
      >
        <defs>
          <pattern :id="`${uid}-grid`" width="30" height="30" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.7" fill="#c9dcea" />
          </pattern>
          <radialGradient :id="`${uid}-glow`">
            <stop offset="0" stop-color="#d9ecfa" stop-opacity="0.65" />
            <stop offset="1" stop-color="#eef7fc" stop-opacity="0" />
          </radialGradient>
        </defs>
        <rect :width="viewport.width" :height="viewport.height" :fill="`url(#${uid}-grid)`" />
        <ellipse
          :cx="viewport.width / 2"
          :cy="viewport.height / 2"
          :rx="viewport.width / 2"
          :ry="viewport.height / 2"
          :fill="`url(#${uid}-glow)`"
        />
        <g
          :transform="`translate(${fitted.offsetX + pan.x} ${fitted.offsetY + pan.y}) scale(${fitted.scale * zoom}) translate(${-fitted.centerX} ${-fitted.centerY})`"
        >
          <g
            v-for="edge in graph.edges"
            :key="edge.index"
            class="run-network-edge"
            :class="{
              lit: edge.from.id === selected || edge.to.id === selected,
              chosen: edgeIndex === edge.index,
            }"
          >
            <line :x1="edge.from.x" :y1="edge.from.y" :x2="edge.to.x" :y2="edge.to.y" />
            <line
              class="edge-target"
              data-interactive="edge"
              :x1="edge.from.x"
              :y1="edge.from.y"
              :x2="edge.to.x"
              :y2="edge.to.y"
              role="button"
              tabindex="0"
              :aria-label="`查看本轮关系 ${edge.from.name} 与 ${edge.to.name}`"
              @click="selectEdge(edge.index)"
              @keydown.enter="selectEdge(edge.index)"
              @keydown.space.prevent="selectEdge(edge.index)"
            />
          </g>
          <g
            v-for="node in graph.nodes"
            :key="node.index"
            data-interactive="node"
            class="run-network-node"
            :class="{ selected: selected === node.id, neighbor: neighbors.has(node.id) }"
            :style="{ '--node-color': nodeColor(node.type) }"
            role="button"
            tabindex="0"
            :aria-label="`查看本轮实体 ${node.name}`"
            :aria-pressed="selected === node.id"
            @click="select(node.id)"
            @keydown.enter="select(node.id)"
            @keydown.space.prevent="select(node.id)"
          >
            <circle class="node-halo" :cx="node.x" :cy="node.y" :r="node.radius + 12" />
            <circle class="node-body" :cx="node.x" :cy="node.y" :r="node.radius" />
            <circle
              v-if="highlightIds?.includes(node.id)"
              class="returned-ring"
              :cx="node.x"
              :cy="node.y"
              :r="node.radius + 5"
            />
            <text
              v-if="labels || labelIds.has(node.id)"
              :x="node.x"
              :y="node.y + node.radius + 17"
              text-anchor="middle"
              :style="{ fontSize: `${(compact ? 10 : 12) / Math.min(1, fitted.scale)}px` }"
            >
              {{ node.name.length > 14 ? node.name.slice(0, 13) + '…' : node.name }}
            </text>
            <title>{{ node.name }} · {{ entityTypeLabel(node.type) }}</title>
          </g>
        </g>
        <text
          v-if="!graph.nodes.length"
          :x="viewport.width / 2"
          :y="viewport.height / 2"
          text-anchor="middle"
          class="graph-placeholder"
        >
          本轮没有返回实体图谱
        </text>
      </svg>
      <div class="run-graph-controls">
        <button aria-label="缩小演示网络" @click="changeZoom(-0.15)"><ZoomOut :size="16" /></button>
        <span>{{ Math.round(zoom * 100) }}%</span>
        <button aria-label="放大演示网络" @click="changeZoom(0.15)"><ZoomIn :size="16" /></button>
        <button aria-label="适应演示网络" @click="reset"><Maximize2 :size="16" /></button>
        <label>
          <input v-model="labels" type="checkbox" />
          全部标签
        </label>
      </div>
      <div class="run-graph-legend">
        <span v-for="type in types" :key="type">
          <i :style="{ background: nodeColor(type) }" />
          {{ entityTypeLabel(type) }}
        </span>
        <small v-if="expanded">蓝环：本轮检索返回实体</small>
        <small v-else>点击节点或连线，查看关联原文</small>
      </div>
    </div>
    <aside v-if="details && detail" class="run-graph-detail" aria-label="演示图谱来源详情">
      <button class="detail-dismiss" aria-label="关闭实体详情" @click="details = false">
        <X :size="18" />
      </button>
      <span class="detail-eyebrow">
        <Network :size="14" />
        {{ activeEdge ? '关系说明' : entityTypeLabel(activeNode?.type || '') }}
      </span>
      <h3>{{ detailTitle }}</h3>
      <p v-for="part in parts(detail.description)" :key="part">{{ part }}</p>
      <h4>关联知识原文</h4>
      <GraphSources :ids="sourceIds(detail)" :sources="sources" :hits="hits" />
    </aside>
  </section>
</template>

<style scoped>
.run-graph.compact,
.compact .run-graph-canvas {
  min-height: 360px;
}
.compact .run-graph-caption {
  left: 14px;
  top: 14px;
}
.compact .run-graph-controls {
  left: 10px;
  bottom: 12px;
  gap: 5px;
}
.compact .run-graph-legend {
  display: none;
}
.run-graph {
  position: relative;
  display: flex;
  min-height: 420px;
  height: 100%;
  overflow: hidden;
  border: 1px solid #dbe5ef;
  border-radius: 14px;
  background: #f3f8fd;
}
.run-graph-canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 420px;
}
.run-graph-canvas > svg {
  position: absolute;
  width: 100%;
  height: 100%;
  touch-action: none;
  cursor: grab;
}
.run-graph-caption {
  position: absolute;
  left: 22px;
  top: 20px;
  z-index: 1;
  pointer-events: none;
  display: grid;
  gap: 7px;
  color: #203b56;
}
.run-graph-caption > span {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: #60758f;
}
.run-graph-caption i {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #248d6b;
  margin-right: 8px;
  box-shadow: 0 0 10px #248d6b33;
}
.run-graph-caption strong {
  font-size: 19px;
  font-weight: 500;
}
.run-graph-caption small {
  font-size: 10px;
  font-weight: 400;
  color: #60758f;
}
.run-network-edge line {
  stroke: #91acc3;
  stroke-width: 1;
  stroke-opacity: 0.5;
}
.run-network-edge.lit line {
  stroke: #278ba5;
  stroke-opacity: 0.85;
  stroke-width: 1.5;
}
.run-network-edge.chosen line {
  stroke: #b27b21;
  stroke-width: 2;
}
.run-network-edge .edge-target {
  stroke: transparent;
  stroke-width: 10;
  cursor: pointer;
}
.run-network-edge .edge-target:focus-visible {
  stroke: #356c9b80;
  outline: none;
}
.run-network-node {
  cursor: pointer;
}
.node-halo {
  fill: var(--node-color);
  opacity: 0.08;
}
.node-body {
  fill: var(--node-color);
  stroke: var(--node-color);
  stroke-width: 1;
}
.run-network-node.selected .node-body,
.run-network-node:focus-visible .node-body {
  stroke: #356c9b;
  stroke-width: 2.5;
  filter: drop-shadow(0 0 7px var(--node-color));
}
.run-network-node.selected .node-halo {
  opacity: 0.2;
}
.run-network-node text {
  fill: #35516d;
  paint-order: stroke;
  stroke: #f3f8fd;
  stroke-width: 3;
  stroke-linejoin: round;
  pointer-events: none;
}
.run-network-node.selected text {
  fill: #173853;
  font-weight: 600;
}
.returned-ring {
  fill: none;
  stroke: #2e6da2;
  stroke-width: 1;
  stroke-dasharray: 3 3;
}
.graph-placeholder {
  fill: #60758f;
  font-size: 14px;
}
.run-graph-controls {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 9px;
  bottom: 61px;
  left: 20px;
  padding: 7px;
  background: #ffffffef;
  border: 1px solid #c8d9e8;
  border-radius: 8px;
  font-size: 11px;
  color: #42678d;
}
.run-graph-controls button {
  display: grid;
  place-items: center;
  padding: 4px;
  border: 0;
  background: transparent;
  color: inherit;
  border-radius: 5px;
}
.run-graph-controls button:hover {
  background: #e5effa;
  color: #1d5f9e;
}
.run-graph-controls label {
  display: flex;
  gap: 5px;
  align-items: center;
  font-size: 10px;
}
.run-graph-legend {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  border-top: 1px solid #dbe5ef;
  padding: 12px 20px;
  color: #536b87;
  font-size: 10px;
  background: #ffffffd9;
}
.run-graph-legend i {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
}
.run-graph-legend small {
  font-size: 10px;
  color: #60758f;
}
.run-graph-detail {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: min(340px, 88%);
  z-index: 3;
  overflow: auto;
  padding: 25px 22px;
  background: #f8fbff;
  color: #23334b;
  border-left: 1px solid #c4d2e3;
  box-shadow: -18px 0 45px #1834511a;
}
.detail-dismiss {
  float: right;
  border: 0;
  padding: 3px;
  background: transparent;
}
.detail-eyebrow {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #4d6f96;
}
.run-graph-detail h3 {
  margin: 16px 0;
  font-size: 19px;
  overflow-wrap: anywhere;
}
.run-graph-detail > p {
  font-size: 12px;
  line-height: 1.9;
  margin-bottom: 10px;
}
.run-graph-detail h4 {
  margin: 20px 0 12px;
  font-size: 13px;
}
.run-graph-detail :deep(.graph-source) {
  padding: 10px 0;
  font-size: 11px;
  line-height: 1.8;
  border-bottom: 1px solid #d7e0eb;
}
.run-graph-detail :deep(summary) {
  cursor: pointer;
}
.run-graph-detail :deep(.markdown-text) {
  font-size: 12px;
}
@media (max-width: 600px) {
  .run-graph,
  .run-graph-canvas {
    min-height: 390px;
  }
  .run-graph-caption {
    left: 14px;
  }
  .run-graph-legend {
    padding: 10px 12px;
  }
}
</style>
