interface LoadingOverlayProps {
  isVisible: boolean
  message: string
  status: string
  searches: Array<{
    tool: string
    query?: string
    message?: string
    url?: string
    timestamp: number
  }>
}

export function LoadingOverlay({ isVisible, message, status, searches }: LoadingOverlayProps) {
  if (!isVisible) return null

  return (
    <div className="loading-hint" id="loading-hint">
      <div className="loading-spinner" />
      <div className="loading-text">{message}</div>
      <div className="loading-details">{status}</div>

      {/* Search history during loading */}
      {searches.length > 0 && (
        <div className="search-history visible">
          <div className="search-history-header">
            <span>🔍 Search Activity</span>
            <span className="search-count">{searches.length} searches</span>
          </div>
          <div className="search-history-content">
            {searches.map((search, idx) => (
              <div key={idx} className="search-history-item">
                <span className="search-tool">{search.tool}</span>
                {search.query && (
                  <span className="search-query">{search.query}</span>
                )}
                {search.message && (
                  <span className="search-message">{search.message}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
