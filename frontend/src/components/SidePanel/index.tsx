import { useState } from 'react'
import { ProfileTab } from './ProfileTab'
import { SettingsTab } from './SettingsTab'
import type { UseProfileReturn, UseSettingsReturn } from '../../hooks'

interface SidePanelProps {
  profile: UseProfileReturn
  settings: UseSettingsReturn
  icons: Record<string, string>
}

export function SidePanel({ profile, settings, icons }: SidePanelProps) {
  const [activeTab, setActiveTab] = useState<'profile' | 'settings'>('profile')
  const [isCollapsed, setIsCollapsed] = useState(false)

  const handleTabChange = (tab: 'profile' | 'settings') => {
    // Warn if dirty
    if (tab === 'settings' && profile.isDirty) {
      if (!confirm('You have unsaved profile changes. Switch anyway?')) return
    }
    if (tab === 'profile' && settings.isDirty) {
      if (!confirm('You have unsaved settings changes. Switch anyway?')) return
    }
    setActiveTab(tab)
  }

  return (
    <aside className={`side-panel ${isCollapsed ? 'collapsed' : ''}`} id="side-panel">
      <nav className="tab-nav">
        <button
          className={`tab-btn ${activeTab === 'profile' ? 'active' : ''}`}
          onClick={() => handleTabChange('profile')}
        >
          Profile
        </button>
        <button
          className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => handleTabChange('settings')}
        >
          Settings
        </button>
        <button
          className="toggle-btn"
          onClick={() => setIsCollapsed(!isCollapsed)}
          title={isCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          <CollapseIcon />
        </button>
      </nav>

      <div className="tab-content">
        {activeTab === 'profile' && (
          <ProfileTab profile={profile} icons={icons} />
        )}
        {activeTab === 'settings' && (
          <SettingsTab settings={settings} />
        )}
      </div>
    </aside>
  )
}

function CollapseIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      width={16}
      height={16}
    >
      <polyline points="11 17 6 12 11 7" />
      <polyline points="18 17 13 12 18 7" />
    </svg>
  )
}
