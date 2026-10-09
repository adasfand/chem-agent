import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createWorkbench, type VisibilitySource } from '../src/composables/useWorkbench'
import { ApiError } from '../src/services/api'
import type { Bootstrap, Job, Session, WorkbenchApi } from '../src/types/api'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function job(id: string, finished = false, question = '计算显热负荷'): Job {
  return {
    job_id: id,
    finished,
    cancel_requested: false,
    result: {
      run_id: `run-${id}`,
      status: finished ? 'completed' : 'running',
      question,
      answer: finished ? '已完成计算。' : '',
      started_at: '2026-10-03T00:00:00Z',
      plan: [],
      calls: [],
      evidence: [],
      citations: [],
    },
  }
}

function session(...jobs: Job[]): Session {
  return {
    id: 'local-session',
    active_job_id: jobs.find((item) => !item.finished)?.job_id ?? null,
    runs: jobs.map((item) => ({
      job_id: item.job_id,
      question: item.result.question,
      status: item.result.status,
      created_at: item.result.started_at,
      run_id: item.result.run_id,
      client_request_id: item.client_request_id,
    })),
  }
}

function bootstrap(current = session(), configured = true): Bootstrap {
  return {
    version: '0.3.0',
    configured,
    model: 'test-model',
    examples: [],
    knowledge: [],
    session: current,
  }
}

function mockApi() {
  return {
    bootstrap: vi.fn<WorkbenchApi['bootstrap']>().mockResolvedValue(bootstrap()),
    session: vi.fn<WorkbenchApi['session']>().mockResolvedValue(session()),
    job: vi.fn<WorkbenchApi['job']>(),
    submit: vi.fn<WorkbenchApi['submit']>(),
    cancel: vi.fn<WorkbenchApi['cancel']>(),
    knowledge: vi.fn<WorkbenchApi['knowledge']>(),
  }
}

const controllers: ReturnType<typeof createWorkbench>[] = []
function controller(api: WorkbenchApi, visibility?: VisibilitySource) {
  const value = createWorkbench(api, 10, visibility)
  controllers.push(value)
  return value
}

function visibilitySource() {
  const listeners = new Set<() => void>()
  return {
    hidden: false,
    addEventListener: (_type: 'visibilitychange', listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: 'visibilitychange', listener: () => void) =>
      listeners.delete(listener),
    change(hidden: boolean) {
      this.hidden = hidden
      listeners.forEach((listener) => listener())
    },
    listeners,
  }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  controllers.splice(0).forEach((value) => value.dispose())
  vi.useRealTimers()
})

describe('workbench task lifecycle', () => {
  it('allows browsing without credentials while preventing model submission', async () => {
    const api = mockApi()
    api.bootstrap.mockResolvedValue(bootstrap(session(), false))
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '给出显热计算公式。'
    await workbench.submit()
    expect(workbench.state.connected).toBe(true)
    expect(workbench.canSubmit.value).toBe(false)
    expect(api.submit).not.toHaveBeenCalled()
  })

  it('rejects blank and overlong input before contacting the backend', async () => {
    const api = mockApi()
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '   '
    expect(workbench.canSubmit.value).toBe(false)
    workbench.state.draft = '字'.repeat(4001)
    await workbench.submit()
    expect(api.submit).not.toHaveBeenCalled()
  })

  it('locks repeat submission and passes the selected parent job for a follow-up', async () => {
    const api = mockApi()
    const parent = job('parent', true)
    parent.result.status = 'needs_input'
    api.bootstrap.mockResolvedValue(bootstrap(session(parent)))
    api.job.mockResolvedValue(parent)
    const pending = deferred<Job>()
    api.submit.mockReturnValue(pending.promise)
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '  比热为4.18 kJ/(kg·K)。  '
    const submitting = workbench.submit()
    await workbench.submit()
    expect(api.submit).toHaveBeenCalledExactlyOnceWith(
      '比热为4.18 kJ/(kg·K)。',
      'parent',
      expect.stringMatching(/^[a-f0-9]{32}$/),
    )
    pending.resolve(job('child'))
    await submitting
    expect(workbench.state.job?.job_id).toBe('child')
    expect(workbench.state.submitting).toBe(false)
  })

  it('ignores a history response after the user has started a new task', async () => {
    const api = mockApi()
    const pending = deferred<Job>()
    api.job.mockReturnValue(pending.promise)
    const workbench = controller(api)
    await workbench.boot()
    const loading = workbench.loadJob('old')
    workbench.startNew('新的独立任务')
    pending.resolve(job('old', true))
    await loading
    expect(workbench.state.job).toBeNull()
    expect(workbench.state.draft).toBe('新的独立任务')
    expect(workbench.state.loadingId).toBeNull()
  })

  it('recovers a finished task after its POST response is lost without resubmitting', async () => {
    const api = mockApi()
    const received = job('received', true, '查询定压比热')
    api.submit.mockImplementation(async (_question, _parent, requestId) => {
      received.client_request_id = requestId
      throw new ApiError('网络中断')
    })
    api.session.mockImplementation(async () => session(received))
    api.job.mockResolvedValue(received)
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = received.result.question
    await workbench.submit()
    expect(api.submit).toHaveBeenCalledTimes(1)
    expect(workbench.state.job?.job_id).toBe('received')
    expect(workbench.state.uncertainSubmission).toBe(false)
    expect(workbench.busy.value).toBe(false)
  })

  it('blocks an uncertain submission until reconnection resolves the server state', async () => {
    const api = mockApi()
    api.submit.mockRejectedValue(new ApiError('超时'))
    api.session.mockRejectedValueOnce(new ApiError('离线'))
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '查询定压比热'
    await workbench.submit()
    expect(workbench.state.uncertainSubmission).toBe(true)
    expect(workbench.busy.value).toBe(true)
    workbench.startNew('不应覆盖原任务')
    await workbench.submit()
    expect(workbench.state.draft).toBe('查询定压比热')
    expect(api.submit).toHaveBeenCalledTimes(1)
    const received = job('received', false, '查询定压比热')
    received.client_request_id = api.submit.mock.calls[0]?.[2]
    api.bootstrap.mockResolvedValue(bootstrap(session(received)))
    api.session.mockResolvedValue(session(received))
    api.job.mockResolvedValue(received)
    await workbench.boot()
    expect(workbench.state.uncertainSubmission).toBe(false)
    expect(workbench.state.job?.job_id).toBe('received')
  })

  it('retains the task during polling errors and resumes with a later response', async () => {
    const api = mockApi()
    const current = job('running')
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job
      .mockResolvedValueOnce(current)
      .mockRejectedValueOnce(new ApiError('暂时断线'))
      .mockResolvedValueOnce(job('running', true))
    const workbench = controller(api)
    await workbench.boot()
    await vi.advanceTimersByTimeAsync(10)
    expect(workbench.state.connected).toBe(false)
    expect(workbench.state.job?.job_id).toBe('running')
    expect(workbench.busy.value).toBe(true)
    await vi.advanceTimersByTimeAsync(20)
    expect(workbench.state.job?.finished).toBe(true)
    expect(workbench.state.connected).toBe(true)
  })

  it('polls less often in the background and refreshes immediately when the page returns', async () => {
    const api = mockApi()
    const current = job('running')
    const visibility = visibilitySource()
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job.mockResolvedValue(current)
    const workbench = controller(api, visibility)
    await workbench.boot()
    visibility.change(true)
    await vi.advanceTimersByTimeAsync(4999)
    expect(api.job).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(api.job).toHaveBeenCalledTimes(2)
    api.job.mockResolvedValue(job('running', true))
    visibility.change(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.job).toHaveBeenCalledTimes(3)
    expect(workbench.state.job?.finished).toBe(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.job).toHaveBeenCalledTimes(3)
  })

  it('does not overlap a pending poll when visibility changes', async () => {
    const api = mockApi()
    const current = job('running')
    const visibility = visibilitySource()
    const pending = deferred<Job>()
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job.mockResolvedValueOnce(current).mockReturnValueOnce(pending.promise)
    const workbench = controller(api, visibility)
    await workbench.boot()
    await vi.advanceTimersByTimeAsync(10)
    visibility.change(true)
    visibility.change(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.job).toHaveBeenCalledTimes(2)
    pending.resolve(job('running', true))
    await vi.advanceTimersByTimeAsync(0)
    expect(workbench.state.job?.finished).toBe(true)
  })

  it('removes the visibility listener and pending timer on disposal', async () => {
    const api = mockApi()
    const current = job('running')
    const visibility = visibilitySource()
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job.mockResolvedValue(current)
    const workbench = controller(api, visibility)
    await workbench.boot()
    expect(visibility.listeners.size).toBe(1)
    workbench.dispose()
    expect(visibility.listeners.size).toBe(0)
    visibility.change(false)
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.job).toHaveBeenCalledTimes(1)
  })

  it('clears expired task state when the backend returns 404', async () => {
    const api = mockApi()
    const current = job('expired')
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job.mockResolvedValueOnce(current).mockRejectedValueOnce(new ApiError('过期', 404))
    const workbench = controller(api)
    await workbench.boot()
    await vi.advanceTimersByTimeAsync(10)
    expect(workbench.state.job).toBeNull()
    expect(workbench.state.runs).toEqual([])
    expect(workbench.state.notice?.kind).toBe('warning')
    expect(workbench.busy.value).toBe(false)
  })

  it('does not regress a terminal cancellation when an older poll returns running', async () => {
    const api = mockApi()
    const current = job('task')
    const cancelled = job('task', true)
    cancelled.cancel_requested = true
    cancelled.result.status = 'cancelled'
    const stalePoll = deferred<Job>()
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job.mockResolvedValueOnce(current).mockReturnValueOnce(stalePoll.promise)
    api.cancel.mockResolvedValue(cancelled)
    const workbench = controller(api)
    await workbench.boot()
    await vi.advanceTimersByTimeAsync(10)
    await workbench.cancel()
    stalePoll.resolve(current)
    await vi.advanceTimersByTimeAsync(0)
    expect(workbench.state.job?.finished).toBe(true)
    expect(workbench.state.job?.result.status).toBe('cancelled')
    expect(workbench.state.job?.cancel_requested).toBe(true)
    await vi.advanceTimersByTimeAsync(10)
    expect(api.job).toHaveBeenCalledTimes(2)
  })

  it('releases a cancelled operation flag after the user moves to the next task', async () => {
    const api = mockApi()
    const current = job('old')
    api.bootstrap.mockResolvedValue(bootstrap(session(current)))
    api.job.mockResolvedValueOnce(current).mockResolvedValueOnce(job('old', true))
    const stopping = deferred<Job>()
    api.cancel.mockReturnValueOnce(stopping.promise).mockResolvedValueOnce(job('next'))
    api.submit.mockResolvedValue(job('next'))
    const workbench = controller(api)
    await workbench.boot()
    const cancelRequest = workbench.cancel()
    await vi.advanceTimersByTimeAsync(10)
    workbench.startNew('下一轮问题')
    await workbench.submit()
    stopping.resolve(job('old', true))
    await cancelRequest
    expect(workbench.state.job?.job_id).toBe('next')
    expect(workbench.state.cancelling).toBe(false)
    await workbench.cancel()
    expect(api.cancel).toHaveBeenLastCalledWith('next')
  })

  it('can reconnect again after an in-flight bootstrap is superseded by a new draft', async () => {
    const api = mockApi()
    const pending = deferred<Bootstrap>()
    api.bootstrap.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(bootstrap())
    const workbench = controller(api)
    const firstBoot = workbench.boot()
    workbench.startNew('待输入的新任务')
    pending.resolve(bootstrap())
    await firstBoot
    expect(workbench.state.booting).toBe(false)
    await workbench.boot()
    expect(api.bootstrap).toHaveBeenCalledTimes(2)
    expect(workbench.state.connected).toBe(true)
  })

  it('preserves an unsent follow-up when reconnecting the selected task', async () => {
    const api = mockApi()
    const previous = job('previous', true)
    api.bootstrap.mockResolvedValue(bootstrap(session(previous)))
    api.job.mockResolvedValue(previous)
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '请将入口温度改为 30℃。'
    await workbench.boot()
    expect(workbench.state.job?.job_id).toBe('previous')
    expect(workbench.state.draft).toBe('请将入口温度改为 30℃。')
  })

  it('keeps a new independent draft separate from historical tasks during reconnection', async () => {
    const api = mockApi()
    const previous = job('previous', true)
    api.bootstrap.mockResolvedValue(bootstrap(session(previous)))
    api.job.mockResolvedValue(previous)
    const workbench = controller(api)
    await workbench.boot()
    workbench.startNew('一个新的混合问题')
    await workbench.boot()
    expect(workbench.state.job).toBeNull()
    expect(workbench.state.draft).toBe('一个新的混合问题')
    expect(api.job).toHaveBeenCalledTimes(1)
  })

  it('keeps input typed while the initial history request is pending', async () => {
    const api = mockApi()
    const previous = job('previous', true)
    const pending = deferred<Job>()
    api.bootstrap.mockResolvedValue(bootstrap(session(previous)))
    api.job.mockReturnValue(pending.promise)
    const workbench = controller(api)
    const loading = workbench.boot()
    await vi.advanceTimersByTimeAsync(0)
    expect(api.job).toHaveBeenCalledTimes(1)
    workbench.state.draft = '正在输入的新任务'
    pending.resolve(previous)
    await loading
    expect(workbench.state.job).toBeNull()
    expect(workbench.state.draft).toBe('正在输入的新任务')
  })

  it('does not mutate app state after the controller is disposed', async () => {
    const api = mockApi()
    const pending = deferred<Bootstrap>()
    api.bootstrap.mockReturnValue(pending.promise)
    const workbench = controller(api)
    const loading = workbench.boot()
    workbench.dispose()
    pending.resolve(bootstrap())
    await loading
    expect(workbench.state.bootstrap).toBeNull()
    expect(workbench.state.connected).toBe(false)
  })
})

// A second tab's task must never be mistaken for this POST's result.
describe('idempotent submission recovery', () => {
  it('retries the identical request ID when the session snapshot precedes acceptance', async () => {
    const api = mockApi()
    const accepted = job('accepted')
    api.submit.mockRejectedValueOnce(new ApiError('响应丢失')).mockResolvedValueOnce(accepted)
    api.session.mockResolvedValue(session(job('other-tab')))
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '计算本轮任务'
    await workbench.submit()
    expect(api.submit).toHaveBeenCalledTimes(2)
    expect(api.submit.mock.calls[1]).toEqual(api.submit.mock.calls[0])
    expect(workbench.state.job?.job_id).toBe('accepted')
    expect(api.job).not.toHaveBeenCalledWith('other-tab')
  })
  it('recovers the matching finished request even when a different tab is active', async () => {
    const api = mockApi()
    const accepted = job('accepted', true)
    api.submit.mockImplementation(async (_question, _parent, id) => {
      accepted.client_request_id = id
      throw new ApiError('响应丢失')
    })
    api.session.mockImplementation(async () => session(job('other-tab'), accepted))
    api.job.mockResolvedValue(accepted)
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = accepted.result.question
    await workbench.submit()
    expect(api.job).toHaveBeenCalledExactlyOnceWith('accepted')
    expect(api.submit).toHaveBeenCalledTimes(1)
  })
  it('keeps the draft editable after an explicit busy rejection', async () => {
    const api = mockApi()
    api.submit.mockRejectedValue(new ApiError('服务忙', 409))
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '待运行的问题'
    await workbench.submit()
    expect(workbench.state.draft).toBe('待运行的问题')
    expect(workbench.busy.value).toBe(false)
    expect(api.submit).toHaveBeenCalledTimes(1)
  })
})

describe('recovery rejection', () => {
  it('releases an uncertain follow-up when its parent expired during a restart', async () => {
    const api = mockApi()
    const parent = job('expired-parent', true)
    api.bootstrap.mockResolvedValue(bootstrap(session(parent)))
    api.job.mockResolvedValue(parent)
    api.session.mockResolvedValue(session())
    api.submit
      .mockRejectedValueOnce(new ApiError('连接中断'))
      .mockRejectedValueOnce(new ApiError('父任务已过期', 404))
    const workbench = controller(api)
    await workbench.boot()
    workbench.state.draft = '比热为4.18 kJ/(kg·K)'
    await workbench.submit()
    expect(workbench.state.uncertainSubmission).toBe(false)
    expect(workbench.state.job).toBeNull()
    expect(workbench.state.draft).toBe('比热为4.18 kJ/(kg·K)')
    expect(workbench.busy.value).toBe(false)
    expect(workbench.state.notice?.message).toBe('父任务已过期')
  })
})
