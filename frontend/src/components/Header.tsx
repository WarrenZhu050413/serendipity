import { List, Network, Moon, Sun } from './icons'

interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  viewMode: 'list' | 'canvas'
  onViewModeChange: (mode: 'list' | 'canvas') => void
}

export function Header({ theme, onToggleTheme, viewMode, onViewModeChange }: HeaderProps) {
  return (
    <header className="header-bar">
      <div className="header-brand">
        <h1 className="header-title">Serendipity</h1>
        <span className="header-subtitle">Discovery engine</span>
      </div>
      <div className="header-actions">
        {/* View toggle */}
        <div className="view-toggle">
          <button
            className={viewMode === 'list' ? 'active' : ''}
            onClick={() => onViewModeChange('list')}
            title="List view"
          >
            <List size={14} />
            List
          </button>
          <button
            className={viewMode === 'canvas' ? 'active' : ''}
            onClick={() => onViewModeChange('canvas')}
            title="Canvas view"
          >
            <Network size={14} />
            Canvas
          </button>
        </div>

        <button
          className="theme-toggle"
          onClick={onToggleTheme}
          title="Toggle dark mode"
        >
          {theme === 'dark' ? <Sun className="icon-sun" size={20} /> : <Moon className="icon-moon" size={20} />}
        </button>
      </div>
    </header>
  )
}
