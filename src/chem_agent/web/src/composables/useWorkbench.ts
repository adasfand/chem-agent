import { computed, shallowReactive } from 'vue'
import { ApiError, api as defaultApi } from '../services/api'
import type { Bootstrap, Job, RunSummary, Session, WorkbenchApi } from '../types/api'

export type Notice = { message: string; kind: 'error' | 'info' | 'warning' } | null

export interface VisibilitySource {
  readonly hidden: boolean
  addEventListener(type: 'visibilitychange', listener: () => void): void
  removeEventListener(type: 'visibilitychange', listener: () => void): void
}

/** One controller per browser app. Generation tokens keep stale responses out of the UI. */
export function createWorkbench(
  api: WorkbenchApi = defaultApi,
  pollMs = 900,
  visibility: VisibilitySource | undefined = typeof document === 'undefined' ? undefined : document,
) {
  const state = shallowReactive({
    bootstrap: null as Bootstrap | null,
    runs: [] as RunSummary[],
    job: null as Job | null,
    draft: '',
    booting: false,
    submitting: false,
    loadingId: null as string | null,
    cancelling: false,
    uncertainSubmission: false,
    connected: false,
    notice: null as Notice,
  })
  let generation = 0
  let sessionGeneration = 0
  let disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let pendingPoll: { id: string; version: number } | null = null
  let failures = 0
  let pendingSubmission: { question: string; previousIds: Set<string> } | null = null

  const running = computed(() => Boolean(state.job && !state.job.finished))
  const busy = computed(() => running.value || state.submitting || state.uncertainSubmission)
  const canSubmit = computed(() =>
    Boolean(
      state.bootstrap?.configured &&
      state.connected &&
      !busy.value &&
      !state.loadingId &&
      state.draft.trim() &&
      state.draft.trim().length <= 4000,
    ),
  )
  const current = (version: number) => !disposed && generation === version
  const stopPoll = () => {
    clearTimeout(timer)
    timer = undefined
  }
  const message = (error: unknown) =>
    error instanceof Error ? error.message : '请求未完成，请稍后重试。'
  const notify = (text: string, kind: NonNullable<Notice>['kind'] = 'info') => {
    state.notice = { message: text, kind }
  }

  function update(job: Job) {
    // A polling response may have been captured before the cancellation response.
    if (state.job?.job_id === job.job_id) {
      if (state.job.finished && !job.finished) return
      if (state.job.cancel_requested) job = { ...job, cancel_requested: true }
    }
    state.job = job
  }

  async function refreshSession() {
    const version = ++sessionGeneration
    const session = await api.session()
    if (!disposed && version === sessionGeneration) state.runs = session.runs
    return session
  }

  function adopt(job: Job, clearDraft = true) {
    state.job = job
    if (clearDraft) state.draft = ''
    state.loadingId = null
    state.connected = true
    failures = 0
    if (!job.finished) schedulePoll(job.job_id, generation)
  }

  function schedulePoll(id: string, version: number, immediately = false) {
    stopPoll()
    const retryDelay = Math.min(pollMs * 2 ** Math.min(failures, 3), 8000)
    timer = setTimeout(
      async () => {
        if (!current(version) || state.job?.job_id !== id || state.job.finished) return
        // A visibility change or cancellation may request a refresh during an existing poll.
        if (pendingPoll?.id === id && pendingPoll.version === version) return
        const poll = { id, version }
        pendingPoll = poll
        try {
          const job = await api.job(id)
          if (!current(version) || state.job?.job_id !== id) return
          update(job)
          failures = 0
          state.connected = true
          if (state.notice?.kind === 'error') state.notice = null
          if (state.job?.finished) {
            await refreshSession().catch(() => {
              /* Result remains usable if history refresh fails. */
            })
          } else schedulePoll(id, version)
        } catch (error) {
          if (!current(version)) return
          if (error instanceof ApiError && error.status === 404) {
            generation++
            state.job = null
            state.connected = true
            notify('任务记录已过期或后端已重启。请新建任务。', 'warning')
            await refreshSession().catch(() => {
              state.runs = []
            })
            return
          }
          state.connected = false
          failures++
          notify(message(error) + ' 正在自动重连，当前任务记录会保留。', 'error')
          schedulePoll(id, version)
        } finally {
          if (pendingPoll === poll) pendingPoll = null
        }
      },
      immediately ? 0 : visibility?.hidden ? Math.max(retryDelay, 5000) : retryDelay,
    )
  }

  function visibilityChanged() {
    if (!disposed && state.job && !state.job.finished && !state.booting) {
      schedulePoll(state.job.job_id, generation, !visibility?.hidden)
    }
  }
  visibility?.addEventListener('visibilitychange', visibilityChanged)

  async function loadJob(id: string) {
    if (state.submitting || state.uncertainSubmission) return
    if (running.value && state.job?.job_id !== id) {
      notify('当前任务仍在执行，请等待完成或停止后再切换记录。')
      return
    }
    const version = ++generation
    stopPoll()
    state.loadingId = id
    try {
      const job = await api.job(id)
      if (current(version)) adopt(job)
    } catch (error) {
      if (!current(version)) return
      notify(message(error), 'error')
      if (state.job && !state.job.finished) schedulePoll(state.job.job_id, version)
    } finally {
      if (current(version)) state.loadingId = null
    }
  }

  function startNew(question = '') {
    if (busy.value) {
      notify('请等待当前任务结束，或先停止任务。')
      return
    }
    generation++
    stopPoll()
    state.job = null
    state.loadingId = null
    state.draft = question
    state.notice = null
  }

  function recoveredId(session: Session) {
    if (session.active_job_id) return session.active_job_id
    // Also recover a task that finished while its POST response was lost.
    return session.runs.find(
      (run) =>
        pendingSubmission &&
        !pendingSubmission.previousIds.has(run.job_id) &&
        run.question === pendingSubmission.question,
    )?.job_id
  }

  async function recoverSubmission(version: number) {
    const session = await refreshSession()
    const id = recoveredId(session)
    if (!current(version)) return
    if (id) {
      const job = await api.job(id)
      if (!current(version)) return
      adopt(job)
      notify('已恢复服务器接收的任务。')
    }
    pendingSubmission = null
    state.uncertainSubmission = false
    state.connected = true
  }

  async function submit() {
    if (!canSubmit.value) return
    const question = state.draft.trim()
    const parent = state.job?.job_id ?? null
    const version = ++generation
    stopPoll()
    state.submitting = true
    state.notice = null
    pendingSubmission = { question, previousIds: new Set(state.runs.map((run) => run.job_id)) }
    try {
      const job = await api.submit(question, parent)
      if (!current(version)) return
      pendingSubmission = null
      adopt(job)
      await refreshSession().catch(() => notify('任务已接收，历史列表稍后更新。'))
    } catch (error) {
      if (!current(version)) return
      notify(message(error), 'error')
      // Only ambiguous transport/server errors require reconciliation; never blindly retry POST.
      const ambiguous = !(error instanceof ApiError) || !error.status || error.status >= 500
      if (ambiguous || (error instanceof ApiError && error.status === 409)) {
        state.uncertainSubmission = true
        try {
          await recoverSubmission(version)
        } catch {
          if (current(version)) {
            state.connected = false
            notify('任务提交状态暂时未知。请点击“重新连接”确认后再提交，避免重复运行。', 'error')
          }
        }
      } else pendingSubmission = null
    } finally {
      if (current(version)) state.submitting = false
    }
  }

  async function cancel() {
    const job = state.job
    if (!job || job.finished || job.cancel_requested || state.cancelling) return
    const version = generation
    state.cancelling = true
    try {
      const response = await api.cancel(job.job_id)
      if (!current(version) || state.job?.job_id !== job.job_id) return
      update(response)
      if (response.finished) {
        stopPoll()
        await refreshSession().catch(() => {})
      } else schedulePoll(job.job_id, version)
    } catch (error) {
      if (current(version)) notify(message(error) + ' 停止请求尚未确认，请重试。', 'error')
    } finally {
      state.cancelling = false
    }
  }

  async function boot() {
    if (state.booting || state.submitting) return
    const version = ++generation
    state.booting = true
    stopPoll()
    try {
      const bootstrap = await api.bootstrap()
      if (!current(version)) return
      state.bootstrap = bootstrap
      state.runs = bootstrap.session.runs
      state.connected = true
      state.notice = null
      if (state.uncertainSubmission) {
        await recoverSubmission(version)
      } else {
        const restoringHistory = !bootstrap.session.active_job_id && !state.job
        const id =
          bootstrap.session.active_job_id ||
          state.job?.job_id ||
          (!state.draft.trim() ? state.runs[0]?.job_id : undefined)
        if (id) {
          try {
            const job = await api.job(id)
            // Reconnection must not discard an unsent follow-up or attach a new draft
            // to an unrelated historical task restored in the background.
            if (current(version) && !(restoringHistory && state.draft.trim())) adopt(job, false)
          } catch (error) {
            if (!current(version)) return
            if (error instanceof ApiError && error.status === 404) state.job = null
            else throw error
          }
        }
      }
    } catch (error) {
      if (current(version)) {
        state.connected = false
        notify(message(error), 'error')
        if (state.job && !state.job.finished) schedulePoll(state.job.job_id, version)
      }
    } finally {
      state.booting = false
    }
  }

  function dispose() {
    disposed = true
    generation++
    sessionGeneration++
    stopPoll()
    visibility?.removeEventListener('visibilitychange', visibilityChanged)
  }
  return { state, running, busy, canSubmit, boot, submit, cancel, startNew, loadJob, dispose }
}
export type Workbench = ReturnType<typeof createWorkbench>
