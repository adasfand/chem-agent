import type { RunResult, ToolCall } from '../types/api'
import { explorerLayout } from './graphExplorer'
import { graphLayout, retrievalFor, type RetrievalRecord } from './retrieval'
import { toolLabels } from './presentation'

export function runQueries(result: RunResult) {
  return result.calls
    .filter((call) => call.tool_name === 'search_knowledge' && call.status === 'succeeded')
    .map((call) => ({ ...retrievalFor(call), callId: call.call_id, stepId: call.step_id }))
}

export function runGraph(entities: RetrievalRecord[], relationships: RetrievalRecord[]) {
  // Resolve SDK aliases using the same rules as the evidence inspector. Missing
  // endpoints stay missing: the presentation must never fabricate extra entities.
  const matched = graphLayout(entities, relationships)
  const normalized = matched.nodes.map((node) => ({
    ...entities[node.index],
    id: node.id,
    name: node.name,
    type: node.type,
    degree: matched.edges.filter((edge) => edge.from === node || edge.to === node).length,
  }))
  const links = matched.edges.map((edge) => ({
    ...relationships[edge.index],
    source: edge.from.id,
    target: edge.to.id,
    originalIndex: edge.index,
  }))
  return {
    ...explorerLayout({ entities: normalized, relationships: links }),
    omitted: relationships.length - links.length,
  }
}

/** Keep automatic labels legible without removing any graph nodes or links. */
export function graphLabelIds(
  nodes: { id: string; name: string; degree: number; x: number; y: number; radius: number }[],
  selected: string,
  scale: number,
  fontSize: number,
  limit: number,
) {
  const boxes: { left: number; right: number; top: number; bottom: number }[] = []
  const ids = new Set<string>()
  const ranked = [...nodes].sort(
    (a, b) => Number(b.id === selected) - Number(a.id === selected) || b.degree - a.degree,
  )
  for (const node of ranked) {
    if (ids.size >= limit) break
    const label = node.name.length > 14 ? node.name.slice(0, 13) + '…' : node.name
    const width =
      Array.from(label).reduce(
        (sum, char) => sum + ((char.codePointAt(0) ?? 0) < 128 ? 0.6 : 1),
        0,
      ) * fontSize
    const box = {
      left: node.x * scale - width / 2 - 4,
      right: node.x * scale + width / 2 + 4,
      top: (node.y + node.radius + 17) * scale - fontSize - 3,
      bottom: (node.y + node.radius + 17) * scale + 4,
    }
    if (
      boxes.some(
        (other) =>
          box.left < other.right &&
          box.right > other.left &&
          box.top < other.bottom &&
          box.bottom > other.top,
      )
    )
      continue
    ids.add(node.id)
    boxes.push(box)
  }
  return ids
}

export function executionNetwork(result: RunResult) {
  const steps = new Map(result.plan.map((step) => [step.step_id, { ...step }]))
  for (const call of result.calls) {
    if (!steps.has(call.step_id))
      steps.set(call.step_id, {
        step_id: call.step_id,
        goal: toolLabels[call.tool_name] || call.tool_name,
        tool_name: call.tool_name,
        depends_on: [],
        status: call.status,
      })
  }
  const nodes = [...steps.values()].map((step, index) => {
    const calls = result.calls.filter((call) => call.step_id === step.step_id)
    return {
      id: step.step_id,
      title: toolLabels[step.tool_name] || step.tool_name,
      goal: step.goal,
      status: calls.at(-1)?.status || step.status,
      tool: step.tool_name,
      calls,
      index,
      layer: 0,
      x: 0,
      y: 0,
    }
  })
  const byId = new Map(nodes.map((node) => [node.id, node]))
  type Reference = NonNullable<ToolCall['input_refs']>[number]
  const edges = new Map<
    string,
    { from: string; to: string; planned: boolean; references: Reference[] }
  >()
  function link(from: string, to: string, planned: boolean, reference?: Reference) {
    if (from === to || !byId.has(from) || !byId.has(to)) return
    const key = JSON.stringify([from, to])
    const edge = edges.get(key) || { from, to, planned: false, references: [] }
    edge.planned ||= planned
    if (reference) edge.references.push(reference)
    edges.set(key, edge)
  }
  for (const step of steps.values())
    for (const predecessor of step.depends_on) link(predecessor, step.step_id, true)
  result.calls.forEach((call, index) => {
    for (const reference of call.input_refs || []) {
      const source = reference.ref.split('.')[0] || ''
      const exists = result.calls
        .slice(0, index)
        .some((prior) => prior.step_id === source && prior.status === 'succeeded')
      if (exists) link(source, call.step_id, false, reference)
    }
  })
  const links = [...edges.values()]
  // Topological levels, bounded even for malformed historical records. No edge
  // is added merely because two steps appear next to each other in the plan.
  const remaining = new Set(nodes.map((node) => node.id))
  while (remaining.size) {
    const ready = nodes.filter(
      (node) =>
        remaining.has(node.id) && !links.some((e) => e.to === node.id && remaining.has(e.from)),
    )
    if (!ready.length) break
    for (const node of ready) {
      node.layer = Math.max(
        0,
        ...links.filter((e) => e.to === node.id).map((e) => byId.get(e.from)!.layer + 1),
      )
      remaining.delete(node.id)
    }
  }
  const layers = Math.max(1, ...nodes.map((node) => node.layer + 1))
  const height = Math.max(
    260,
    ...nodes.map((node) => nodes.filter((other) => other.layer === node.layer).length * 102 + 60),
  )
  for (const node of nodes) {
    const peers = nodes.filter((other) => other.layer === node.layer)
    node.x = 24 + node.layer * 216
    node.y = (height - peers.length * 102) / 2 + peers.indexOf(node) * 102
  }
  return {
    nodes,
    edges: links.map((edge) => ({ ...edge, start: byId.get(edge.from)!, end: byId.get(edge.to)! })),
    width: Math.max(320, layers * 216 + 24),
    height,
    referenceCount: links.reduce((count, edge) => count + edge.references.length, 0),
  }
}

export function citationEvidence(result: RunResult) {
  const cited = new Set(result.citations)
  const context = new Set(
    result.context_evidence
      ?.filter((item) => item.request_indices.length)
      .map((item) => item.chunk_id),
  )
  const offline = result.mode?.startsWith('offline') ?? false
  return result.evidence.map((item) => ({
    ...item,
    cited: cited.has(item.chunk_id),
    inContext: !offline && context.has(item.chunk_id),
  }))
}
