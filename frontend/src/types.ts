// ============================================================
// Core Types - Match Python models in serendipity/models.py
// ============================================================

export interface Recommendation {
  url: string
  title: string
  reason: string
  media_type: string
  approach: 'convergent' | 'divergent'
  metadata?: Record<string, string>
}

export interface Pairing {
  type: 'tip' | 'info' | 'resource' | 'music' | 'food' | 'quote' | 'discussion' | 'activity'
  title: string
  content: string
  url?: string
}

export interface Batch {
  id: number
  title: string | null
  timestamp: string
  recommendations: Recommendation[]
  pairings: Pairing[]
}

// ============================================================
// Profile Types
// ============================================================

export interface Learning {
  id: string
  type: 'like' | 'avoid'
  title: string
  content: string
}

export interface HistoryEntry {
  url: string
  title?: string
  reason?: string
  type?: string
  rating?: number
  feedback?: 'liked' | 'disliked' | null
  timestamp: string
  session_id: string
  media_type?: string
}

export interface ContextSource {
  name: string
  type: 'mcp' | 'loader' | 'feedback'
  description?: string
  enabled: boolean
}

// ============================================================
// Settings Types
// ============================================================

export interface ApproachConfig {
  enabled: boolean
  display_name: string
}

export interface MediaConfig {
  enabled: boolean
  display_name: string
}

export interface OutputConfig {
  default_format: 'html' | 'markdown' | 'json'
  default_destination: 'browser' | 'stdout' | 'file'
}

export interface Settings {
  model: 'opus' | 'sonnet' | 'haiku'
  total_count: number
  feedback_server_port: number
  thinking_tokens: number | null
  output: OutputConfig
  approaches: Record<string, ApproachConfig>
  media: Record<string, MediaConfig>
}

// ============================================================
// Session & Feedback Types
// ============================================================

export interface SessionFeedback {
  url: string
  rating: number
}

export interface ProfileDiffs {
  taste?: string
}

// ============================================================
// SSE Event Types
// ============================================================

export interface SSEStatusEvent {
  event: 'status'
  data: { message: string }
}

export interface SSEToolUseEvent {
  event: 'tool_use'
  data: {
    tool: string
    query?: string
    message?: string
    url?: string
  }
}

export interface SSECompleteEvent {
  event: 'complete'
  data: {
    success: boolean
    recommendations: Recommendation[]
    pairings: Pairing[]
    batch_title?: string
  }
}

export interface SSEErrorEvent {
  event: 'error'
  data: { error: string }
}

export type SSEEvent = SSEStatusEvent | SSEToolUseEvent | SSECompleteEvent | SSEErrorEvent

// ============================================================
// API Request Types
// ============================================================

export interface MoreRequest {
  session_id: string
  type: string
  count: number
  session_feedback: SessionFeedback[]
  profile_diffs?: ProfileDiffs
  custom_directives?: string
}

export interface SessionInitResponse {
  session_id: string
  recommendations: Recommendation[]
  pairings: Pairing[]
  icons: Record<string, string>
}

// ============================================================
// Canvas View Types
// ============================================================

export interface TreeCard {
  id: string
  recommendation: Recommendation
  gen: number
  parentId: string | null
  children: string[]
  isNew?: boolean
}

export interface Connection {
  from: string
  to: string
}

export type ContextMode = 'just_this' | 'include_parent' | 'full_chain'

// ============================================================
// Hook Return Types
// ============================================================

export interface ProfileState {
  taste: string
  learnings: Learning[]
  history: HistoryEntry[]
  sources: ContextSource[]
  isLoading: boolean
  isDirty: boolean
  originalTaste: string
  lastSentTaste: string
}

export interface SettingsState {
  data: Settings | null
  isLoading: boolean
  isDirty: boolean
}
