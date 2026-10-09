<script setup lang="ts">
import { ArrowDownRight, Link2 } from '@lucide/vue'
import type { RunResult } from '../types/api'
import { toolLabels } from '../utils/presentation'
import StatusBadge from './StatusBadge.vue'
defineProps<{ result: RunResult }>()
const json = (value: unknown) => JSON.stringify(value ?? {}, null, 2)
</script>
<template>
  <div class="execution-trace">
    <p class="section-help">计划与实际调用分开记录，可展开核对参数、返回值和结果引用。</p>
    <p v-if="!result.plan.length" class="empty-message">尚未形成执行计划。</p>
    <ol class="plan-list">
      <li v-for="(step, index) in result.plan" :key="step.step_id">
        <span class="step-index">{{ index + 1 }}</span>
        <div class="step-content">
          <div class="step-title">
            <strong>{{ step.goal }}</strong>
            <StatusBadge :status="step.status" />
          </div>
          <p>
            {{ toolLabels[step.tool_name] || step.tool_name }}
            <code>{{ step.step_id }}</code>
          </p>
          <small v-if="step.depends_on.length">
            <ArrowDownRight :size="13" />
            依赖：{{ step.depends_on.join('、') }}
          </small>
        </div>
      </li>
    </ol>
    <h3 class="subheading">
      实际工具调用
      <span>{{ result.calls.length }}</span>
    </h3>
    <details v-for="call in result.calls" :key="call.call_id" class="call-detail">
      <summary>
        <span>
          {{ toolLabels[call.tool_name] || call.tool_name }}
          <code>{{ call.step_id }}</code>
        </span>
        <StatusBadge :status="call.status" />
      </summary>
      <div class="call-body">
        <h4>实际输入参数</h4>
        <pre v-if="call.arguments != null">{{ json(call.arguments) }}</pre>
        <p v-else>尚未形成实际输入。</p>
        <div v-if="call.input_refs?.length" class="reference-block">
          <h4>
            <Link2 :size="14" />
            前序结果回用
          </h4>
          <div v-for="(ref, index) in call.input_refs" :key="index">
            <code>{{ ref.ref }}</code>
            <span>→ {{ ref.argument }} = {{ json(ref.value) }} {{ ref.unit || '' }}</span>
          </div>
        </div>
        <details v-if="call.requested_arguments">
          <summary>模型请求的原始参数</summary>
          <pre>{{ json(call.requested_arguments) }}</pre>
        </details>
        <details v-if="call.input_provenance?.length">
          <summary>用户给定参数的来源记录</summary>
          <pre>{{ json(call.input_provenance) }}</pre>
        </details>
        <h4>{{ call.error ? '错误信息' : '工具返回值' }}</h4>
        <pre :class="{ 'error-output': call.error }">{{ json(call.error ?? call.output) }}</pre>
      </div>
    </details>
  </div>
</template>
