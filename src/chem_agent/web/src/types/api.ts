export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
export type RunStatus =
  'running' | 'completed' | 'needs_input' | 'no_evidence' | 'failed' | 'out_of_scope' | 'cancelled'
export type StepStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
export interface PlanStep {
  step_id: string
  goal: string
  tool_name: string
  depends_on: string[]
  status: StepStatus
}
export interface ToolCall {
  call_id: string
  step_id: string
  tool_name: string
  status: StepStatus
  arguments?: Record<string, JsonValue> | null
  requested_arguments?: Record<string, JsonValue>
  input_refs?: {
    ref: string
    argument: string
    value: JsonValue
    unit?: string
    source_value?: JsonValue
    source_unit?: string
  }[]
  output?: Record<string, JsonValue>
  error?: JsonValue
  input_provenance?: Record<string, JsonValue>[]
}
export interface KnowledgeItem {
  doc_id: string
  title: string
  source: string
  chunk_count: number
}
export interface KnowledgeDetail extends KnowledgeItem {
  text: string
}
export interface Evidence {
  doc_id: string
  chunk_id: string
  title: string
  text: string
  source: string
  score?: number
}
export interface RunResult {
  run_id?: string
  parent_run_id?: string | null
  status: RunStatus
  question: string
  answer: string
  started_at: string
  finished_at?: string
  plan: PlanStep[]
  calls: ToolCall[]
  evidence: Evidence[]
  citations: string[]
  record_warning?: string
  answer_source?: string
  history?: { role: 'user' | 'assistant'; content: string }[]
}
export interface Job {
  job_id: string
  client_request_id?: string | null
  finished: boolean
  cancel_requested: boolean
  result: RunResult
}
export interface RunSummary {
  job_id: string
  question: string
  status: RunStatus
  created_at: string
  run_id?: string
  client_request_id?: string | null
}
export interface ConversationSummary extends RunSummary {
  job_ids: string[]
  turn_count: number
  latest_question: string
}
export interface Session {
  id: string
  active_job_id: string | null
  runs: RunSummary[]
}
export interface Example {
  title: string
  question: string
}
export interface Bootstrap {
  version: string
  configured: boolean
  model: string
  examples: Example[]
  knowledge: KnowledgeItem[]
  session: Session
  index_status?: {
    state: string
    backend: string
    message: string
    document_count: number
    chunk_count: number
  }
}
export interface WorkbenchApi {
  bootstrap(): Promise<Bootstrap>
  session(): Promise<Session>
  job(id: string): Promise<Job>
  submit(question: string, parentId: string | null, requestId?: string): Promise<Job>
  cancel(id: string): Promise<Job>
  knowledge(id: string): Promise<KnowledgeDetail>
}
