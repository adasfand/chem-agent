import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import type { Job, RunSummary } from '../src/types/api'
import { conversationChain, groupConversations } from '../src/utils/conversations'
import ConversationPanel from '../src/components/ConversationPanel.vue'

function round(id: string, parent: string | null, question: string, answer: string): Job {
  return {
    job_id: id,
    finished: true,
    cancel_requested: false,
    result: {
      run_id: `run-${id}`,
      parent_run_id: parent ? `run-${parent}` : null,
      question,
      answer,
      status: parent ? 'completed' : 'needs_input',
      started_at: '2026-10-10T00:00:00Z',
      plan: [],
      calls: [],
      evidence: [],
      citations: [],
    },
  }
}
const first = round('first', null, '1800 kg/h，从20℃加热到70℃，比热未知。', '请补充比热。')
const second = round('second', 'first', '比热为3.6 kJ/(kg·K)，其他条件不变。', '热负荷为90 kW。')
const third = round('third', 'second', '流量改为3600 kg/h。', '热负荷为180 kW。')
const unrelated = round('other', null, first.result.question, '另一个独立问题。')
const jobs = { first, second, third, other: unrelated }
const summaries = (...items: Job[]): RunSummary[] =>
  items.map((job) => ({
    job_id: job.job_id,
    run_id: job.result.run_id,
    question: job.result.question,
    status: job.result.status,
    created_at: job.result.started_at,
  }))

describe('conversation identity and display', () => {
  it('groups follow-ups under the original title and opens the newest round', () => {
    const runs = summaries(third, unrelated, second, first)
    const grouped = groupConversations(runs, jobs)
    expect(grouped).toHaveLength(2)
    expect(grouped[0]).toMatchObject({
      job_id: 'third',
      question: first.result.question,
      turn_count: 3,
      job_ids: ['third', 'second', 'first'],
    })
    expect(grouped[1]?.job_id).toBe('other')
    expect(conversationChain(third, runs, jobs).map((job) => job.job_id)).toEqual([
      'first',
      'second',
      'third',
    ])
  })

  it('does not invent expired ancestors and terminates cyclic malformed links', () => {
    expect(conversationChain(second, summaries(second), { second })).toEqual([second])
    const cycle = { ...first, result: { ...first.result, parent_run_id: 'run-second' } }
    expect(
      conversationChain(second, summaries(second, cycle), { first: cycle, second }),
    ).toHaveLength(2)
  })

  it('renders the missing-input answer and supplied-parameter result in one conversation', async () => {
    const html = await renderToString(
      createSSRApp(ConversationPanel, {
        job: second,
        turns: [first, second],
        loading: false,
        examples: [],
        busy: false,
      }),
    )
    expect(html).toContain(first.result.question)
    expect(html).toContain(first.result.answer)
    expect(html).toContain(second.result.question)
    expect(html).toContain('热负荷为90 kW。')
    expect(html).toContain('首次提问')
    expect(html).toContain('补充与追问')
  })
})
