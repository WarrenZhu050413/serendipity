import { useState } from 'react'
import type { UseSettingsReturn } from '../../hooks'

interface SettingsTabProps {
  settings: UseSettingsReturn
}

export function SettingsTab({ settings }: SettingsTabProps) {
  const [saveStatus, setSaveStatus] = useState('')

  const handleSave = async () => {
    setSaveStatus('Saving...')
    const success = await settings.saveSettings()
    setSaveStatus(success ? 'Saved!' : 'Failed')
    setTimeout(() => setSaveStatus(''), 2000)
  }

  const handleReset = async () => {
    if (!confirm('Reset all settings to defaults?')) return
    await settings.resetSettings()
  }

  if (!settings.data) {
    return <div className="tab-pane" id="tab-settings">Loading...</div>
  }

  const { data } = settings

  return (
    <div className="tab-pane active" id="tab-settings">
      {/* Generation Settings */}
      <div className="settings-section">
        <h3 className="section-title">Generation</h3>

        <div className="setting-row">
          <label className="setting-label">
            Model
            <span className="hint restart-hint">restart required</span>
          </label>
          <select
            className="setting-select"
            value={data.model}
            onChange={(e) => settings.updateSetting('model', e.target.value as 'opus' | 'sonnet' | 'haiku')}
          >
            <option value="opus">Opus</option>
            <option value="sonnet">Sonnet</option>
            <option value="haiku">Haiku</option>
          </select>
        </div>

        <div className="setting-row">
          <label className="setting-label">
            Count
            <span className="hint">per round</span>
          </label>
          <div className="setting-slider-row">
            <input
              type="range"
              className="setting-slider"
              min={3}
              max={20}
              value={data.total_count}
              onChange={(e) => settings.updateSetting('total_count', parseInt(e.target.value))}
            />
            <span className="slider-value">{data.total_count}</span>
          </div>
        </div>

        <div className="setting-row">
          <label className="setting-label">
            Thinking Tokens
            <span className="hint">extended thinking</span>
            <span className="hint restart-hint">restart required</span>
          </label>
          <input
            type="text"
            className="setting-input"
            placeholder="null (disabled)"
            value={data.thinking_tokens ?? ''}
            onChange={(e) => {
              const val = e.target.value.trim()
              settings.updateSetting('thinking_tokens', val ? parseInt(val) : null)
            }}
          />
        </div>

        <div className="setting-row">
          <label className="setting-label">Port</label>
          <input
            type="text"
            className="setting-input"
            value={data.feedback_server_port}
            onChange={(e) => settings.updateSetting('feedback_server_port', parseInt(e.target.value) || 9876)}
          />
        </div>
      </div>

      {/* Approaches */}
      <div className="settings-section">
        <h3 className="section-title">Approaches</h3>
        <div id="approaches-list">
          {Object.entries(data.approaches).map(([name, config]) => (
            <div key={name} className="toggle-row">
              <span className="toggle-label">{config.display_name}</span>
              <button
                className={`mini-toggle ${config.enabled ? 'active' : ''}`}
                onClick={() => settings.toggleApproach(name)}
              >
                <span className="toggle-knob" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Media Types */}
      <div className="settings-section">
        <h3 className="section-title">Media Types</h3>
        <div id="media-list">
          {Object.entries(data.media).map(([name, config]) => (
            <div key={name} className="toggle-row">
              <span className="toggle-label">{config.display_name}</span>
              <button
                className={`mini-toggle ${config.enabled ? 'active' : ''}`}
                onClick={() => settings.toggleMedia(name)}
              >
                <span className="toggle-knob" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Output */}
      <div className="settings-section">
        <h3 className="section-title">Output</h3>

        <div className="setting-row">
          <label className="setting-label">Format</label>
          <select
            className="setting-select"
            value={data.output.default_format}
            onChange={(e) => settings.updateSetting('output', {
              ...data.output,
              default_format: e.target.value as 'html' | 'markdown' | 'json'
            })}
          >
            <option value="html">HTML</option>
            <option value="markdown">Markdown</option>
            <option value="json">JSON</option>
          </select>
        </div>

        <div className="setting-row">
          <label className="setting-label">Destination</label>
          <select
            className="setting-select"
            value={data.output.default_destination}
            onChange={(e) => settings.updateSetting('output', {
              ...data.output,
              default_destination: e.target.value as 'browser' | 'stdout' | 'file'
            })}
          >
            <option value="browser">Browser</option>
            <option value="stdout">Terminal</option>
            <option value="file">File</option>
          </select>
        </div>
      </div>

      {/* Save/Reset */}
      <div className="settings-section">
        <div className="source-actions">
          <button className="save-btn" onClick={handleSave}>
            Save Settings
          </button>
          <button className="reset-btn" onClick={handleReset}>
            Reset to Defaults
          </button>
          <span className="save-status">{saveStatus}</span>
          {settings.isDirty && <span className="dirty-indicator">(unsaved)</span>}
        </div>
      </div>
    </div>
  )
}
