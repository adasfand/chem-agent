<script setup lang="ts">
import type { RetrievalRecord } from '../utils/retrieval'
import { text, safeUrl } from '../utils/retrieval'
import MarkdownText from './MarkdownText.vue'
defineProps<{ ids: string[]; sources: RetrievalRecord[]; hits: RetrievalRecord[] }>()
</script>
<template>
  <div class="graph-sources">
    <p v-if="!ids.length" class="muted">本轮未提供此实体的关联原文。</p>
    <details v-for="(id, index) in ids" :key="id" class="graph-source">
      <summary>
        展开原文：{{
          text(sources.find((item) => item.chunk_id === id)?.title) ||
          `关联来源 ${index + 1}（未解析）`
        }}
      </summary>
      <template
        v-for="source in sources.filter((item) => item.chunk_id === id)"
        :key="text(source.chunk_id)"
      >
        <span class="citation-tag">
          {{
            hits.some((item) => item.chunk_id === id) ? '本轮检索已命中' : '仅索引关联，本轮未命中'
          }}
        </span>
        <MarkdownText v-if="source.text" :text="text(source.text)" />
        <p v-else class="muted">未提供原文，无法核验。</p>
        <p class="source-line">
          来源：
          <a
            v-if="safeUrl(source.url || source.source)"
            :href="safeUrl(source.url || source.source)"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ text(source.source) || text(source.url) }} ↗
          </a>
          <span v-else>{{ text(source.source) || '未标注' }}</span>
        </p>
      </template>
      <p v-if="!sources.some((item) => item.chunk_id === id)" class="muted">
        索引未解析此来源，不能据此核验。
      </p>
    </details>
  </div>
</template>
