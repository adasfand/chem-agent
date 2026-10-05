<script setup lang="ts">
import { BookOpen, ArrowUpRight } from '@lucide/vue'
import type { Evidence } from '../types/api'
import MarkdownText from './MarkdownText.vue'
defineProps<{ evidence: Evidence[]; citations: string[] }>()
defineEmits<{ open: [id: string] }>()
</script>
<template>
  <div class="evidence-panel">
    <p class="section-help">以下为本轮真实检索片段。相关度反映文本匹配程度，不代表答案准确率。</p>
    <div v-if="!evidence.length" class="empty-message">当前任务尚无检索依据。</div>
    <article v-for="item in evidence" :key="item.chunk_id" class="evidence-card">
      <div class="evidence-heading">
        <BookOpen :size="16" />
        <strong>{{ item.title }}</strong>
        <span class="citation-tag" :class="{ cited: citations.includes(item.chunk_id) }">
          {{ citations.includes(item.chunk_id) ? '回答已引用' : '仅检索' }}
        </span>
      </div>
      <div class="evidence-meta">
        <code>{{ item.chunk_id }}</code>
        <span>相关度 {{ item.score.toFixed(3) }}</span>
      </div>
      <MarkdownText :text="item.text" />
      <p class="source-line">来源：{{ item.source }}</p>
      <button class="text-button" @click="$emit('open', item.doc_id)">
        查看完整知识卡
        <ArrowUpRight :size="14" />
      </button>
    </article>
  </div>
</template>
