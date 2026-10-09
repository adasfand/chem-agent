<script setup lang="ts">
import { statusLabels } from '../utils/presentation'
defineProps<{ status: string; label?: string }>()
</script>
<template>
  <span class="badge" :class="status">
    {{ label || statusLabels[status] || status }}
  </span>
</template>
