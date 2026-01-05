import { StarRating } from '../StarRating'
import { mediaTypeIcons, approachIcons } from '../icons'
import type { Recommendation } from '../../types'

interface CardProps {
  recommendation: Recommendation
  rating?: number
  onRating: (rating: number) => void
  isNew: boolean
  index: number
  icons: Record<string, string>
}

export function Card({ recommendation, rating, onRating, isNew, index }: CardProps) {
  const { url, title, reason, media_type, approach, metadata } = recommendation

  // Get icon components (with fallback to null if not found)
  const MediaIcon = mediaTypeIcons[media_type] || null
  const ApproachIcon = approachIcons[approach] || null

  return (
    <div
      className={`discovery-card ${isNew ? 'new-card' : ''}`}
      data-url={url}
      data-approach={approach}
      data-media-type={media_type}
      style={{ animationDelay: isNew ? `${index * 0.05}s` : undefined }}
    >
      {/* Rating */}
      <div className="card-feedback">
        <StarRating
          rating={rating}
          onRate={onRating}
        />
      </div>

      {/* Tags - icons with text fallback */}
      <div className="card-tags">
        <span className={`card-tag approach-${approach}`} title={approach}>
          {ApproachIcon ? <ApproachIcon className="card-icon" size={14} /> : approach}
        </span>
        <span className={`card-tag media-${media_type}`} title={media_type}>
          {MediaIcon ? <MediaIcon className="card-icon" size={14} /> : media_type}
        </span>
      </div>

      {/* Title & Link */}
      <a
        className="card-title"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {title}
      </a>

      {/* Reason */}
      <p className="card-description">{reason}</p>

      {/* Metadata */}
      {metadata && Object.keys(metadata).length > 0 && (
        <div className="card-metadata">
          {Object.entries(metadata).map(([key, value]) => (
            <span key={key} className="metadata-item">
              <span className="metadata-label">{key}:</span> {value}
            </span>
          ))}
        </div>
      )}

      {/* URL preview */}
      <div className="card-url">
        {new URL(url).hostname}
      </div>
    </div>
  )
}
