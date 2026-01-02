import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { Settings } from '../types'

export function useSettings() {
  const [data, setData] = useState<Settings | null>(null)
  const [originalData, setOriginalData] = useState<Settings | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isDirty, setIsDirty] = useState(false)

  // Load settings
  const loadSettings = useCallback(async () => {
    setIsLoading(true)
    try {
      const settings = await api.getSettings()
      setData(settings)
      setOriginalData(settings)
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  // Update a setting
  const updateSetting = useCallback(<K extends keyof Settings>(
    key: K,
    value: Settings[K]
  ) => {
    setData(prev => {
      if (!prev) return prev
      const updated = { ...prev, [key]: value }
      setIsDirty(JSON.stringify(updated) !== JSON.stringify(originalData))
      return updated
    })
  }, [originalData])

  // Update nested setting (for approaches/media)
  const updateNestedSetting = useCallback(<
    K extends 'approaches' | 'media',
    NK extends string
  >(
    section: K,
    name: NK,
    updates: Partial<{ enabled: boolean; display_name: string }>
  ) => {
    setData(prev => {
      if (!prev) return prev
      const sectionData = prev[section] as Record<string, { enabled: boolean; display_name: string }>
      const updated = {
        ...prev,
        [section]: {
          ...sectionData,
          [name]: { ...sectionData[name], ...updates },
        },
      }
      setIsDirty(JSON.stringify(updated) !== JSON.stringify(originalData))
      return updated as Settings
    })
  }, [originalData])

  // Save settings
  const saveSettings = useCallback(async () => {
    if (!data) return false
    try {
      await api.updateSettings(data)
      setOriginalData(data)
      setIsDirty(false)
      return true
    } catch (error) {
      console.error('Failed to save settings:', error)
      return false
    }
  }, [data])

  // Reset to defaults
  const resetSettings = useCallback(async () => {
    try {
      await api.resetSettings()
      await loadSettings()
      return true
    } catch (error) {
      console.error('Failed to reset settings:', error)
      return false
    }
  }, [loadSettings])

  // Get enabled approaches
  const getEnabledApproaches = useCallback(() => {
    if (!data) return ['convergent']
    return Object.entries(data.approaches)
      .filter(([_, config]) => config.enabled)
      .map(([name]) => name)
  }, [data])

  // Get enabled media types
  const getEnabledMedia = useCallback(() => {
    if (!data) return []
    return Object.entries(data.media)
      .filter(([_, config]) => config.enabled)
      .map(([name]) => name)
  }, [data])

  // Toggle approach
  const toggleApproach = useCallback((name: string) => {
    updateNestedSetting('approaches', name, {
      enabled: !data?.approaches[name]?.enabled,
    })
  }, [data, updateNestedSetting])

  // Toggle media
  const toggleMedia = useCallback((name: string) => {
    updateNestedSetting('media', name, {
      enabled: !data?.media[name]?.enabled,
    })
  }, [data, updateNestedSetting])

  return {
    // State
    data,
    isLoading,
    isDirty,

    // Actions
    updateSetting,
    updateNestedSetting,
    saveSettings,
    resetSettings,
    loadSettings,

    // Utilities
    getEnabledApproaches,
    getEnabledMedia,
    toggleApproach,
    toggleMedia,
  }
}

export type UseSettingsReturn = ReturnType<typeof useSettings>
