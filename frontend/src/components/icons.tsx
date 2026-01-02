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
  Star,
} from 'lucide-react'

// Media type to icon mapping
export const mediaTypeIcons: Record<string, LucideIcon> = {
  article: BookOpen,
  book: Book,
  podcast: Headphones,
  video: Play,
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
export const pairingTypeIcons: Record<string, LucideIcon> = {
  tip: Lightbulb,
  info: Info,
  resource: Link,
  music: Music,
  food: Utensils,
  quote: Quote,
  discussion: MessageCircle,
  activity: Activity,
  wine: Wine,
  game: Gamepad2,
  default: Star,
}
