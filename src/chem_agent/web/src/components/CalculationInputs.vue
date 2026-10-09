<script setup lang="ts">
import { computed } from 'vue'
import type { RunResult } from '../types/api'
import { calculationInputs, numberText } from '../utils/presentation'

const props = defineProps<{ result: RunResult }>()
const groups = computed(() => calculationInputs(props.result))
</script>

<template>
  <details v-if="groups.length" class="calculation-review">
    <summary>
      核对实际计算入参
      <span>{{ groups.length }} 个工具步骤</span>
    </summary>
    <p class="section-help">与本题及前轮已知条件核对；来源标签按执行记录显示。</p>
    <section v-for="group in groups" :key="group.id" class="input-group">
      <h4>
        {{ group.title }}
        <code>{{ group.step }}</code>
      </h4>
      <div class="input-table-scroll">
        <table>
          <caption class="sr-only">{{ group.title }} {{ group.step }} 实际参数与来源</caption>
          <thead>
            <tr>
              <th scope="col">参数</th>
              <th scope="col">实际数值</th>
              <th scope="col">来源记录</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="parameter in group.parameters" :key="parameter.label">
              <th scope="row">{{ parameter.label }}</th>
              <td>
                {{ numberText(parameter.value) }}
                <span>{{ parameter.unit }}</span>
              </td>
              <td>{{ parameter.source }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </details>
</template>

<style scoped>
.calculation-review {
  margin-bottom: 24px;
  padding: 12px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  color: #475467;
}
summary span {
  margin-left: 8px;
  font-size: 11px;
  color: var(--muted);
}
.section-help {
  margin: 12px 0;
}
.input-group + .input-group {
  margin-top: 18px;
}
h4 {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
}
h4 code {
  margin-left: 6px;
  color: var(--muted);
}
.input-table-scroll {
  max-width: 100%;
  overflow: auto;
}
table {
  width: 100%;
  min-width: 440px;
  border-collapse: collapse;
  text-align: left;
}
th,
td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  overflow-wrap: anywhere;
}
thead th {
  background: var(--soft);
  font-size: 11px;
  font-weight: 500;
  color: var(--muted);
}
tbody th {
  font-weight: 400;
}
td:nth-child(2) {
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
td span {
  font-size: 11px;
  color: var(--muted);
}
td:last-child {
  font-size: 11px;
  color: var(--muted);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
