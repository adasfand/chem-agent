<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import { X, RefreshCw, Wrench, Plug, Play } from '@lucide/vue'
import type { ToolRegistry, RegisteredTool, ManualToolResult } from '../types/api'
import { toolRegistryApi } from '../services/api'
import { durationText, parseToolArguments } from '../utils/audit'
import StatusBadge from './StatusBadge.vue'

const dialog = ref<HTMLDialogElement>()
const registry = shallowRef<ToolRegistry | null>(null)
const selected = shallowRef<RegisteredTool | null>(null)
const argumentsText = ref('')
const loading = ref(false)
const calling = ref(false)
const error = ref('')
const result = shallowRef<ManualToolResult | null>(null)
const records = shallowRef<ManualToolResult[]>([])
const tools = computed(() => registry.value?.tools ?? [])
const json = (value: unknown) => JSON.stringify(value ?? {}, null, 2)
function select(tool: RegisteredTool) {
  if (calling.value) return
  selected.value = tool
  argumentsText.value = json(tool.example)
  result.value = null
  error.value = ''
}
async function load(refresh = false) {
  if (loading.value || calling.value) return
  loading.value = true
  error.value = ''
  try {
    registry.value = await toolRegistryApi.list(refresh)
    const previous = selected.value?.name
    const tool =
      tools.value.find((tool) => tool.name === previous) ??
      tools.value.find((tool) => tool.source === 'mcp') ??
      tools.value[0]
    if (tool) select(tool)
    else selected.value = null
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '工具目录加载失败。'
  } finally {
    loading.value = false
  }
}
async function invoke() {
  const tool = selected.value
  if (!tool || tool.source !== 'mcp' || calling.value) return
  error.value = ''
  result.value = null
  try {
    const args = parseToolArguments(argumentsText.value)
    calling.value = true
    result.value = await toolRegistryApi.invoke(tool.name, args)
    records.value = [result.value, ...records.value].slice(0, 10)
  } catch (cause) {
    error.value =
      cause instanceof SyntaxError
        ? 'JSON 格式无效，请检查引号、逗号和括号。'
        : cause instanceof Error
          ? cause.message
          : '工具调用失败。'
  } finally {
    calling.value = false
  }
}
function open() {
  if (!dialog.value?.open) dialog.value?.showModal()
  if (!registry.value) void load()
}
defineExpose({ open })
</script>
<template>
  <dialog ref="dialog" class="tool-registry-dialog" aria-labelledby="tool-registry-title">
    <header class="dialog-heading">
      <div>
        <h2 id="tool-registry-title">
          <Wrench :size="19" />
          工具注册表
        </h2>
        <p>查看工具能力、参数与实际返回结果</p>
      </div>
      <button class="icon-button" aria-label="关闭工具注册表" @click="dialog?.close()">
        <X :size="19" />
      </button>
    </header>
    <div class="registry-connection">
      <span>
        <Plug :size="14" />
        {{
          registry?.state === 'connected'
            ? '本地 MCP 已连接'
            : loading
              ? '正在发现工具…'
              : 'MCP 未连接'
        }}
      </span>
      <small v-if="registry">{{ registry.server }} · {{ registry.transport }}</small>
      <button class="button secondary" :disabled="loading || calling" @click="load(true)">
        <RefreshCw :size="13" />
        刷新目录
      </button>
    </div>
    <p v-if="registry?.message" class="registry-message">{{ registry.message }}</p>
    <p v-if="error" class="registry-error" role="alert">{{ error }}</p>
    <div class="registry-layout">
      <nav class="registry-catalog" aria-label="已注册工具">
        <template v-for="source in ['agent', 'mcp']" :key="source">
          <h3>{{ source === 'agent' ? 'Agent 业务工具' : 'MCP 辅助工具' }}</h3>
          <button
            v-for="tool in tools.filter((item) => item.source === source)"
            :key="tool.name"
            :class="{ selected: selected?.name === tool.name }"
            :aria-pressed="selected?.name === tool.name"
            :disabled="calling"
            @click="select(tool)"
          >
            <strong>{{ tool.title }}</strong>
            <small>{{ tool.invocation === 'model' ? '由模型按计划调用' : '支持手动试用' }}</small>
          </button>
        </template>
      </nav>
      <section v-if="selected" class="registry-tool-detail">
        <div class="registry-tool-heading">
          <h3>{{ selected.title }}</h3>
          <span>{{ selected.source === 'mcp' ? 'MCP' : 'Agent' }}</span>
        </div>
        <p>{{ selected.description }}</p>
        <template v-if="selected.source === 'mcp'">
          <p class="registry-note">此处为手动试用，结果保留在工具面板中。</p>
          <label for="mcp-arguments">输入参数（JSON）</label>
          <textarea
            id="mcp-arguments"
            v-model="argumentsText"
            spellcheck="false"
            :disabled="calling"
            :maxlength="12000"
          />
          <div class="registry-actions">
            <button
              class="button secondary"
              :disabled="calling"
              @click="argumentsText = json(selected.example)"
            >
              填入示例参数
            </button>
            <button class="button primary" :disabled="calling || loading" @click="invoke">
              <Play :size="14" />
              {{ calling ? '工具执行中…' : '执行工具' }}
            </button>
          </div>
          <details v-if="selected.input_schema" class="registry-schema">
            <summary>查看参数规范</summary>
            <pre>{{ json(selected.input_schema) }}</pre>
          </details>
          <section v-if="result" class="registry-result" aria-label="手动工具结果">
            <div>
              <h4>工具返回结果</h4>
              <StatusBadge :status="result.status" />
            </div>
            <p>手动调用 · {{ durationText(result.latency_ms) }}（含 MCP 连接）</p>
            <pre>{{ result.error ?? json(result.output) }}</pre>
          </section>
        </template>
        <template v-else>
          <p class="registry-note">
            在问答中描述任务及已知条件，模型会登记计划并选择业务工具。执行审计展示实际调用和参数来源。
          </p>
          <details v-if="selected.input_schema" class="registry-schema">
            <summary>查看业务工具参数规范</summary>
            <pre>{{ json(selected.input_schema) }}</pre>
          </details>
        </template>
      </section>
      <p v-else class="registry-tool-detail section-help">
        {{ loading ? '正在读取注册工具…' : '刷新目录后选择工具查看。' }}
      </p>
    </div>
    <details v-if="records.length" class="registry-history">
      <summary>本次页面的手动调用记录（{{ records.length }}）</summary>
      <ol>
        <li v-for="(record, index) in records" :key="index">
          <span>
            {{ tools.find((tool) => tool.name === record.tool_name)?.title || record.tool_name }}
          </span>
          <StatusBadge :status="record.status" />
          <small>
            {{ new Date(record.started_at).toLocaleTimeString('zh-CN') }} ·
            {{ durationText(record.latency_ms) }}
          </small>
        </li>
      </ol>
    </details>
  </dialog>
</template>
