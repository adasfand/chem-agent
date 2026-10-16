import { describe, expect, it } from 'vitest'
import { adjacentIds, explorerLayout, fitGraphView } from '../src/utils/graphExplorer'
import { entityTypeLabel } from '../src/utils/retrieval'

describe('knowledge atlas layout', () => {
  it('keeps every real edge and never invents missing endpoint relationships', () => {
    const result = explorerLayout({
      entities: [
        { id: '质量分数', name: '质量分数', degree: 4, community: 0, source_ids: ['index-only'] },
        { id: '质量流量', degree: 2, community: 0 },
        { id: '热负荷', degree: 1, community: 1 },
      ],
      relationships: [
        { source: '质量分数', target: '质量流量' },
        { source: '质量流量', target: '热负荷' },
        { source: '热负荷', target: '不存在' },
      ],
    })
    expect(result.edges).toHaveLength(2)
    expect(result.nodes[0]?.sourceIds).toEqual(['index-only'])
    expect(adjacentIds(result, '质量分数')).toEqual(new Set(['质量流量']))
    expect(adjacentIds(result, '质量流量')).toEqual(new Set(['质量分数', '热负荷']))
  })

  it('lays out a dense index reproducibly within the view and keeps nodes apart', () => {
    const input = {
      entities: Array.from({ length: 72 }, (_, index) => ({
        id: `N${index}`,
        community: index % 5,
        degree: index % 20,
      })),
      relationships: Array.from({ length: 71 }, (_, index) => ({
        source: `N${index}`,
        target: `N${index + 1}`,
      })),
    }
    const result = explorerLayout(input)
    expect(explorerLayout(input)).toEqual(result)
    expect(result.nodes).toHaveLength(72)
    expect(result.edges).toHaveLength(71)
    for (const node of result.nodes) {
      expect(node.x).toBeGreaterThan(0)
      expect(node.x).toBeLessThan(result.width)
      expect(node.y).toBeGreaterThan(0)
      expect(node.y).toBeLessThan(result.height)
    }
    expect(new Set(result.nodes.map(({ x, y }) => `${x},${y}`)).size).toBe(72)
    for (const first of result.nodes)
      for (const second of result.nodes) {
        if (first.index < second.index)
          expect(Math.hypot(first.x - second.x, first.y - second.y)).toBeGreaterThan(
            first.radius + second.radius,
          )
      }
  })

  it('handles unavailable or unmatched graphs', () => {
    const result = explorerLayout({ entities: [], relationships: [] })
    expect(result.nodes).toEqual([])
    expect(result.edges).toEqual([])
    expect(adjacentIds(result, 'missing').size).toBe(0)
  })

  it('fits content bounds to the actual 795px presentation canvas without fixed-viewBox gaps', () => {
    const nodes = [
      { x: 220, y: 180, radius: 15 },
      { x: 920, y: 500, radius: 10 },
    ]
    const fit = fitGraphView(nodes, 765, 550)
    for (const node of nodes) {
      const x = (node.x - fit.centerX) * fit.scale + fit.offsetX
      const y = (node.y - fit.centerY) * fit.scale + fit.offsetY
      expect(x - node.radius * fit.scale).toBeGreaterThan(0)
      expect(x + node.radius * fit.scale).toBeLessThan(765)
      expect(y - node.radius * fit.scale).toBeGreaterThan(60)
      expect(y + node.radius * fit.scale).toBeLessThan(470)
    }
    expect(fit.scale).toBeGreaterThan(0.8)
    expect(fitGraphView(nodes, 480, 550).scale).toBeLessThan(fit.scale)
    expect(Number.isFinite(fitGraphView([], 300, 400).scale)).toBe(true)
  })

  it('labels all supported extraction types in Chinese', () => {
    expect(['content', 'event', 'naturalobject', 'organization'].map(entityTypeLabel)).toEqual([
      '知识内容',
      '事件',
      '自然物质',
      '机构',
    ])
  })
})
