<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Search } from '@lucide/vue'
import type { RunResult } from '../types/api'
import {
  retrievalFor,
  graphLayout,
  text,
  parts,
  sourceIds,
  safeUrl,
  entityTypeLabel,
} from '../utils/retrieval'
import GraphSources from './GraphSources.vue'
import EntityGraph from './EntityGraph.vue'
const props = defineProps<{ result: RunResult }>()
const queries = computed(() =>
  props.result.calls
    .filter((call) => call.tool_name === 'search_knowledge' && call.status === 'succeeded')
    .map(retrievalFor),
)
const queryIndex = ref(0)
const selected = ref(0)
const query = computed(() => queries.value[queryIndex.value])
const graph = computed(() =>
  graphLayout(query.value?.entities || [], query.value?.relationships || []),
)
const entity = computed(() => query.value?.entities[selected.value])
watch(
  () => props.result.run_id,
  () => {
    queryIndex.value = 0
    selected.value = 0
  },
)
watch(queryIndex, () => {
  selected.value = 0
})
</script>
<template>
  <div class="retrieval-path">
    <p v-if="!queries.length" class="empty-message">
      完成知识检索后，在这里查看本轮查询、实体关系和命中片段。
    </p>
    <label v-if="queries.length > 1" class="query-select">
      检索查询
      <select v-model="queryIndex">
        <option v-for="(item, index) in queries" :key="index" :value="index">
          {{ index + 1 }}. {{ item.query }}
        </option>
      </select>
    </label>
    <template v-if="query">
      <div class="path-query">
        <Search :size="16" />
        <div>
          <small>
            {{
              query.mode === 'lexical'
                ? '词法检索'
                : query.mode === 'mix'
                  ? '图谱与向量混合检索'
                  : '知识检索'
            }}
          </small>
          <strong>{{ query.query || '未记录查询' }}</strong>
        </div>
        <span>{{ query.hits.length }} 命中</span>
      </div>
      <div v-if="query.keywords.length" class="keyword-groups">
        <span v-for="word in query.keywords" :key="word">{{ word }}</span>
      </div>
      <p v-if="query.mode === 'lexical'" class="inline-note">
        本轮使用词法回退，没有实体关系数据。
      </p>
      <template v-if="graph.nodes.length">
        <EntityGraph
          v-model:selected="selected"
          :entities="query.entities"
          :relationships="query.relationships"
          :sources="query.sources"
          :hits="query.hits"
        />
        <div v-if="entity" class="entity-detail">
          <h4>
            {{ text(entity.name) || text(entity.id) }}
            <small>{{ entityTypeLabel(text(entity.type) || text(entity.entity_type)) }}</small>
          </h4>
          <p v-for="part in parts(entity.description)" :key="part">{{ part }}</p>
          <small>关联来源集合，需逐条核对原文</small>
          <GraphSources :ids="sourceIds(entity)" :sources="query.sources" :hits="query.hits" />
        </div>
      </template>
      <details v-if="query.relationships.length" class="relation-list">
        <summary>全部返回关系 · {{ query.relationships.length }}</summary>
        <article v-for="(rel, index) in query.relationships" :key="index">
          <h4>
            {{ text(rel.source) || text(rel.src_id) }} 与 {{ text(rel.target) || text(rel.tgt_id) }}
          </h4>
          <p v-for="part in parts(rel.description)" :key="part">{{ part }}</p>
          <GraphSources :ids="sourceIds(rel)" :sources="query.sources" :hits="query.hits" />
        </article>
      </details>
      <div class="section-title">
        <h3>本轮命中片段</h3>
        <span>{{ query.hits.length }}</span>
      </div>
      <details
        v-for="(hit, index) in query.hits"
        :key="text(hit.chunk_id) || index"
        class="path-hit"
      >
        <summary>
          {{ text(hit.title) || `知识片段 ${index + 1}` }}
          <span v-if="result.citations.includes(text(hit.chunk_id))" class="citation-tag cited">
            已引用
          </span>
        </summary>
        <p>{{ text(hit.text) }}</p>
        <p class="source-line">{{ text(hit.source) }}</p>
      </details>
      <p v-if="!query.hits.length" class="muted">本轮未返回命中片段。</p>
      <details v-if="query.sources.length" class="source-index">
        <summary>本轮返回的关联来源 · {{ query.sources.length }}</summary>
        <p class="section-help">包含非命中片段；关联来源不自动视为回答引用。</p>
        <GraphSources
          :ids="query.sources.map((item) => text(item.chunk_id)).filter(Boolean)"
          :sources="query.sources"
          :hits="query.hits"
        />
      </details>
      <details v-if="query.references.length" class="source-index">
        <summary>检索来源记录 · {{ query.references.length }}</summary>
        <p v-for="(item, index) in query.references" :key="index">
          <a
            v-if="safeUrl(item.url || item.source)"
            :href="safeUrl(item.url || item.source)"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ text(item.source) || text(item.url) }} ↗
          </a>
          <span v-else>{{ text(item.source) || '未标注来源' }}</span>
        </p>
      </details>
      <p v-if="query.metadata.truncated" class="inline-note">
        后端对检索数据做了截断，当前视图并非全部索引内容。
      </p>
    </template>
  </div>
</template>
