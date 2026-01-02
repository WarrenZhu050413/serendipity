import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { Learning, HistoryEntry, ContextSource, ProfileDiffs } from '../types'

export function useProfile() {
  // State
  const [taste, setTaste] = useState('')
  const [originalTaste, setOriginalTaste] = useState('')
  const [lastSentTaste, setLastSentTaste] = useState('')
  const [learnings, setLearnings] = useState<Learning[]>([])
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [sources, setSources] = useState<ContextSource[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isDirty, setIsDirty] = useState(false)

  // Load all profile data
  const loadProfile = useCallback(async () => {
    setIsLoading(true)
    try {
      const [tasteData, learningsData, historyData, sourcesData] = await Promise.all([
        api.getTaste(),
        api.getLearnings(),
        api.getHistory(20),
        api.getSources(),
      ])

      const tasteContent = tasteData.content || ''
      setTaste(tasteContent)
      setOriginalTaste(tasteContent)
      setLastSentTaste(tasteContent)
      setLearnings(learningsData.learnings || [])
      setHistory(historyData.history || [])
      setSources(sourcesData.sources || [])
    } catch (error) {
      console.error('Failed to load profile:', error)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  // Taste operations
  const updateTaste = useCallback((newTaste: string) => {
    setTaste(newTaste)
    setIsDirty(newTaste !== originalTaste)
  }, [originalTaste])

  const saveTaste = useCallback(async () => {
    try {
      await api.saveTaste(taste)
      setOriginalTaste(taste)
      setIsDirty(false)
      return true
    } catch (error) {
      console.error('Failed to save taste:', error)
      return false
    }
  }, [taste])

  // Learning operations
  const deleteLearning = useCallback(async (id: string) => {
    try {
      await api.deleteLearning(id)
      setLearnings(prev => prev.filter(l => l.id !== id))
      return true
    } catch (error) {
      console.error('Failed to delete learning:', error)
      return false
    }
  }, [])

  // History operations
  const deleteHistoryEntry = useCallback(async (url: string) => {
    try {
      await api.deleteHistoryEntry(url)
      setHistory(prev => prev.filter(h => h.url !== url))
      return true
    } catch (error) {
      console.error('Failed to delete history entry:', error)
      return false
    }
  }, [])

  // Source operations
  const toggleSource = useCallback(async (name: string) => {
    try {
      const result = await api.toggleSource(name)
      setSources(prev =>
        prev.map(s => (s.name === name ? { ...s, enabled: result.enabled } : s))
      )
      return true
    } catch (error) {
      console.error('Failed to toggle source:', error)
      return false
    }
  }, [])

  // Get profile diffs for /more request
  const getProfileDiffs = useCallback((): ProfileDiffs | undefined => {
    if (taste === lastSentTaste) {
      return undefined
    }

    // Compute line-by-line diff
    const oldLines = lastSentTaste.split('\n')
    const newLines = taste.split('\n')

    const added: string[] = []
    const removed: string[] = []

    // Simple diff: lines in new but not old = added
    for (const line of newLines) {
      if (line.trim() && !oldLines.includes(line)) {
        added.push(line)
      }
    }

    // Lines in old but not new = removed
    for (const line of oldLines) {
      if (line.trim() && !newLines.includes(line)) {
        removed.push(line)
      }
    }

    if (added.length === 0 && removed.length === 0) {
      return undefined
    }

    let diffStr = ''
    if (added.length > 0) {
      diffStr += 'Added:\n' + added.map(l => `+ ${l}`).join('\n') + '\n'
    }
    if (removed.length > 0) {
      diffStr += 'Removed:\n' + removed.map(l => `- ${l}`).join('\n')
    }

    // Update lastSentTaste after computing diff
    setLastSentTaste(taste)

    return { taste: diffStr.trim() }
  }, [taste, lastSentTaste])

  // Get liked/disliked items from history
  const getLikedItems = useCallback(() => {
    return history.filter(h => h.rating && h.rating >= 4)
  }, [history])

  const getDislikedItems = useCallback(() => {
    return history.filter(h => h.rating && h.rating <= 2)
  }, [history])

  return {
    // State
    taste,
    originalTaste,
    learnings,
    history,
    sources,
    isLoading,
    isDirty,

    // Actions
    updateTaste,
    saveTaste,
    deleteLearning,
    deleteHistoryEntry,
    toggleSource,
    loadProfile,

    // Utilities
    getProfileDiffs,
    getLikedItems,
    getDislikedItems,
  }
}

export type UseProfileReturn = ReturnType<typeof useProfile>
