import { useState } from 'react'
import { ProfileTab } from './ProfileTab'
import { SettingsTab } from './SettingsTab'
import { ChevronsLeft } from '../icons'
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
          <ChevronsLeft size={16} />
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
