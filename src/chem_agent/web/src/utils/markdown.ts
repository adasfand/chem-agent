export interface InlineToken {
  kind: 'text' | 'strong' | 'code'
  text: string
}
export interface MarkdownBlock {
  kind: 'heading' | 'paragraph' | 'quote' | 'code' | 'list'
  text: string
  items?: string[]
  ordered?: boolean
  level?: number
}
/** A deliberately small Markdown subset; all content is rendered as Vue text nodes. */
export function inlineTokens(text: string): InlineToken[] {
  const tokens: InlineToken[] = []
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g
  let previous = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > previous) tokens.push({ kind: 'text', text: text.slice(previous, index) })
    const code = match[0].startsWith('`')
    tokens.push({
      kind: code ? 'code' : 'strong',
      text: match[0].slice(code ? 1 : 2, code ? -1 : -2),
    })
    previous = index + match[0].length
  }
  if (previous < text.length) tokens.push({ kind: 'text', text: text.slice(previous) })
  return tokens
}
export function markdownBlocks(text: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = []
  let paragraph: string[] = []
  let code: string[] | null = null
  let list: MarkdownBlock | null = null
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', text: paragraph.join('\n') })
    if (list) blocks.push(list)
    paragraph = []
    list = null
  }
  for (const line of text.split('\n')) {
    if (/^\s*```/.test(line)) {
      if (code) {
        blocks.push({ kind: 'code', text: code.join('\n') })
        code = null
      } else {
        flush()
        code = []
      }
      continue
    }
    if (code) {
      code.push(line)
      continue
    }
    if (!line.trim()) {
      flush()
      continue
    }
    const heading = line.match(/^(#{1,6})\s+(.+)/)
    const section = line
      .trim()
      .match(/^(计算结果|计算输入与方法|适用条件|计算方法|计算步骤|结论|注意事项)[：:]$/)
    const item = line.match(/^\s*(?:([-*])|\d+[.)、])\s+(.+)/)
    if (heading) {
      flush()
      blocks.push({ kind: 'heading', text: heading[2] ?? '', level: heading[1]?.length || 1 })
    } else if (section) {
      flush()
      blocks.push({ kind: 'heading', text: section[1] ?? '', level: 1 })
    } else if (item) {
      const ordered = !item[1]
      if (!list || list.ordered !== ordered) {
        flush()
        list = { kind: 'list', text: '', items: [], ordered }
      }
      list.items?.push(item[2] ?? '')
    } else if (/^>\s?/.test(line)) {
      flush()
      blocks.push({ kind: 'quote', text: line.replace(/^>\s?/, '') })
    } else {
      if (list) flush()
      paragraph.push(line)
    }
  }
  flush()
  if (code) blocks.push({ kind: 'code', text: code.join('\n') })
  return blocks
}
