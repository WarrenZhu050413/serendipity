import { useState, useEffect, useCallback } from 'react'
import { Header } from './components/Header'
import { SidePanel } from './components/SidePanel'
import { DiscoveryGrid } from './components/DiscoveryGrid'
import { CanvasView } from './components/CanvasView'
import { LoadingOverlay } from './components/LoadingOverlay'
import { ThumbsUp, ThumbsDown, RotateCw } from './components/icons'
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

  // View mode
  const [viewMode, setViewMode] = useState<'list' | 'canvas'>('list')

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

  // Load user theme overrides
  useEffect(() => {
    const loadTheme = async () => {
      try {
        const response = await fetch('/api/theme.css')
        if (response.ok) {
          const css = await response.text()
          if (css.trim()) {
            // Inject user theme overrides
            const styleId = 'user-theme-overrides'
            let styleEl = document.getElementById(styleId) as HTMLStyleElement
            if (!styleEl) {
              styleEl = document.createElement('style')
              styleEl.id = styleId
              document.head.appendChild(styleEl)
            }
            styleEl.textContent = css
          }
        }
      } catch (error) {
        // Theme loading is optional - fail silently
        console.debug('No user theme overrides:', error)
      }
    }
    loadTheme()
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

  // Get enabled approaches for canvas grow
  const getEnabledApproaches = useCallback(() => {
    return settings.getEnabledApproaches()
  }, [settings])

  // Get profile diffs for canvas grow
  const getProfileDiffs = useCallback(() => {
    return profile.getProfileDiffs()
  }, [profile])

  return (
    <div className="app-container">
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
      />

      <div className="main-layout">
        <SidePanel
          profile={profile}
          settings={settings}
          icons={icons}
        />

        {viewMode === 'list' ? (
          <main className="center-panel">
            <div className="center-header">
              <div className="stats-bar">
                <div className="stat">Shown: <span>{stats.shown}</span></div>
                <div className="stat liked">
                  <ThumbsUp className="stat-icon" size={16} />
                  <span>{stats.liked}</span>
                </div>
                <div className="stat disliked">
                  <ThumbsDown className="stat-icon" size={16} />
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
                  <RotateCw size={16} />
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
        ) : (
          <CanvasView
            sessionId={sessionId}
            batches={batches}
            icons={icons}
            sessionFeedback={sessionFeedback}
            profileDiffs={getProfileDiffs()}
            getEnabledApproaches={getEnabledApproaches}
            onRating={handleRating}
            initialGrowCount={settings.data?.total_count ? Math.min(settings.data.total_count, 5) : 5}
          />
        )}
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

export default App
