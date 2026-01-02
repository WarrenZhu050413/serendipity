import { StarRating } from '../StarRating'
import type { Recommendation } from '../../types'

interface CardProps {
  recommendation: Recommendation
  rating?: number
  onRating: (rating: number) => void
  isNew: boolean
  index: number
  icons: Record<string, string>
}

export function Card({ recommendation, rating, onRating, isNew, index, icons }: CardProps) {
  const { url, title, reason, media_type, approach, metadata } = recommendation

  // Get icon for media type
  const getIconHtml = (iconName: string) => {
    const path = icons[iconName]
    if (!path) return null
    return (
      <svg
        className="card-icon"
        viewBox="0 0 24 24"
        width={16}
        height={16}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        dangerouslySetInnerHTML={{ __html: path }}
      />
    )
  }

  // Map media type to icon name
  const mediaTypeIcons: Record<string, string> = {
    article: 'book-open',
    book: 'book',
    podcast: 'headphones',
    video: 'play',
    music: 'music',
    art: 'palette',
    architecture: 'building',
    course: 'graduation-cap',
    tool: 'wrench',
    newsletter: 'mail',
    paper: 'file-text',
  }

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

      {/* Tags */}
      <div className="card-tags">
        <span className={`card-tag approach-${approach}`}>
          {approach}
        </span>
        <span className={`card-tag media-${media_type}`}>
          {getIconHtml(mediaTypeIcons[media_type] || 'link')}
          {media_type}
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
