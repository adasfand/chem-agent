<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  FlaskConical,
  MessagesSquare,
  BookOpen,
  Plus,
  Search,
  MessageSquare,
  CircleHelp,
} from '@lucide/vue'
import type { RunSummary } from '../types/api'
import { timeText, statusLabels } from '../utils/presentation'
const props = defineProps<{
  view: string
  runs: RunSummary[]
  selected?: string
  busy: boolean
  loadingId: string | null
  connected: boolean
  version?: string
}>()
defineEmits<{
  navigate: [view: 'workbench' | 'knowledge']
  new: []
  select: [id: string]
  settings: []
}>()
const query = ref('')
const filtered = computed(() =>
  props.runs.filter((run) => run.question.toLowerCase().includes(query.value.trim().toLowerCase())),
)
</script>
<template>
  <aside class="sidebar">
    <a class="brand" href="#" @click.prevent="$emit('navigate', 'workbench')">
      <span class="brand-symbol"><FlaskConical :size="22" /></span>
      <span>
        Chem Agent
        <small>化工知识与计算</small>
      </span>
    </a>
    <button class="new-task-button" :disabled="busy" @click="$emit('new')">
      <Plus :size="17" />
      新建问答
    </button>
    <nav aria-label="工作空间">
      <button
        :class="{ active: view === 'workbench' }"
        :aria-current="view === 'workbench' ? 'page' : undefined"
        @click="$emit('navigate', 'workbench')"
      >
        <MessagesSquare :size="17" />
        问答工作台
      </button>
      <button
        :class="{ active: view === 'knowledge' }"
        :aria-current="view === 'knowledge' ? 'page' : undefined"
        @click="$emit('navigate', 'knowledge')"
      >
        <BookOpen :size="17" />
        知识资料库
      </button>
    </nav>
    <div class="sidebar-history">
      <div class="nav-caption">
        最近问答
        <span>{{ runs.length }}</span>
      </div>
      <label v-if="runs.length" class="history-search">
        <Search :size="14" />
        <input v-model="query" type="search" aria-label="搜索任务记录" placeholder="搜索记录" />
      </label>
      <div v-if="!runs.length" class="history-empty">
        <MessageSquare :size="19" />
        <p>暂无问答记录</p>
        <small>运行后的任务会显示在这里</small>
      </div>
      <div v-else class="history-list">
        <button
          v-for="run in filtered"
          :key="run.job_id"
          :class="{ selected: selected === run.job_id }"
          :aria-current="selected === run.job_id ? 'true' : undefined"
          :title="run.question"
          :disabled="(busy && selected !== run.job_id) || loadingId === run.job_id"
          @click="$emit('select', run.job_id)"
        >
          <span class="history-title">{{ run.question }}</span>
          <span class="history-meta">
            <i :class="`status-${run.status}`" />
            {{ statusLabels[run.status] }}
            <time>{{ timeText(run.created_at) }}</time>
          </span>
        </button>
        <p v-if="!filtered.length" class="empty-message">没有匹配的记录</p>
      </div>
    </div>
    <div class="sidebar-footer">
      <button @click="$emit('settings')">
        <CircleHelp :size="16" />
        运行配置与说明
      </button>
      <div>
        <i :class="{ offline: !connected }" />
        {{ connected ? '后端已连接' : '后端未连接' }}
        <span>v{{ version || '—' }}</span>
      </div>
    </div>
  </aside>
</template>
