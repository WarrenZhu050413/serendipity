import { useState } from 'react'
import { X, ThumbsUp, ThumbsDown } from '../icons'
import type { UseProfileReturn } from '../../hooks'
import type { HistoryEntry } from '../../types'

interface ProfileTabProps {
  profile: UseProfileReturn
  icons: Record<string, string>
}

export function ProfileTab({ profile }: ProfileTabProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['taste']))
  const [prefTab, setPrefTab] = useState<'liked' | 'disliked'>('liked')
  const [saveStatus, setSaveStatus] = useState('')

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(section)) {
        next.delete(section)
      } else {
        next.add(section)
      }
      return next
    })
  }

  const handleSaveTaste = async () => {
    setSaveStatus('Saving...')
    const success = await profile.saveTaste()
    setSaveStatus(success ? 'Saved!' : 'Failed')
    setTimeout(() => setSaveStatus(''), 2000)
  }

  const likedItems = profile.getLikedItems()
  const dislikedItems = profile.getDislikedItems()
  const currentPrefItems = prefTab === 'liked' ? likedItems : dislikedItems

  return (
    <div className="tab-pane active" id="tab-profile">
      {/* Taste Source */}
      <SourceSection
        name="taste"
        type="loader"
        isExpanded={expandedSections.has('taste')}
        onToggle={() => toggleSection('taste')}
        meta={profile.taste ? 'loaded' : 'empty'}
      >
        <textarea
          className="taste-textarea"
          placeholder="Describe your interests..."
          value={profile.taste}
          onChange={(e) => profile.updateTaste(e.target.value)}
        />
        <div className="source-actions">
          <button className="save-btn" onClick={handleSaveTaste}>
            Save Taste
          </button>
          <span className="save-status">{saveStatus}</span>
          {profile.isDirty && <span className="dirty-indicator">(unsaved)</span>}
        </div>
      </SourceSection>

      {/* Learnings Source */}
      <SourceSection
        name="learnings"
        type="loader"
        isExpanded={expandedSections.has('learnings')}
        onToggle={() => toggleSection('learnings')}
        meta={`${profile.learnings.length} patterns`}
      >
        <div className="learning-list">
          {profile.learnings.length === 0 ? (
            <div className="empty-state">No learnings yet</div>
          ) : (
            profile.learnings.map(l => (
              <div key={l.id} className={`learning-item ${l.type}`}>
                <div className="learning-text">
                  <span className="learning-tag">{l.type === 'like' ? 'Like' : 'Avoid'}</span>
                  <strong>{l.title}</strong>
                  <p>{l.content}</p>
                </div>
                <div className="learning-actions">
                  <button
                    className="delete"
                    title="Delete"
                    onClick={() => profile.deleteLearning(l.id)}
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </SourceSection>

      {/* History Source */}
      <SourceSection
        name="history"
        type="loader"
        isExpanded={expandedSections.has('history')}
        onToggle={() => toggleSection('history')}
        meta={`${profile.history.length} recent`}
      >
        <div className="history-list">
          {profile.history.length === 0 ? (
            <div className="empty-state">No history yet</div>
          ) : (
            profile.history.slice(0, 20).map(h => (
              <HistoryItem
                key={h.url}
                entry={h}
                onDelete={() => profile.deleteHistoryEntry(h.url)}
              />
            ))
          )}
        </div>
      </SourceSection>

      {/* Preferences Section */}
      <SourceSection
        name="preferences"
        type="feedback"
        isExpanded={expandedSections.has('preferences')}
        onToggle={() => toggleSection('preferences')}
        meta={`${likedItems.length + dislikedItems.length} items`}
      >
        <div className="preferences-tabs">
          <button
            className={`pref-tab ${prefTab === 'liked' ? 'active' : ''}`}
            onClick={() => setPrefTab('liked')}
          >
            <ThumbsUp className="tab-icon" size={16} />
            Liked
          </button>
          <button
            className={`pref-tab ${prefTab === 'disliked' ? 'active' : ''}`}
            onClick={() => setPrefTab('disliked')}
          >
            <ThumbsDown className="tab-icon" size={16} />
            Disliked
          </button>
        </div>
        <div className="preferences-list">
          {currentPrefItems.length === 0 ? (
            <div className="empty-state">No {prefTab} items yet</div>
          ) : (
            currentPrefItems.map(h => (
              <HistoryItem
                key={h.url}
                entry={h}
                onDelete={() => profile.deleteHistoryEntry(h.url)}
              />
            ))
          )}
        </div>
      </SourceSection>

      {/* Context Sources (MCP etc) */}
      <SourceSection
        name="sources"
        type="mcp"
        isExpanded={expandedSections.has('sources')}
        onToggle={() => toggleSection('sources')}
        meta={`${profile.sources.filter(s => s.enabled).length}/${profile.sources.length}`}
      >
        <div id="sources-list">
          {profile.sources.map(s => (
            <div key={s.name} className="toggle-row">
              <span className="toggle-label">{s.name}</span>
              <button
                className={`mini-toggle ${s.enabled ? 'active' : ''}`}
                onClick={() => profile.toggleSource(s.name)}
              >
                <span className="toggle-knob" />
              </button>
            </div>
          ))}
        </div>
      </SourceSection>
    </div>
  )
}

// ============================================================
// Sub-components
// ============================================================

interface SourceSectionProps {
  name: string
  type: 'loader' | 'mcp' | 'feedback'
  isExpanded: boolean
  onToggle: () => void
  meta: string
  children: React.ReactNode
}

function SourceSection({ name, type, isExpanded, onToggle, meta, children }: SourceSectionProps) {
  return (
    <div className={`source-section ${isExpanded ? 'expanded' : ''}`} data-source={name}>
      <div className="source-header" onClick={onToggle}>
        <div className="source-info">
          <span className="source-status" />
          <span className="source-name">{name}</span>
          <span className="source-type">{type}</span>
        </div>
        <span className="source-meta">{meta}</span>
      </div>
      <div className="source-content">{children}</div>
    </div>
  )
}

interface HistoryItemProps {
  entry: HistoryEntry
  onDelete: () => void
}

function HistoryItem({ entry, onDelete }: HistoryItemProps) {
  const icon = entry.feedback === 'liked' ? (
    <ThumbsUp size={14} />
  ) : entry.feedback === 'disliked' ? (
    <ThumbsDown size={14} />
  ) : (
    <span>•</span>
  )

  return (
    <div className="history-item">
      <div className="history-item-content">
        <span className={`history-icon ${entry.feedback === 'disliked' ? 'disliked' : ''}`}>
          {icon}
        </span>
        <span className="history-title">{entry.title || entry.url}</span>
      </div>
      <button className="history-delete" title="Remove" onClick={onDelete}>
        <X size={12} />
      </button>
    </div>
  )
}
