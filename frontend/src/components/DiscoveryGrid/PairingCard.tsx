import type { Pairing } from '../../types'

interface PairingCardProps {
  pairing: Pairing
  isNew: boolean
  icons: Record<string, string>
}

export function PairingCard({ pairing, isNew, icons }: PairingCardProps) {
  const { type, title, content, url } = pairing

  // Map pairing type to icon
  const typeIcons: Record<string, string> = {
    tip: 'lightbulb',
    info: 'info',
    resource: 'link',
    music: 'music',
    food: 'utensils',
    quote: 'quote',
    discussion: 'message-circle',
    activity: 'activity',
    wine: 'wine',
    game: 'gamepad-2',
  }

  const iconPath = icons[typeIcons[type] || 'star']

  return (
    <div className={`pairing-card pairing-${type} ${isNew ? 'new-pairing' : ''}`}>
      <div className="pairing-icon">
        {iconPath ? (
          <svg
            className="pairing-icon-svg"
            viewBox="0 0 24 24"
            width={24}
            height={24}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            dangerouslySetInnerHTML={{ __html: iconPath }}
          />
        ) : (
          <span className="pairing-icon-fallback">✨</span>
        )}
      </div>
      <div className="pairing-content">
        <div className="pairing-title">{title}</div>
        <div className="pairing-text">{content}</div>
        {url && (
          <a
            className="pairing-link"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Learn more →
          </a>
        )}
      </div>
    </div>
  )
}
