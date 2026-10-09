<script setup lang="ts">
import { computed } from 'vue'
import { markdownBlocks } from '../utils/markdown'
import InlineText from './InlineText.vue'
const props = defineProps<{ text: string }>()
const blocks = computed(() => markdownBlocks(props.text))
</script>

<template>
  <div class="markdown-text">
    <template v-for="(block, index) in blocks" :key="index">
      <component
        :is="`h${Math.min(6, (block.level || 1) + 2)}`"
        v-if="block.kind === 'heading'"
        class="markdown-heading"
      >
        <InlineText :text="block.text" />
      </component>
      <pre v-else-if="block.kind === 'code'"><code>{{ block.text }}</code></pre>
      <blockquote v-else-if="block.kind === 'quote'"><InlineText :text="block.text" /></blockquote>
      <component :is="block.ordered ? 'ol' : 'ul'" v-else-if="block.kind === 'list'">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
          <InlineText :text="item" />
        </li>
      </component>
      <p v-else><InlineText :text="block.text" /></p>
    </template>
  </div>
</template>
