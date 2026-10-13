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
  started_at?: string
  finished_at?: string
  latency_ms?: number
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
export interface ModelEvent {
  requested_at?: string
  finished_at?: string
  status?: 'pending' | 'succeeded' | 'failed'
  latency_ms?: number
  selected_tools?: string[]
  usage?: { input_tokens?: number; output_tokens?: number }
}
export interface RegisteredTool {
  name: string
  title: string
  description: string
  source: 'agent' | 'mcp'
  invocation: 'model' | 'manual'
  input_schema?: Record<string, JsonValue>
  output_schema?: Record<string, JsonValue> | null
  example?: Record<string, JsonValue>
}
export interface ToolRegistry {
  state: 'connected' | 'unavailable'
  server: string
  transport: string
  checked_at: string
  message?: string
  tools: RegisteredTool[]
}
export interface ManualToolResult {
  tool_name: string
  source: 'manual'
  server: string
  status: 'succeeded' | 'failed'
  started_at: string
  finished_at: string
  latency_ms: number
  arguments: Record<string, JsonValue>
  output: JsonValue
  error: string | null
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
  latency_ms?: number
  mode?: string
  model_events?: ModelEvent[]
  context_evidence?: { chunk_id: string; title: string; request_indices: number[] }[]
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
