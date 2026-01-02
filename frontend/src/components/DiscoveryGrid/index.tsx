import { useState } from 'react'
import { Card } from './Card'
import { PairingCard } from './PairingCard'
import type { Batch, SessionFeedback } from '../../types'

interface DiscoveryGridProps {
  batches: Batch[]
  sessionFeedback: SessionFeedback[]
  onRating: (url: string, rating: number) => void
  icons: Record<string, string>
}

export function DiscoveryGrid({ batches, sessionFeedback, onRating, icons }: DiscoveryGridProps) {
  const [filter, setFilter] = useState('')

  // Get rating for a URL
  const getRating = (url: string) => {
    return sessionFeedback.find(f => f.url === url)?.rating
  }

  // Filter cards by search term
  const filterCards = (cards: Batch['recommendations']) => {
    if (!filter.trim()) return cards
    const term = filter.toLowerCase()
    return cards.filter(rec =>
      rec.title.toLowerCase().includes(term) ||
      rec.reason.toLowerCase().includes(term) ||
      rec.media_type.toLowerCase().includes(term) ||
      rec.approach.toLowerCase().includes(term)
    )
  }

  return (
    <>
      {/* Filter row */}
      <div className="filter-row">
        <input
          type="text"
          className="content-filter"
          placeholder="Filter..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      {/* Discovery Grid */}
      <div className="discovery-grid" id="recommendations">
        {batches.map(batch => (
          <BatchContainer
            key={batch.id}
            batch={batch}
            filterCards={filterCards}
            getRating={getRating}
            onRating={onRating}
            icons={icons}
          />
        ))}
      </div>
    </>
  )
}

interface BatchContainerProps {
  batch: Batch
  filterCards: (cards: Batch['recommendations']) => Batch['recommendations']
  getRating: (url: string) => number | undefined
  onRating: (url: string, rating: number) => void
  icons: Record<string, string>
}

function BatchContainer({ batch, filterCards, getRating, onRating, icons }: BatchContainerProps) {
  const filteredCards = filterCards(batch.recommendations)
  const isNewBatch = batch.id > 0

  return (
    <div className={`batch-container ${isNewBatch ? 'new-batch' : ''}`}>
      {/* Batch header */}
      {batch.title && (
        <div className="batch-header">
          <span className="batch-title">{batch.title}</span>
          <span className="batch-time">
            {new Date(batch.timestamp).toLocaleTimeString()}
          </span>
        </div>
      )}

      {/* Pairings row */}
      {batch.pairings.length > 0 && (
        <div className="pairings-row">
          {batch.pairings.map((pairing, idx) => (
            <PairingCard
              key={`${batch.id}-pairing-${idx}`}
              pairing={pairing}
              isNew={isNewBatch}
              icons={icons}
            />
          ))}
        </div>
      )}

      {/* Cards grid */}
      <div className="cards-grid">
        {filteredCards.map((rec, idx) => (
          <Card
            key={rec.url}
            recommendation={rec}
            rating={getRating(rec.url)}
            onRating={(rating) => onRating(rec.url, rating)}
            isNew={isNewBatch}
            index={idx}
            icons={icons}
          />
        ))}
      </div>
    </div>
  )
}
