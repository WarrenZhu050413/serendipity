import type {
  SessionInitResponse,
  Settings,
  Learning,
  HistoryEntry,
  ContextSource,
} from './types'

const API_BASE = ''

class ApiClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })
    if (!response.ok) {
      throw new Error(`${options.method || 'GET'} ${endpoint} failed: ${response.status}`)
    }
    return response.json()
  }

  // ============================================================
  // Session
  // ============================================================

  async getSessionInit(): Promise<SessionInitResponse> {
    return this.request('/api/session/init')
  }

  // ============================================================
  // Profile - Taste
  // ============================================================

  async getTaste(): Promise<{ content: string }> {
    return this.request('/api/profile/taste')
  }

  async saveTaste(content: string): Promise<{ success: boolean }> {
    return this.request('/api/profile/taste', {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
  }

  // ============================================================
  // Profile - Learnings
  // ============================================================

  async getLearnings(): Promise<{ learnings: Learning[] }> {
    return this.request('/api/profile/learnings')
  }

  async addLearning(learning: Omit<Learning, 'id'>): Promise<{ success: boolean; id: string }> {
    return this.request('/api/profile/learnings', {
      method: 'POST',
      body: JSON.stringify(learning),
    })
  }

  async deleteLearning(id: string): Promise<{ success: boolean }> {
    return this.request(`/api/profile/learnings/${id}`, {
      method: 'DELETE',
    })
  }

  async updateLearning(id: string, updates: Partial<Learning>): Promise<{ success: boolean }> {
    return this.request(`/api/profile/learnings/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  }

  // ============================================================
  // Profile - History
  // ============================================================

  async getHistory(limit = 20): Promise<{ history: HistoryEntry[] }> {
    return this.request(`/api/profile/history?limit=${limit}`)
  }

  async deleteHistoryEntry(url: string): Promise<{ success: boolean }> {
    return this.request(`/api/profile/history?url=${encodeURIComponent(url)}`, {
      method: 'DELETE',
    })
  }

  // ============================================================
  // Sources
  // ============================================================

  async getSources(): Promise<{ sources: ContextSource[] }> {
    return this.request('/api/sources')
  }

  async toggleSource(name: string): Promise<{ success: boolean; enabled: boolean }> {
    return this.request(`/api/sources/${name}/toggle`, {
      method: 'POST',
    })
  }

  // ============================================================
  // Settings
  // ============================================================

  async getSettings(): Promise<Settings> {
    const response = await this.request<{ settings: Settings }>('/api/settings')
    return response.settings
  }

  async updateSettings(updates: Partial<Settings>): Promise<{ success: boolean }> {
    return this.request('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  }

  async resetSettings(): Promise<{ success: boolean }> {
    return this.request('/api/settings/reset', {
      method: 'POST',
      body: JSON.stringify({}),
    })
  }

  // ============================================================
  // Feedback
  // ============================================================

  async submitFeedback(
    url: string,
    sessionId: string,
    rating: number
  ): Promise<{ success: boolean }> {
    return this.request('/feedback', {
      method: 'POST',
      body: JSON.stringify({ url, session_id: sessionId, rating }),
    })
  }
}

export const api = new ApiClient()
