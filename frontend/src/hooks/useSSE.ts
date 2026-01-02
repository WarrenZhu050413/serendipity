import { useState, useCallback, useRef } from 'react'
import type { Recommendation, Pairing, MoreRequest } from '../types'

interface SearchItem {
  tool: string
  query?: string
  message?: string
  url?: string
  timestamp: number
}

interface UseSSEOptions {
  onComplete: (recommendations: Recommendation[], pairings: Pairing[], batchTitle?: string) => void
  onError: (error: string) => void
}

export function useSSE({ onComplete, onError }: UseSSEOptions) {
  const [status, setStatus] = useState('')
  const [searches, setSearches] = useState<SearchItem[]>([])
  const eventSourceRef = useRef<EventSource | null>(null)

  const startStream = useCallback((request: Omit<MoreRequest, 'session_id'> & { sessionId: string }) => {
    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    // Clear previous search history
    setSearches([])
    setStatus('Connecting...')

    // We need to use fetch + ReadableStream for POST requests
    // EventSource only supports GET
    const abortController = new AbortController()

    const payload: MoreRequest = {
      session_id: request.sessionId,
      type: request.type,
      count: request.count,
      session_feedback: request.session_feedback,
      profile_diffs: request.profile_diffs,
      custom_directives: request.custom_directives,
    }

    fetch('/more/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(payload),
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Stream request failed: ${response.status}`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Parse SSE events from buffer
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // Keep incomplete line in buffer

          let currentEvent = ''
          let currentData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7)
            } else if (line.startsWith('data: ')) {
              currentData = line.slice(6)
            } else if (line === '' && currentEvent && currentData) {
              // End of event, process it
              try {
                const data = JSON.parse(currentData)
                handleEvent(currentEvent, data)
              } catch (e) {
                console.error('Failed to parse SSE data:', e)
              }
              currentEvent = ''
              currentData = ''
            }
          }
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('Stream error:', error)
          onError(error.message)
        }
      })

    function handleEvent(event: string, data: unknown) {
      switch (event) {
        case 'status': {
          const statusData = data as { message: string }
          setStatus(statusData.message)
          break
        }
        case 'tool_use': {
          const toolData = data as SearchItem
          setSearches((prev) => [...prev, { ...toolData, timestamp: Date.now() }])
          break
        }
        case 'complete': {
          const completeData = data as {
            success: boolean
            recommendations: Recommendation[]
            pairings: Pairing[]
            batch_title?: string
          }
          if (completeData.success) {
            onComplete(
              completeData.recommendations,
              completeData.pairings,
              completeData.batch_title
            )
          }
          setStatus('')
          break
        }
        case 'error': {
          const errorData = data as { error: string }
          onError(errorData.error)
          setStatus('')
          break
        }
      }
    }

    // Return abort function
    return () => {
      abortController.abort()
    }
  }, [onComplete, onError])

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  return {
    startStream,
    stopStream,
    status,
    searches,
  }
}
