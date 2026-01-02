import { useState } from 'react'
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
                    <XIcon size={12} />
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
            <ThumbsUpIcon />
            Liked
          </button>
          <button
            className={`pref-tab ${prefTab === 'disliked' ? 'active' : ''}`}
            onClick={() => setPrefTab('disliked')}
          >
            <ThumbsDownIcon />
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
    <ThumbsUpIcon size={14} />
  ) : entry.feedback === 'disliked' ? (
    <ThumbsDownIcon size={14} />
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
        <XIcon size={12} />
      </button>
    </div>
  )
}

// ============================================================
// Icons
// ============================================================

function XIcon({ size = 24 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
    >
      <line x1={18} y1={6} x2={6} y2={18} />
      <line x1={6} y1={6} x2={18} y2={18} />
    </svg>
  )
}

function ThumbsUpIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      className="tab-icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
    </svg>
  )
}

function ThumbsDownIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      className="tab-icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
    </svg>
  )
}
