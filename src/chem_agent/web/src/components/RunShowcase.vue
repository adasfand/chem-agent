<script setup lang="ts">
import { computed, onUnmounted, ref, useId, watch } from 'vue'
import {
  Network,
  Workflow,
  ChartNoAxesCombined,
  Presentation,
  ArrowRight,
  ArrowLeft,
  X,
  Link2,
  BookOpen,
  Check,
  FileDown,
  LoaderCircle,
} from '@lucide/vue'
import type { Job } from '../types/api'
import { request, exportUrl } from '../services/api'
import type { GraphOverview } from '../utils/graphExplorer'
import { citationEvidence, executionNetwork, runQueries } from '../utils/runShowcase'
import {
  resultMetrics,
  summaryNumberText,
  numberText,
  statusLabels,
  assumptions,
} from '../utils/presentation'
import { text } from '../utils/retrieval'
import RunKnowledgeGraph from './RunKnowledgeGraph.vue'
import MarkdownText from './MarkdownText.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ job: Job }>()
const result = computed(() => props.job.result)
const queries = computed(() => runQueries(result.value))
const network = computed(() => executionNetwork(result.value))
const metrics = computed(() => resultMetrics(result.value))
const evidence = computed(() => citationEvidence(result.value))
const conditions = computed(() => assumptions(result.value))
const dialog = ref<HTMLDialogElement>()
const opened = ref(false)
const scene = ref(0)
const queryIndex = ref(0)
const query = computed(() => queries.value[queryIndex.value])
const mode = ref<'retrieved' | 'related'>('retrieved')
const anchor = ref('')
const expansion = ref<GraphOverview>()
const loading = ref(false)
const error = ref('')
const selectedStep = ref('')
const executionZoom = ref(false)
const activeStep = computed(() =>
  network.value.nodes.find((node) => node.id === selectedStep.value),
)
const titleId = useId()
const markerId = useId()
const scenes = [
  {
    title: '检索知识网络',
    short: '检索',
    icon: Network,
    description: '从本轮查询出发，沿实体关系追溯知识原文。',
  },
  {
    title: '工具执行与回用',
    short: '执行',
    icon: Workflow,
    description: '查看任务依赖，以及前序结果如何进入后续计算。',
  },
  {
    title: '结果与引用',
    short: '结果',
    icon: ChartNoAxesCombined,
    description: '核对计算数值、适用条件和实际引用的资料。',
  },
]
const successfulCalls = computed(
  () => result.value.calls.filter((call) => call.status === 'succeeded').length,
)
const graphEntities = computed(() =>
  mode.value === 'related' ? expansion.value?.entities || [] : query.value?.entities || [],
)
const graphRelationships = computed(() =>
  mode.value === 'related'
    ? expansion.value?.relationships || []
    : query.value?.relationships || [],
)
const graphSources = computed(() =>
  mode.value === 'related' ? expansion.value?.sources || [] : query.value?.sources || [],
)
const isOffline = computed(() => result.value.mode?.startsWith('offline'))
let requestId = 0
function resetQuery() {
  requestId++
  expansion.value = undefined
  mode.value = 'retrieved'
  loading.value = false
  error.value = ''
  anchor.value = text(query.value?.entities[0]?.name) || text(query.value?.entities[0]?.id)
}
watch(query, resetQuery, { immediate: true })
watch(
  () => props.job.job_id,
  () => {
    close()
    queryIndex.value = 0
    selectedStep.value = ''
  },
)
async function expand() {
  if (!anchor.value || loading.value) return
  const id = ++requestId
  loading.value = true
  error.value = ''
  mode.value = 'related'
  expansion.value = undefined
  try {
    const value = await request<GraphOverview>(
      `/api/knowledge-graph?query=${encodeURIComponent(anchor.value)}&limit=72`,
    )
    if (id !== requestId) return
    expansion.value = value
    if (value.state !== 'ready') error.value = value.message
    else if (!value.entities.length)
      error.value = '当前索引没有该实体的关联网络，请查看本轮检索记录。'
  } catch (cause) {
    if (id === requestId)
      error.value = cause instanceof Error ? cause.message : '关联网络读取失败。'
  } finally {
    if (id === requestId) loading.value = false
  }
}
function showRetrieved() {
  requestId++
  loading.value = false
  error.value = ''
  mode.value = 'retrieved'
}
function open() {
  scene.value = 0
  opened.value = true
  dialog.value?.showModal()
}
function close() {
  dialog.value?.close()
  opened.value = false
  requestId++
  loading.value = false
}
function changeScene(index: number) {
  scene.value = index
  selectedStep.value = ''
}
function openStep(id: string) {
  scene.value = 1
  selectedStep.value = id
}
const referencePath = (edge: (typeof network.value.edges)[number]) => {
  const x1 = edge.start.x + 176,
    y1 = edge.start.y + 36,
    x2 = edge.end.x,
    y2 = edge.end.y + 36
  return `M ${x1} ${y1} C ${x1 + 25} ${y1}, ${x2 - 25} ${y2}, ${x2} ${y2}`
}
const json = (value: unknown) => JSON.stringify(value, null, 2)
onUnmounted(() => {
  requestId++
})
</script>

<template>
  <section class="run-showcase-launch" aria-label="本轮流程演示入口">
    <div class="showcase-invitation">
      <span class="showcase-symbol"><Presentation :size="23" /></span>
      <div>
        <span class="showcase-overline">
          {{ job.result.status === 'completed' ? '本轮已完成' : statusLabels[job.result.status] }} ·
          过程可追溯
        </span>
        <h3>把这次问答，展开来看</h3>
        <p>
          {{ queries.length }} 次成功检索 · {{ successfulCalls }} 次成功工具调用 ·
          {{ network.referenceCount }} 处结果回用
        </p>
      </div>
    </div>
    <div class="showcase-launch-bottom">
      <span>
        <Network :size="13" />
        知识网络
        <i />
        <Workflow :size="13" />
        执行路径
        <i />
        <ChartNoAxesCombined :size="13" />
        结果与引用
      </span>
      <button @click="open">
        演示本轮流程
        <ArrowRight :size="15" />
      </button>
    </div>
  </section>
  <Teleport to="body">
    <dialog
      ref="dialog"
      class="run-showcase-dialog"
      :aria-labelledby="titleId"
      @close="opened = false"
      @cancel="close"
    >
      <template v-if="opened">
        <header class="showcase-header">
          <div class="showcase-title">
            <span class="showcase-brand">
              <Presentation :size="17" />
              CHEM AGENT
              <i>/</i>
              本轮演示
            </span>
            <h2 :id="titleId">知识如何成为可核验的结果</h2>
          </div>
          <div class="showcase-header-actions">
            <StatusBadge :status="result.status" />
            <button class="showcase-close" aria-label="关闭本轮演示" @click="close">
              <X :size="21" />
            </button>
          </div>
        </header>
        <nav class="showcase-scenes" aria-label="演示章节">
          <button
            v-for="(item, index) in scenes"
            :key="item.title"
            :aria-current="scene === index ? 'step' : undefined"
            :class="{ active: scene === index }"
            @click="changeScene(index)"
          >
            <span class="scene-number">0{{ index + 1 }}</span>
            <component :is="item.icon" :size="17" />
            <span>{{ item.title }}</span>
          </button>
        </nav>
        <main :key="scene" class="showcase-content">
          <div class="showcase-scene-heading">
            <div>
              <span class="showcase-overline">
                {{ isOffline ? '离线记录演示' : '基于本轮执行记录' }}
              </span>
              <p>{{ scenes[scene]?.description }}</p>
            </div>
            <details class="showcase-question">
              <summary>查看本轮问题</summary>
              <p>{{ result.question }}</p>
            </details>
          </div>
          <template v-if="scene === 0">
            <div v-if="query" class="showcase-querybar">
              <label v-if="queries.length > 1">
                查询
                <select v-model="queryIndex" aria-label="选择演示检索查询">
                  <option v-for="(item, index) in queries" :key="item.callId" :value="index">
                    {{ index + 1 }} · {{ item.query }}
                  </option>
                </select>
              </label>
              <p v-else>
                <span>
                  {{
                    query.mode === 'mix'
                      ? 'LightRAG 混合检索'
                      : query.mode === 'lexical'
                        ? '词法检索'
                        : '知识检索'
                  }}
                </span>
                {{ query.query }}
              </p>
            </div>
            <div class="showcase-graph-options">
              <button
                :class="{ active: mode === 'retrieved' }"
                :aria-pressed="mode === 'retrieved'"
                @click="showRetrieved"
              >
                本轮检索
              </button>
              <label v-if="query?.entities.length">
                从实体
                <select v-model="anchor" aria-label="关联网络起点">
                  <option
                    v-for="entity in query.entities"
                    :key="text(entity.id)"
                    :value="text(entity.name) || text(entity.id)"
                  >
                    {{ text(entity.name) || text(entity.id) }}
                  </option>
                </select>
                展开
              </label>
              <button
                v-if="query?.entities.length"
                class="expand-related"
                :class="{ active: mode === 'related' }"
                :disabled="loading || !anchor || anchor.length > 100"
                @click="expand"
              >
                <LoaderCircle v-if="loading" :size="14" class="spinning" />
                <Network v-else :size="14" />
                {{ loading ? '读取索引…' : '拓展关联网络' }}
              </button>
            </div>
            <p v-if="mode === 'related'" class="showcase-scope">
              当前展示本轮实体在现有索引中的关联拓展，蓝环标出本轮返回实体；拓展内容不增加回答引用。
            </p>
            <p v-else class="showcase-scope">
              实体与连线来自该次检索返回；节点数量随查询变化。点击节点或连线查看来源。
            </p>
            <template v-if="mode === 'retrieved'">
              <p v-for="notice in query?.notices" :key="notice" class="showcase-scope">
                {{ notice }}
              </p>
            </template>
            <p v-if="error" class="showcase-error" role="alert">{{ error }}</p>
            <div v-if="loading" class="showcase-loading" role="status">
              <LoaderCircle :size="26" class="spinning" />
              正在展开真实索引关系…
            </div>
            <div v-else class="showcase-network-wrap">
              <RunKnowledgeGraph
                :entities="graphEntities"
                :relationships="graphRelationships"
                :sources="graphSources"
                :hits="query?.hits || []"
                :expanded="mode === 'related'"
                :highlight-ids="
                  mode === 'related' ? query?.entities.map((item) => text(item.id)) : []
                "
              />
            </div>
            <div class="showcase-hit-strip">
              <span>
                <BookOpen :size="14" />
                本轮命中 {{ query?.hits.length || 0 }}
              </span>
              <span v-if="!query?.hits.length">
                {{
                  result.status === 'needs_input'
                    ? '等待必要参数，尚未形成检索依据。'
                    : '该记录没有可展示的命中片段。'
                }}
              </span>
              <button v-for="hit in query?.hits" :key="text(hit.chunk_id)" @click="changeScene(2)">
                {{ text(hit.title) }}
                <Check v-if="result.citations.includes(text(hit.chunk_id))" :size="12" />
              </button>
            </div>
          </template>
          <template v-else-if="scene === 1">
            <div class="showcase-stat-row">
              <div>
                <strong>{{ network.nodes.length }}</strong>
                <span>登记或调用步骤</span>
              </div>
              <div>
                <strong>{{ successfulCalls }}</strong>
                <span>成功工具调用</span>
              </div>
              <div>
                <strong>{{ network.referenceCount }}</strong>
                <span>实际结果回用</span>
              </div>
              <div>
                <strong>{{ result.tool_batches?.length ?? '—' }}</strong>
                <span>已记录响应批次</span>
              </div>
            </div>
            <div class="execution-stage" aria-label="演示执行依赖图">
              <p class="execution-legend">
                <span>
                  <i />
                  计划依赖
                </span>
                <span>
                  <i class="reference" />
                  实际结果回用
                </span>
                <small>点击步骤查看实际输入与输出</small>
                <button :aria-pressed="executionZoom" @click="executionZoom = !executionZoom">
                  {{ executionZoom ? '适应宽度' : '放大步骤图' }}
                </button>
              </p>
              <div
                v-if="network.nodes.length"
                class="execution-scroll"
                tabindex="0"
                aria-label="执行依赖画布，可横向滚动"
              >
                <svg
                  :viewBox="`0 0 ${network.width} ${network.height}`"
                  :style="{ minWidth: executionZoom ? `${network.width}px` : '0' }"
                  role="group"
                  aria-label="本轮工具依赖与结果回用"
                >
                  <defs>
                    <marker
                      :id="markerId"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="5"
                      markerHeight="5"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#78aecb" />
                    </marker>
                  </defs>
                  <path
                    v-for="edge in network.edges"
                    :key="`${edge.from}:${edge.to}`"
                    :d="referencePath(edge)"
                    class="execution-link"
                    :class="{ reference: edge.references.length }"
                    :marker-end="`url(#${markerId})`"
                  >
                    <title>
                      {{ edge.from }} → {{ edge.to }} ·
                      {{
                        edge.references.length
                          ? edge.references.map((item) => item.ref).join('、')
                          : '计划依赖'
                      }}
                    </title>
                  </path>
                  <g
                    v-for="node in network.nodes"
                    :key="node.id"
                    class="execution-node"
                    :class="[node.status, { selected: selectedStep === node.id }]"
                    role="button"
                    tabindex="0"
                    :aria-label="`查看步骤 ${node.id} ${node.title}`"
                    :aria-pressed="selectedStep === node.id"
                    @click="selectedStep = node.id"
                    @keydown.enter="selectedStep = node.id"
                    @keydown.space.prevent="selectedStep = node.id"
                  >
                    <rect :x="node.x" :y="node.y" width="176" height="72" rx="10" />
                    <circle :cx="node.x + 18" :cy="node.y + 19" r="3" />
                    <text class="execution-step-id" :x="node.x + 28" :y="node.y + 23">
                      {{ node.id }} · {{ statusLabels[node.status] || node.status }}
                    </text>
                    <text class="execution-node-title" :x="node.x + 15" :y="node.y + 50">
                      {{ node.title }}
                    </text>
                  </g>
                </svg>
              </div>
              <p v-else class="showcase-empty">
                {{
                  result.status === 'needs_input'
                    ? '本轮等待补充必要参数。补参后，新的执行记录会显示在同一对话中。'
                    : '本轮没有登记或调用的工具步骤。'
                }}
              </p>
              <p class="execution-footnote">
                连线表示依赖与字段回用；同列节点不表示并行执行。真实调用按响应批次顺序处理。
              </p>
            </div>
            <section v-if="activeStep" class="showcase-step-detail" aria-label="演示步骤详情">
              <header>
                <div>
                  <small>{{ activeStep.id }}</small>
                  <h3>{{ activeStep.title }}</h3>
                </div>
                <StatusBadge :status="activeStep.status" />
              </header>
              <p>{{ activeStep.goal }}</p>
              <p v-if="!activeStep.calls.length">该步骤尚无实际工具调用。</p>
              <details
                v-for="(call, index) in activeStep.calls"
                :key="call.call_id"
                :open="index === activeStep.calls.length - 1"
              >
                <summary>
                  调用 {{ index + 1 }} · {{ statusLabels[call.status] || call.status }}
                </summary>
                <div v-if="call.input_refs?.length" class="showcase-references">
                  <span v-for="(item, refIndex) in call.input_refs" :key="refIndex">
                    <Link2 :size="13" />
                    <code>{{ item.ref }}</code>
                    →
                    <code>{{ item.argument }}</code>
                  </span>
                </div>
                <div class="showcase-io">
                  <div>
                    <h4>实际输入</h4>
                    <pre>{{ json(call.arguments) || '未形成实际输入' }}</pre>
                  </div>
                  <div>
                    <h4>{{ call.error ? '调用错误' : '实际输出' }}</h4>
                    <pre>{{ json(call.error ?? call.output) || '未形成输出' }}</pre>
                  </div>
                </div>
              </details>
            </section>
            <div v-else-if="network.referenceCount" class="showcase-reference-list">
              <h3>
                <Link2 :size="16" />
                前序结果如何继续计算
              </h3>
              <button
                v-for="edge in network.edges.filter((item) => item.references.length)"
                :key="`${edge.from}:${edge.to}`"
                @click="selectedStep = edge.to"
              >
                <span>
                  {{ edge.start.title }}
                  <ArrowRight :size="13" />
                  {{ edge.end.title }}
                </span>
                <small>
                  {{ edge.references.map((item) => `${item.ref} → ${item.argument}`).join('；') }}
                </small>
              </button>
            </div>
          </template>
          <template v-else>
            <p v-if="result.status !== 'completed'" class="showcase-scope">
              本轮状态：{{
                statusLabels[result.status]
              }}。以下只展示已成功步骤的结果；未完成的计算不会展示为成功。
            </p>
            <div v-if="metrics.length" class="showcase-results">
              <article
                v-for="(metric, index) in metrics"
                :key="`${metric.step}:${index}`"
                :style="{ animationDelay: `${index * 45}ms` }"
              >
                <span>{{ metric.label }}</span>
                <small v-if="metric.valueLabel">{{ metric.valueLabel }}</small>
                <strong>
                  {{ summaryNumberText(metric.value) }}
                  <small>{{ metric.unit }}</small>
                </strong>
                <dl v-if="metric.details?.length">
                  <div v-for="(item, i) in metric.details" :key="i">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ numberText(item.value) }} {{ item.unit }}</dd>
                  </div>
                </dl>
                <button @click="openStep(metric.step)">
                  {{ metric.step }} · 查看计算来源
                  <ArrowRight :size="12" />
                </button>
              </article>
            </div>
            <section class="showcase-answer">
              <h3>
                {{
                  result.status === 'needs_input'
                    ? '需要补充的条件'
                    : metrics.length
                      ? '计算结论与说明'
                      : '知识答复'
                }}
              </h3>
              <MarkdownText :text="result.answer || '本记录未保存答复。'" />
              <details v-if="conditions.length">
                <summary>计算适用条件 · {{ conditions.length }}</summary>
                <ul>
                  <li v-for="condition in conditions" :key="condition">{{ condition }}</li>
                </ul>
              </details>
            </section>
            <section class="showcase-evidence">
              <header>
                <h3>
                  <BookOpen :size="17" />
                  知识来源与回答引用
                </h3>
                <span>
                  {{ evidence.filter((item) => item.cited).length }} /
                  {{ evidence.length }} 个命中片段被引用
                </span>
              </header>
              <p v-if="!evidence.length">本轮没有检索依据记录。</p>
              <details v-for="item in evidence" :key="item.chunk_id">
                <summary>
                  <span>{{ item.title }}</span>
                  <span class="showcase-evidence-tags">
                    <i v-if="item.inContext">已匹配模型输入</i>
                    <b :class="{ cited: item.cited }">
                      {{ item.cited ? '回答已引用' : '仅检索命中' }}
                    </b>
                  </span>
                </summary>
                <MarkdownText :text="item.text" />
                <p class="showcase-source">来源：{{ item.source }}</p>
              </details>
              <p class="showcase-citation-note">
                引用标记来自本轮记录；具体结论请结合原文核对。关联网络不计入这里的引用。
              </p>
            </section>
          </template>
        </main>
        <footer class="showcase-footer">
          <div>
            <span>运行记录</span>
            <code>{{ result.run_id || '未记录编号' }}</code>
          </div>
          <div class="showcase-navigation">
            <button v-if="scene > 0" aria-label="上一幕" @click="changeScene(scene - 1)">
              <ArrowLeft :size="15" />
              上一幕
            </button>
            <button v-if="scene < 2" class="next-scene" @click="changeScene(scene + 1)">
              下一幕：{{ scenes[scene + 1]?.short }}
              <ArrowRight :size="15" />
            </button>
            <a v-else :href="exportUrl(job.job_id, 'report.md')" download>
              <FileDown :size="15" />
              导出本轮报告
            </a>
          </div>
        </footer>
      </template>
    </dialog>
  </Teleport>
</template>

<style scoped>
.run-showcase-launch {
  margin: 18px 0 22px;
  border: 1px solid #dbe5ef;
  border-radius: 12px;
  overflow: hidden;
  color: #1e314b;
  background: radial-gradient(ellipse at 100% 0%, #e8f3ff 0%, transparent 65%), #f4f9ff;
}
.showcase-invitation {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 19px 20px;
}
.showcase-symbol {
  display: grid;
  place-items: center;
  width: 47px;
  height: 47px;
  flex-shrink: 0;
  border: 1px solid #c1d7e8;
  border-radius: 13px;
  color: #1d5f9e;
  background: #e5f1ff;
  box-shadow: 0 0 28px #57b9db18;
}
.showcase-overline {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: #60758f;
}
.showcase-invitation h3 {
  font-size: 17px;
  font-weight: 550;
  margin: 7px 0;
}
.showcase-invitation p {
  font-size: 11px;
  line-height: 1.7;
  color: #536b87;
}
.showcase-launch-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 16px;
  border-top: 1px solid #dbe7f2;
  background: #edf5fb;
}
.showcase-launch-bottom > span {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 10px;
  color: #536b87;
}
.showcase-launch-bottom i {
  width: 12px;
  height: 1px;
  background: #53738c;
  margin: 0 3px;
}
.showcase-launch-bottom button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  flex-shrink: 0;
  background: #2563eb;
  color: #ffffff;
  border: 0;
  border-radius: 6px;
  padding: 9px 12px;
  font-size: 12px;
  font-weight: 600;
}
.showcase-launch-bottom button:hover {
  background: #1d4ed8;
}
.run-showcase-dialog {
  position: fixed;
  inset: 0;
  margin: 0;
  width: 100vw;
  max-width: none;
  height: 100dvh;
  max-height: none;
  padding: 0;
  border: 0;
  color: #1e314b;
  background: #f5f8fc;
  color-scheme: light;
}
.run-showcase-dialog[open] {
  display: flex;
  flex-direction: column;
}
.run-showcase-dialog::backdrop {
  background: #050a14cc;
}
.showcase-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 16px;
  padding: 22px 32px 20px;
  border-bottom: 1px solid #dbe5ef;
  background: radial-gradient(ellipse at top right, #e8f3ff, transparent 65%);
}
.showcase-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 10px;
  letter-spacing: 0.13em;
  color: #60758f;
}
.showcase-brand i {
  font-style: normal;
  color: #4e637d;
}
.showcase-title h2 {
  margin-top: 9px;
  font-size: 23px;
  font-weight: 550;
  letter-spacing: 0.03em;
}
.showcase-header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.showcase-close {
  display: grid;
  place-items: center;
  border: 1px solid #dbe5ef;
  border-radius: 8px;
  background: #f1f6fb;
  color: #33465e;
  padding: 8px;
}
.showcase-close:hover {
  background: #e5effa;
}
.showcase-scenes {
  display: flex;
  gap: 6px;
  padding: 0 32px;
  border-bottom: 1px solid #dbe5ef;
  flex-shrink: 0;
}
.showcase-scenes button {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 19px 18px;
  background: transparent;
  color: #60758f;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 12px;
}
.showcase-scenes button.active {
  color: #1d5f9e;
  border-bottom-color: #2563eb;
  background: linear-gradient(0deg, #dcecfb80, transparent);
}
.scene-number {
  font-size: 10px;
  opacity: 0.55;
  margin-right: 3px;
}
.showcase-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 22px 32px 30px;
  animation: scene-in 250ms ease-out;
}
@keyframes scene-in {
  from {
    opacity: 0;
    transform: translateY(7px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.showcase-scene-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}
.showcase-scene-heading > div > p {
  margin-top: 6px;
  font-size: 12px;
  color: #536b87;
  line-height: 1.7;
}
.showcase-question {
  position: relative;
  flex-shrink: 0;
  font-size: 11px;
}
.showcase-question summary {
  cursor: pointer;
  color: #42678d;
}
.showcase-question > p {
  position: absolute;
  right: 0;
  top: 24px;
  width: min(480px, 80vw);
  max-height: 240px;
  overflow: auto;
  padding: 18px;
  border: 1px solid #dbe5ef;
  border-radius: 9px;
  background: #ffffff;
  z-index: 10;
  line-height: 1.9;
  box-shadow: 0 15px 45px #1834511a;
}
.showcase-querybar {
  margin-bottom: 15px;
  padding-left: 12px;
  border-left: 2px solid #77a6d3;
  color: #1e314b;
}
.showcase-querybar p {
  font-size: 12px;
  line-height: 1.7;
}
.showcase-querybar p > span {
  color: #42678d;
  margin-right: 13px;
  font-size: 10px;
}
.showcase-querybar label {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
}
.showcase-querybar select {
  flex: 1;
  min-width: 0;
}
.showcase-graph-options {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.showcase-graph-options button,
.showcase-graph-options select,
.showcase-querybar select {
  background: #ffffff;
  color: #536b87;
  border: 1px solid #dbe5ef;
  border-radius: 7px;
  padding: 8px 10px;
  font-size: 11px;
}
.showcase-graph-options label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #60758f;
}
.showcase-graph-options select {
  max-width: 170px;
}
.showcase-graph-options .active {
  color: #1d5f9e;
  border-color: #77a6d3;
  background: #e5f2ff;
}
.expand-related {
  display: flex;
  align-items: center;
  gap: 6px;
}
.showcase-scope {
  font-size: 10px;
  line-height: 1.7;
  color: #60758f;
  margin-bottom: 13px;
}
.showcase-network-wrap {
  height: min(58vh, 640px);
  min-height: 420px;
}
.showcase-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 420px;
  color: #42678d;
  font-size: 13px;
  border: 1px solid #dbe5ef;
  border-radius: 14px;
}
.showcase-error {
  padding: 12px;
  border: 1px solid #a65c5c;
  background: #eef4fa;
  color: #b24141;
  font-size: 12px;
  margin: 12px 0;
}
.showcase-hit-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
  font-size: 10px;
  color: #60758f;
}
.showcase-hit-strip > span:first-child {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-right: 4px;
}
.showcase-hit-strip button {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border: 1px solid #dbe5ef;
  border-radius: 20px;
  background: #f0f7fc;
  color: #536b87;
  font-size: 10px;
}
.showcase-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin: 5px 0 22px;
}
.showcase-stat-row > div {
  display: grid;
  gap: 7px;
  border-left: 1px solid #dbe5ef;
  padding-left: 17px;
}
.showcase-stat-row strong {
  font-size: 31px;
  font-weight: 450;
  color: #16607c;
  font-variant-numeric: tabular-nums;
}
.showcase-stat-row span {
  font-size: 10px;
  color: #60758f;
}
.execution-stage {
  border: 1px solid #dbe5ef;
  border-radius: 13px;
  overflow: hidden;
  background: radial-gradient(ellipse at center, #f4faff, #edf5fb 72%);
}
.execution-legend {
  display: flex;
  align-items: center;
  gap: 17px;
  padding: 18px 20px 5px;
  color: #60758f;
  font-size: 10px;
}
.execution-legend > span {
  display: flex;
  align-items: center;
  gap: 7px;
}
.execution-legend i {
  width: 20px;
  border-top: 1px dashed #647e99;
}
.execution-legend i.reference {
  border-top: 2px solid #168d89;
}
.execution-legend small {
  font-size: 10px;
  margin-left: auto;
}
.execution-legend button {
  padding: 5px 8px;
  color: #42678d;
  background: #ffffff;
  border: 1px solid #dbe5ef;
  border-radius: 5px;
  font-size: 10px;
}
.execution-scroll {
  overflow: auto;
}
.execution-scroll svg {
  display: block;
  width: 100%;
  max-height: 480px;
}
.execution-link {
  fill: none;
  stroke: #647e99;
  stroke-width: 1.3;
  stroke-dasharray: 4 5;
}
.execution-link.reference {
  stroke: #168d89;
  stroke-width: 2;
  stroke-dasharray: none;
  filter: drop-shadow(0 0 3px #7cebdc30);
}
.execution-node {
  cursor: pointer;
}
.execution-node rect {
  fill: #ffffff;
  stroke: #bdd1e1;
  stroke-width: 1;
}
.execution-node.succeeded rect {
  stroke: #3a9f99;
}
.execution-node.selected rect,
.execution-node:focus-visible rect {
  stroke: #2a879a;
  stroke-width: 2;
  fill: #e9f5fb;
}
.execution-node circle {
  fill: #647e99;
}
.execution-node.succeeded circle {
  fill: #248d6b;
}
.execution-node.failed circle {
  fill: #b24141;
}
.execution-node.running circle {
  fill: #b27b21;
}
.execution-step-id {
  fill: #647e99;
  font-size: 10px;
}
.execution-node-title {
  fill: #1e314b;
  font-size: 14px;
}
.execution-footnote {
  padding: 0 20px 16px;
  font-size: 10px;
  color: #60758f;
  line-height: 1.8;
}
.showcase-empty {
  padding: 60px 20px;
  text-align: center;
  font-size: 13px;
  color: #60758f;
  line-height: 1.9;
}
.showcase-reference-list {
  margin-top: 23px;
}
.showcase-reference-list h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 12px;
}
.showcase-reference-list button {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  width: 100%;
  text-align: left;
  padding: 13px 0;
  border: 0;
  border-bottom: 1px solid #dbe5ef;
  background: transparent;
  color: #536b87;
}
.showcase-reference-list button > span {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 12px;
  flex-shrink: 0;
}
.showcase-reference-list small {
  color: #60758f;
  font-size: 10px;
  overflow-wrap: anywhere;
}
.showcase-step-detail {
  margin-top: 20px;
  padding: 22px;
  border: 1px solid #dbe5ef;
  background: #ffffff;
  border-radius: 11px;
}
.showcase-step-detail header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.showcase-step-detail h3 {
  font-size: 18px;
  margin-top: 4px;
}
.showcase-step-detail header small {
  color: #42678d;
}
.showcase-step-detail > p {
  font-size: 12px;
  color: #536b87;
  margin: 12px 0;
  line-height: 1.8;
}
.showcase-step-detail summary {
  cursor: pointer;
  padding: 12px 0;
  font-size: 12px;
}
.showcase-references {
  display: grid;
  gap: 9px;
  font-size: 11px;
  color: #168d89;
  margin: 8px 0 16px;
}
.showcase-references span {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.showcase-io {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.showcase-io > div {
  min-width: 0;
}
.showcase-io h4 {
  font-size: 11px;
  color: #60758f;
  font-weight: 400;
}
.showcase-io pre {
  margin-bottom: 0;
  padding: 13px;
  border: 1px solid #dbe5ef;
  background: #f5f8fc;
  border-radius: 8px;
  font-size: 11px;
  line-height: 1.8;
  max-height: 290px;
}
.showcase-results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
  margin-bottom: 24px;
}
.showcase-results article {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 21px 20px 14px;
  border: 1px solid #dbe5ef;
  border-radius: 12px;
  background: radial-gradient(ellipse at 100% 0, #d6eff766, transparent 80%), #ffffff;
  box-shadow: 0 4px 16px #274d7810;
  animation: scene-in 320ms ease-out both;
}
.showcase-results article > span {
  font-size: 12px;
  color: #60758f;
}
.showcase-results article > small {
  font-size: 10px;
  color: #60758f;
  margin-bottom: -7px;
}
.showcase-results strong {
  font-size: clamp(26px, 2.8vw, 38px);
  font-weight: 450;
  color: #16607c;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.showcase-results strong small {
  margin-left: 8px;
  font-size: 12px;
  color: #42678d;
}
.showcase-results dl {
  margin: 0 0 3px;
  display: grid;
  gap: 7px;
  font-size: 11px;
  color: #536b87;
}
.showcase-results dl > div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.showcase-results dd {
  margin: 0;
  color: #33465e;
}
.showcase-results article > button {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  padding: 11px 0 0;
  border: 0;
  border-top: 1px solid #dbe5ef;
  font-size: 10px;
  background: transparent;
  color: #42678d;
  text-align: left;
}
.showcase-answer {
  padding: 22px;
  border: 1px solid #dbe5ef;
  border-radius: 11px;
  background: #ffffff;
}
.showcase-answer h3 {
  font-size: 15px;
  font-weight: 550;
  margin-bottom: 17px;
}
.showcase-answer :deep(.markdown-text),
.showcase-evidence :deep(.markdown-text) {
  color: #33465e;
  font-size: 12px;
  line-height: 1.95;
}
.showcase-answer :deep(table),
.showcase-evidence :deep(table) {
  color: #33465e;
}
.showcase-answer :deep(th),
.showcase-evidence :deep(th) {
  background: #eaf2fa;
}
.showcase-answer > details {
  margin-top: 18px;
  font-size: 12px;
  color: #60758f;
  line-height: 1.9;
}
.showcase-answer summary {
  cursor: pointer;
}
.showcase-evidence {
  margin: 26px 0 0;
}
.showcase-evidence > header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 15px;
}
.showcase-evidence h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 500;
}
.showcase-evidence header > span {
  font-size: 10px;
  color: #60758f;
}
.showcase-evidence > details {
  border-top: 1px solid #dbe5ef;
  padding: 15px 0;
}
.showcase-evidence summary {
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: #536b87;
}
.showcase-evidence-tags {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
  font-size: 10px;
}
.showcase-evidence-tags i {
  font-style: normal;
  color: #60758f;
}
.showcase-evidence-tags b {
  padding: 4px 7px;
  color: #647e99;
  background: #edf1f5;
  border-radius: 4px;
  font-weight: 400;
}
.showcase-evidence-tags b.cited {
  color: #248d6b;
  background: #e4f5ed;
}
.showcase-evidence :deep(.markdown-text) {
  margin-top: 16px;
}
.showcase-source,
.showcase-citation-note,
.showcase-evidence > p {
  font-size: 10px;
  line-height: 1.9;
  color: #60758f;
  margin-top: 10px;
  overflow-wrap: anywhere;
}
.showcase-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  border-top: 1px solid #dbe5ef;
  padding: 14px 32px;
  background: #ffffff;
}
.showcase-footer > div:first-child {
  display: grid;
  gap: 4px;
  color: #60758f;
  font-size: 10px;
}
.showcase-footer code {
  color: #536b87;
  font-size: 10px;
}
.showcase-navigation {
  display: flex;
  align-items: center;
  gap: 10px;
}
.showcase-navigation button,
.showcase-navigation a {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 9px 12px;
  border: 1px solid #dbe5ef;
  background: #f3f7fc;
  color: #536b87;
  border-radius: 6px;
}
.showcase-navigation .next-scene {
  background: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  font-weight: 600;
}
@media (min-width: 1400px) {
  .showcase-content {
    padding-left: max(40px, calc((100vw - 1380px) / 2));
    padding-right: max(40px, calc((100vw - 1380px) / 2));
  }
}
@media (max-width: 850px) {
  .showcase-header {
    padding: 17px 20px;
  }
  .showcase-title h2 {
    font-size: 20px;
  }
  .showcase-scenes {
    padding: 0 14px;
  }
  .showcase-scenes button {
    padding: 16px 12px;
    gap: 7px;
    font-size: 11px;
  }
  .showcase-content {
    padding: 18px 20px 26px;
  }
  .showcase-scene-heading {
    margin-bottom: 13px;
  }
  .showcase-network-wrap {
    min-height: 420px;
    height: 420px;
  }
  .showcase-footer {
    padding: 12px 20px;
  }
  .showcase-launch-bottom {
    flex-wrap: wrap;
  }
  .showcase-reference-list button {
    flex-direction: column;
    gap: 7px;
  }
}
@media (max-width: 560px) {
  .showcase-invitation {
    padding: 16px 14px;
    gap: 10px;
  }
  .showcase-invitation h3 {
    font-size: 15px;
  }
  .showcase-header {
    padding: 14px;
  }
  .showcase-title h2 {
    font-size: 17px;
  }
  .showcase-brand {
    font-size: 8px;
  }
  .showcase-header-actions {
    gap: 8px;
  }
  .showcase-header-actions :deep(.status-badge) {
    display: none;
  }
  .showcase-scenes {
    padding: 0 6px;
    justify-content: space-between;
  }
  .showcase-scenes button {
    font-size: 10px;
    padding: 14px 8px;
  }
  .scene-number {
    display: none;
  }
  .showcase-content {
    padding: 15px 12px 25px;
  }
  .showcase-scene-heading {
    align-items: flex-start;
    gap: 12px;
  }
  .showcase-scene-heading > div > p {
    font-size: 11px;
  }
  .showcase-querybar p {
    font-size: 11px;
  }
  .showcase-graph-options select {
    max-width: 118px;
  }
  .showcase-graph-options {
    gap: 7px;
  }
  .showcase-network-wrap {
    min-height: 390px;
    height: 390px;
  }
  .showcase-stat-row {
    gap: 6px;
  }
  .showcase-stat-row > div {
    padding-left: 9px;
  }
  .showcase-stat-row strong {
    font-size: 25px;
  }
  .showcase-stat-row span {
    font-size: 9px;
  }
  .execution-legend {
    flex-wrap: wrap;
    padding: 14px 12px 4px;
  }
  .execution-legend small {
    margin-left: 0;
  }
  .showcase-io {
    grid-template-columns: 1fr;
  }
  .showcase-results {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 9px;
  }
  .showcase-results article {
    padding: 15px 12px 12px;
  }
  .showcase-results strong {
    font-size: 25px;
  }
  .showcase-evidence > header,
  .showcase-evidence summary {
    align-items: flex-start;
    flex-direction: column;
  }
  .showcase-footer {
    padding: 11px 12px;
  }
  .showcase-footer > div:first-child {
    max-width: 42%;
  }
  .showcase-navigation {
    gap: 5px;
  }
  .showcase-navigation button,
  .showcase-navigation a {
    padding: 8px;
    font-size: 10px;
  }
}
@media (max-height: 850px) {
  .showcase-results article {
    padding: 14px 16px 10px;
    gap: 6px;
  }
  .showcase-results strong {
    font-size: 29px;
  }
  .showcase-results article > button {
    padding-top: 8px;
  }
  .showcase-results dl {
    gap: 5px;
  }
  .showcase-header {
    padding-top: 12px;
    padding-bottom: 12px;
  }
  .showcase-title h2 {
    margin-top: 6px;
    font-size: 20px;
  }
  .showcase-scenes button {
    padding-top: 12px;
    padding-bottom: 12px;
  }
  .showcase-content {
    padding-top: 14px;
  }
  .showcase-scene-heading {
    margin-bottom: 12px;
  }
  .showcase-scene-heading .showcase-overline {
    display: none;
  }
  .showcase-scene-heading > div > p {
    margin-top: 0;
  }
  .showcase-querybar {
    margin-bottom: 11px;
  }
  .showcase-network-wrap {
    height: max(320px, calc(100dvh - 340px));
    min-height: 320px;
  }
  .showcase-network-wrap :deep(.run-graph),
  .showcase-network-wrap :deep(.run-graph-canvas) {
    min-height: 320px;
  }
}
</style>
