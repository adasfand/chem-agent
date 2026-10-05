<script setup lang="ts">
import { statusLabels } from '../utils/presentation'
defineProps<{ status: string; label?: string }>()
</script>
<template>
  <span class="status-badge" :class="`status-${status}`">
    <span class="status-dot" />
    {{ label || statusLabels[status] || status }}
  </span>
</template>
