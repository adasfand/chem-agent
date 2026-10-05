import type { Bootstrap, Job, KnowledgeDetail, Session, WorkbenchApi } from '../types/api'
import { createKnowledgeCache } from './knowledgeCache'

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 15_000)
  try {
    const response = await fetch(path, {
      ...options,
      credentials: 'same-origin',
      signal: controller.signal,
      headers: {
        ...options.headers,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
    })
    const data: unknown = await response.json().catch(() => {
      // A successful POST may already have started a task even if its body was cut off.
      // Leave its status unknown so the controller reconciles with the session first.
      throw new ApiError(
        '服务返回了无法读取的数据，请检查后端是否启动。',
        response.ok ? undefined : response.status,
      )
    })
    if (!response.ok) {
      const detail =
        typeof data === 'object' && data !== null && 'detail' in data ? data.detail : null
      throw new ApiError(
        typeof detail === 'string' ? detail : '请求未完成，请稍后重试。',
        response.status,
      )
    }
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(
      error instanceof Error && error.name === 'AbortError'
        ? '连接超时，请检查后端服务。'
        : '无法连接后端服务，请确认服务仍在运行。',
    )
  } finally {
    clearTimeout(timer)
  }
}

const knowledgeCache = createKnowledgeCache((id) =>
  request<KnowledgeDetail>(`/api/knowledge/${encodeURIComponent(id)}`),
)

export const api: WorkbenchApi = {
  bootstrap: async () => {
    const bootstrap = await request<Bootstrap>('/api/bootstrap')
    knowledgeCache.clear()
    return bootstrap
  },
  session: () => request<Session>('/api/session'),
  job: (id) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  submit: (question, parentId) =>
    request<Job>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({ question, parent_job_id: parentId }),
    }),
  cancel: (id) => request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  knowledge: knowledgeCache.load,
}
export function exportUrl(id: string, format: 'report.md' | 'trace.json'): string {
  return `/api/jobs/${encodeURIComponent(id)}/${format}`
}
