import { pairingTypeIcons } from '../icons'
import type { Pairing } from '../../types'

interface PairingCardProps {
  pairing: Pairing
  isNew: boolean
  icons: Record<string, string>
}

export function PairingCard({ pairing, isNew }: PairingCardProps) {
  const { type, title, content, url } = pairing

  // Get icon component for pairing type
  const PairingIcon = pairingTypeIcons[type] || pairingTypeIcons.default

  return (
    <div className={`pairing-card pairing-${type} ${isNew ? 'new-pairing' : ''}`}>
      <div className="pairing-icon">
        <PairingIcon className="pairing-icon-svg" size={24} />
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
