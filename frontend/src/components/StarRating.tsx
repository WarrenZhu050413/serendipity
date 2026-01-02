import { useState } from 'react'

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
          <StarIcon filled={displayRating >= star} />
        </button>
      ))}
    </div>
  )
}

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      className="star-icon"
      viewBox="0 0 24 24"
      width={16}
      height={16}
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  )
}
