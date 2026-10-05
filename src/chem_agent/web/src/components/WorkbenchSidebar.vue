<script setup lang="ts">
import { FlaskConical, LayoutDashboard, BookOpen, Plus, Clock3 } from '@lucide/vue'
import type { RunSummary } from '../types/api'
import { timeText, statusLabels } from '../utils/presentation'
defineProps<{
  view: string
  runs: RunSummary[]
  selected?: string
  busy: boolean
  loadingId: string | null
}>()
defineEmits<{ navigate: [view: 'workbench' | 'knowledge']; new: []; select: [id: string] }>()
</script>
<template>
  <aside class="sidebar">
    <a class="brand" href="#" @click.prevent="$emit('navigate', 'workbench')">
      <span class="brand-symbol"><FlaskConical :size="24" /></span>
      <span>
        Chem Agent
        <small>化工知识与计算</small>
      </span>
    </a>
    <button class="new-task-button" :disabled="busy" @click="$emit('new')">
      <Plus :size="17" />
      新建任务
    </button>
    <div class="nav-caption">工作空间</div>
    <nav aria-label="工作空间">
      <button
        :class="{ active: view === 'workbench' }"
        :aria-current="view === 'workbench' ? 'page' : undefined"
        @click="$emit('navigate', 'workbench')"
      >
        <LayoutDashboard :size="18" />
        任务工作台
      </button>
      <button
        :class="{ active: view === 'knowledge' }"
        :aria-current="view === 'knowledge' ? 'page' : undefined"
        @click="$emit('navigate', 'knowledge')"
      >
        <BookOpen :size="18" />
        知识资料库
      </button>
    </nav>
    <div class="sidebar-history">
      <div class="nav-caption">
        最近任务
        <span>{{ runs.length }}</span>
      </div>
      <div v-if="!runs.length" class="history-empty">
        <Clock3 :size="20" />
        <p>还没有任务记录</p>
        <small>运行后可在这里查看与继续</small>
      </div>
      <div v-else class="history-list">
        <button
          v-for="run in runs"
          :key="run.job_id"
          :class="{ selected: selected === run.job_id }"
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
      </div>
    </div>
    <div class="sidebar-footer">
      本地工作空间
      <small>会话记录随本次服务运行保留</small>
    </div>
  </aside>
</template>
