/**
 * Centralized icon exports from Lucide React.
 * Import icons from here for consistent usage across components.
 */
export {
  // UI Actions
  ThumbsUp,
  ThumbsDown,
  RotateCw,
  Moon,
  Sun,
  X,
  ChevronsLeft,
  ChevronsRight,
  Star,

  // View toggles
  List,
  Network,
  LayoutGrid,
  Focus,
  GitBranch,
  ArrowUp,

  // Media types
  BookOpen,
  Book,
  Headphones,
  Play,
  Music,
  Palette,
  Building,
  GraduationCap,
  Wrench,
  Mail,
  FileText,
  Link as LinkIcon,

  // Pairing types
  Lightbulb,
  Info,
  Quote,
  MessageCircle,
  Activity,
  Wine,
  Gamepad2,
  Utensils,
  Footprints,
  Target,

  // Approach types
  Crosshair,
  Compass,
} from 'lucide-react'

import type { LucideIcon } from 'lucide-react'
import {
  BookOpen,
  Book,
  Headphones,
  Play,
  Music,
  Palette,
  Building,
  GraduationCap,
  Wrench,
  Mail,
  FileText,
  Link,
  Lightbulb,
  Info,
  Quote,
  MessageCircle,
  Activity,
  Wine,
  Gamepad2,
  Utensils,
  Footprints,
  Target,
  Star,
  Crosshair,
  Compass,
} from 'lucide-react'

// Media type to icon mapping
export const mediaTypeIcons: Record<string, LucideIcon> = {
  article: BookOpen,
  book: Book,
  podcast: Headphones,
  video: Play,
  youtube: Play,
  music: Music,
  art: Palette,
  architecture: Building,
  course: GraduationCap,
  tool: Wrench,
  newsletter: Mail,
  paper: FileText,
  link: Link,
}

// Pairing type to icon mapping
// Includes both type keys (music, food) and display name variations (listen, taste)
export const pairingTypeIcons: Record<string, LucideIcon> = {
  // Type keys (from settings)
  tip: Lightbulb,
  music: Music,
  food: Utensils,
  exercise: Footprints,
  quote: Quote,
  action: Target,

  // Display name aliases (agent sometimes outputs these instead of keys)
  listen: Music,
  taste: Utensils,
  move: Footprints,
  try: Lightbulb,
  do: Target,

  // Legacy/other types
  info: Info,
  resource: Link,
  discussion: MessageCircle,
  activity: Activity,
  wine: Wine,
  game: Gamepad2,
  default: Star,
}

// Approach type to icon mapping
export const approachIcons: Record<string, LucideIcon> = {
  convergent: Crosshair,
  divergent: Compass,
}
