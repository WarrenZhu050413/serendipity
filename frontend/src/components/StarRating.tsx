import { useState } from 'react'
import { Star } from './icons'

interface StarRatingProps {
  rating?: number
  onRate: (rating: number) => void
}

export function StarRating({ rating, onRate }: StarRatingProps) {
  const [hoverRating, setHoverRating] = useState<number | null>(null)

  const displayRating = hoverRating ?? rating ?? 0

  return (
    <div className="star-rating">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          className={`star ${displayRating >= star ? 'filled' : ''} ${hoverRating === star ? 'hover' : ''}`}
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onRate(star)
          }}
          onMouseEnter={() => setHoverRating(star)}
          onMouseLeave={() => setHoverRating(null)}
          title={`Rate ${star} star${star > 1 ? 's' : ''}`}
        >
          <Star
            className="star-icon"
            size={16}
            fill={displayRating >= star ? 'currentColor' : 'none'}
          />
        </button>
      ))}
    </div>
  )
}
