<script setup lang="ts">
import { computed } from 'vue'
import { inlineTokens } from '../utils/markdown'
const props = defineProps<{ text: string }>()
const tokens = computed(() => inlineTokens(props.text))
</script>

<template>
  <template v-for="(token, index) in tokens" :key="index">
    <strong v-if="token.kind === 'strong'">{{ token.text }}</strong>
    <code v-else-if="token.kind === 'code'">{{ token.text }}</code>
    <template v-else>{{ token.text }}</template>
  </template>
</template>
