import { sourceIds, text, type RetrievalRecord } from './retrieval'

export interface GraphOverview {
  state: string
  message: string
  scope: 'index_exploration'
  query: string
  entities: RetrievalRecord[]
  relationships: RetrievalRecord[]
  sources: RetrievalRecord[]
  communities: { id: number; label: string; size: number }[]
  topics: string[]
  stats: {
    total_entities: number
    total_relationships: number
    documents: number
    visible_entities?: number
    visible_relationships?: number
    source_documents?: number
  }
}

export const typeColors: Record<string, string> = {
  data: '#168db8',
  concept: '#8b75d6',
  method: '#c28c34',
  process: '#dc7195',
  material: '#249c7a',
  artifact: '#5b87d1',
  content: '#43a0ad',
  event: '#cc8050',
  naturalobject: '#6b9e55',
  organization: '#a47bc3',
}
export const nodeColor = (type: string) => typeColors[type.toLowerCase()] || '#7187a3'

export function explorerLayout(data: Pick<GraphOverview, 'entities' | 'relationships'>) {
  const width = 1100,
    height = 720
  const groups = [...new Set(data.entities.map((entity) => Number(entity.community) || 0))]
  const centers = groups.map((_, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(1, groups.length)
    const radius = groups.length === 1 ? 0 : 215
    return {
      x: width / 2 + Math.cos(angle) * radius * 1.25,
      y: height / 2 + Math.sin(angle) * radius,
    }
  })
  const nodes = data.entities.map((entity, index) => {
    const community = Number(entity.community) || 0
    const center = centers[groups.indexOf(community)]!
    const angle = index * 2.399963229728653
    const orbit = 25 + Math.sqrt(index + 1) * 13
    const degree = Number(entity.degree) || 0
    return {
      id: text(entity.id),
      name: text(entity.name) || text(entity.id),
      index,
      community,
      type: text(entity.type),
      degree,
      radius: Math.min(16, 5 + Math.sqrt(degree) * 1.65),
      sourceIds: sourceIds(entity),
      x: center.x + Math.cos(angle) * orbit,
      y: center.y + Math.sin(angle) * orbit,
      vx: 0,
      vy: 0,
      cx: center.x,
      cy: center.y,
    }
  })
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const edges = data.relationships.flatMap((edge, index) => {
    const from = byId.get(text(edge.source)),
      to = byId.get(text(edge.target))
    return from && to && from !== to ? [{ from, to, index, data: edge }] : []
  })
  // Deterministic bounded simulation: positions are display-only, never inferred relationships.
  for (let iteration = 0; iteration < 260; iteration++) {
    const cooling = 1 - iteration / 300
    for (let a = 0; a < nodes.length; a++) {
      const first = nodes[a]!
      for (let b = a + 1; b < nodes.length; b++) {
        const second = nodes[b]!
        const dx = first.x - second.x || 0.01,
          dy = first.y - second.y || 0.01
        const distance = Math.max(1, Math.hypot(dx, dy))
        const minDistance = first.radius + second.radius + 34
        const force = Math.min(
          7,
          1200 / (distance * distance) + Math.max(0, minDistance - distance) * 0.07,
        )
        first.vx += (dx / distance) * force
        first.vy += (dy / distance) * force
        second.vx -= (dx / distance) * force
        second.vy -= (dy / distance) * force
      }
    }
    for (const { from, to } of edges) {
      const dx = to.x - from.x,
        dy = to.y - from.y
      const distance = Math.max(1, Math.hypot(dx, dy))
      const desired = from.community === to.community ? 86 : 160
      const force = (distance - desired) * 0.008
      from.vx += (dx / distance) * force
      from.vy += (dy / distance) * force
      to.vx -= (dx / distance) * force
      to.vy -= (dy / distance) * force
    }
    for (const node of nodes) {
      node.vx = (node.vx + (node.cx - node.x) * 0.006) * 0.73
      node.vy = (node.vy + (node.cy - node.y) * 0.006) * 0.73
      node.x = Math.max(65, Math.min(width - 65, node.x + node.vx * cooling))
      node.y = Math.max(65, Math.min(height - 65, node.y + node.vy * cooling))
    }
  }
  return { width, height, nodes, edges }
}

export function adjacentIds(layout: ReturnType<typeof explorerLayout>, id: string) {
  return new Set(
    layout.edges.flatMap(({ from, to }) =>
      from.id === id ? [to.id] : to.id === id ? [from.id] : [],
    ),
  )
}

export function fitGraphView(
  nodes: Pick<ReturnType<typeof explorerLayout>['nodes'][number], 'x' | 'y' | 'radius'>[],
  width: number,
  height: number,
) {
  const left = 28,
    right = 28,
    top = 72,
    bottom = 106
  const usableWidth = Math.max(1, width - left - right)
  const usableHeight = Math.max(1, height - top - bottom)
  const minX = nodes.length ? Math.min(...nodes.map((node) => node.x - node.radius - 48)) : 0
  const maxX = nodes.length ? Math.max(...nodes.map((node) => node.x + node.radius + 48)) : 1
  const minY = nodes.length ? Math.min(...nodes.map((node) => node.y - node.radius - 8)) : 0
  const maxY = nodes.length ? Math.max(...nodes.map((node) => node.y + node.radius + 27)) : 1
  return {
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
    offsetX: left + usableWidth / 2,
    offsetY: top + usableHeight / 2,
    scale: Math.min(2, usableWidth / (maxX - minX), usableHeight / (maxY - minY)),
  }
}
