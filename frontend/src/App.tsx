import { useState, useEffect } from 'react'
import { Header } from './components/Header'
import { SidePanel } from './components/SidePanel'
import { DiscoveryGrid } from './components/DiscoveryGrid'
import { LoadingOverlay } from './components/LoadingOverlay'
import { useSSE } from './hooks/useSSE'
import { useProfile } from './hooks/useProfile'
import { useSettings } from './hooks/useSettings'
import type { SessionFeedback, Batch } from './types'
import { api } from './api'

function App() {
  // Theme state
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (localStorage.getItem('serendipity-theme') as 'light' | 'dark') || 'light'
  })

  // Core data state
  const [batches, setBatches] = useState<Batch[]>([])
  const [sessionFeedback, setSessionFeedback] = useState<SessionFeedback[]>([])
  const [sessionId, setSessionId] = useState<string>('')
  const [icons, setIcons] = useState<Record<string, string>>({})

  // Stats
  const [stats, setStats] = useState({ shown: 0, liked: 0, disliked: 0 })

  // Loading state
  const [isLoading, setIsLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('')

  // Directives
  const [directives, setDirectives] = useState('')

  // Profile and settings hooks
  const profile = useProfile()
  const settings = useSettings()

  // SSE hook for streaming
  const { startStream, status, searches } = useSSE({
    onComplete: (recommendations, pairings, batchTitle) => {
      const newBatch: Batch = {
        id: Date.now(),
        title: batchTitle ?? null,
        timestamp: new Date().toISOString(),
        recommendations,
        pairings,
      }
      setBatches(prev => [newBatch, ...prev])
      setStats(prev => ({ ...prev, shown: prev.shown + recommendations.length }))
      setIsLoading(false)
    },
    onError: (error) => {
      console.error('SSE error:', error)
      setIsLoading(false)
    },
  })

  // Toggle theme
  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(newTheme)
    localStorage.setItem('serendipity-theme', newTheme)
  }

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const data = await api.getSessionInit()
        setSessionId(data.session_id)
        setIcons(data.icons || {})

        if (data.recommendations.length > 0 || data.pairings.length > 0) {
          const initialBatch: Batch = {
            id: 0,
            title: null,
            timestamp: new Date().toISOString(),
            recommendations: data.recommendations,
            pairings: data.pairings,
          }
          setBatches([initialBatch])
          setStats({ shown: data.recommendations.length, liked: 0, disliked: 0 })
        }
      } catch (error) {
        console.error('Failed to load initial data:', error)
      }
    }
    loadInitialData()
  }, [])

  // Handle rating
  const handleRating = async (url: string, rating: number) => {
    try {
      await api.submitFeedback(url, sessionId, rating)

      // Update session feedback
      setSessionFeedback(prev => {
        const existing = prev.find(f => f.url === url)
        if (existing) {
          return prev.map(f => f.url === url ? { ...f, rating } : f)
        }
        return [...prev, { url, rating }]
      })

      // Update stats
      setStats(prev => {
        const oldFeedback = sessionFeedback.find(f => f.url === url)
        let newLiked = prev.liked
        let newDisliked = prev.disliked

        // Remove old count
        if (oldFeedback) {
          if (oldFeedback.rating >= 4) newLiked--
          else if (oldFeedback.rating <= 2) newDisliked--
        }

        // Add new count
        if (rating >= 4) newLiked++
        else if (rating <= 2) newDisliked++

        return { ...prev, liked: newLiked, disliked: newDisliked }
      })
    } catch (error) {
      console.error('Failed to submit rating:', error)
    }
  }

  // Request more recommendations
  const handleRequestMore = async () => {
    setIsLoading(true)
    setLoadingMessage('Getting more recommendations...')

    const enabledApproaches = settings.getEnabledApproaches()
    const count = settings.data?.total_count || 10

    // Calculate profile diffs
    const profileDiffs = profile.getProfileDiffs()

    startStream({
      sessionId,
      type: enabledApproaches.join(','),
      count,
      session_feedback: sessionFeedback,
      profile_diffs: profileDiffs,
      custom_directives: directives,
    })
  }

  return (
    <div className="app-container">
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <div className="main-layout">
        <SidePanel
          profile={profile}
          settings={settings}
          icons={icons}
        />

        <main className="center-panel">
          <div className="center-header">
            <div className="stats-bar">
              <div className="stat">Shown: <span>{stats.shown}</span></div>
              <div className="stat liked">
                <ThumbsUpIcon />
                <span>{stats.liked}</span>
              </div>
              <div className="stat disliked">
                <ThumbsDownIcon />
                <span>{stats.disliked}</span>
              </div>
            </div>
            <div className="directives-row">
              <input
                type="text"
                className="directives-input"
                placeholder="More philosophy, avoid podcasts, shorter reads..."
                value={directives}
                onChange={(e) => setDirectives(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleRequestMore()
                  }
                }}
              />
              <button className="round-btn" onClick={handleRequestMore}>
                <RefreshIcon />
                Another Round
              </button>
            </div>
          </div>

          <DiscoveryGrid
            batches={batches}
            sessionFeedback={sessionFeedback}
            onRating={handleRating}
            icons={icons}
          />
        </main>
      </div>

      <LoadingOverlay
        isVisible={isLoading}
        message={loadingMessage}
        status={status}
        searches={searches}
      />
    </div>
  )
}

// Inline icon components (will be refactored to use icons system)
function ThumbsUpIcon() {
  return (
    <svg className="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
    </svg>
  )
}

function ThumbsDownIcon() {
  return (
    <svg className="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="23 4 23 10 17 10"></polyline>
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
    </svg>
  )
}

export default App
