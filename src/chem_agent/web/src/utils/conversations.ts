import type { ConversationSummary, Job, RunSummary } from '../types/api'

/** Only explicit backend parent links join rounds, never similar question text. */
export function groupConversations(runs: RunSummary[], jobs: Record<string, Job>) {
  const byRun = new Map(runs.filter((run) => run.run_id).map((run) => [run.run_id, run]))
  const groups = new Map<string, ConversationSummary>()
  for (const run of runs) {
    let root = run
    const visited = new Set([root.job_id])
    while (true) {
      const parentId = jobs[root.job_id]?.result.parent_run_id
      const parent = parentId ? byRun.get(parentId) : undefined
      if (!parent || visited.has(parent.job_id)) break
      root = parent
      visited.add(root.job_id)
    }
    const existing = groups.get(root.job_id)
    if (existing) {
      existing.job_ids.push(run.job_id)
      existing.turn_count++
    } else {
      groups.set(root.job_id, {
        ...run,
        question: root.question,
        latest_question: run.question,
        job_ids: [run.job_id],
        turn_count: 1,
      })
    }
  }
  // The backend session list is newest first; each entry opens its latest round.
  return [...groups.values()]
}

export function conversationChain(job: Job, runs: RunSummary[], jobs: Record<string, Job>) {
  const byRun = new Map(runs.filter((run) => run.run_id).map((run) => [run.run_id, run.job_id]))
  const turns: Job[] = []
  let current: Job | undefined = job
  const visited = new Set<string>()
  while (current && !visited.has(current.job_id)) {
    visited.add(current.job_id)
    turns.unshift(current)
    const parentId: string | null | undefined = current.result.parent_run_id
    current = parentId ? jobs[byRun.get(parentId) ?? ''] : undefined
  }
  return turns
}
