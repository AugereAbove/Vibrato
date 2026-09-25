import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { CategoryId } from '../api/types'
import { defaultLayers, type LayerId } from '../lib/categories'
import type { ViewMode } from './prefs'

export type LaneId =
  | 'lyrics'
  | 'phonemes'
  | 'waveform'
  | 'pitch'
  | 'spectrogram'
  | 'loudness'
  | 'voice'
  | 'events'
  | 'heatmap'
  | 'alignment'

export const DEFAULT_LANE_HEIGHTS: Record<LaneId, number> = {
  lyrics: 46,
  phonemes: 30,
  waveform: 96,
  pitch: 230,
  spectrogram: 160,
  loudness: 76,
  voice: 76,
  events: 44,
  heatmap: 112,
  alignment: 48,
}

export type BottomTab = 'heatmap' | 'measurements' | 'scores' | 'vowels' | 'previews' | 'takes' | 'quality'

export interface TableFilters {
  category: CategoryId | 'all'
  minConfidence: number
  minMagnitude: number
  search: string
  onlyFlagged: boolean
}

interface UiState {
  sidebarWidth: number
  inspectorWidth: number
  bottomHeight: number
  sidebarOpen: boolean
  inspectorOpen: boolean
  bottomOpen: boolean
  coachOpen: boolean
  bottomTab: BottomTab
  layersByMode: Record<ViewMode, Record<LayerId, boolean>>
  laneHeights: Record<LaneId, number>
  timeMode: 'aligned' | 'raw'
  waveformMode: 'stacked' | 'overlay'
  spectrogramSource: 'take' | 'reference'
  heatmapView: 'phrase' | 'word' | 'fine'
  heatmapMask: boolean
  pitchUnits: 'notes' | 'cents'
  tableFilters: TableFilters
  sidebarSections: Record<string, boolean>
  onboardingDismissed: boolean
  lastProjectId: string | null
  paletteOpen: boolean
  shortcutsOpen: boolean
}

export const LIMITS = {
  sidebar: [200, 420],
  inspector: [280, 560],
  bottom: [140, 520],
} as const

export const useUi = create<UiState>()(
  persist(
    (): UiState => ({
      sidebarWidth: 256,
      inspectorWidth: 348,
      bottomHeight: 250,
      sidebarOpen: true,
      inspectorOpen: true,
      bottomOpen: true,
      coachOpen: true,
      bottomTab: 'heatmap',
      layersByMode: {
        coach: defaultLayers('coach'),
        analyst: defaultLayers('analyst'),
        research: defaultLayers('research'),
      },
      laneHeights: { ...DEFAULT_LANE_HEIGHTS },
      timeMode: 'aligned',
      waveformMode: 'stacked',
      spectrogramSource: 'take',
      heatmapView: 'phrase',
      heatmapMask: true,
      pitchUnits: 'notes',
      tableFilters: { category: 'all', minConfidence: 0, minMagnitude: 0, search: '', onlyFlagged: false },
      sidebarSections: {},
      onboardingDismissed: false,
      lastProjectId: null,
      paletteOpen: false,
      shortcutsOpen: false,
    }),
    {
      name: 'vibrato.layout',
      version: 1,
      partialize: (state) => {
        const { paletteOpen: _palette, shortcutsOpen: _shortcuts, ...rest } = state
        return rest
      },
    },
  ),
)

export function setUi(patch: Partial<UiState>): void {
  useUi.setState(patch)
}

export function toggleLayer(mode: ViewMode, layer: LayerId, value?: boolean): void {
  useUi.setState((state) => {
    const current = state.layersByMode[mode] ?? defaultLayers(mode)
    return {
      layersByMode: {
        ...state.layersByMode,
        [mode]: { ...current, [layer]: value ?? !current[layer] },
      },
    }
  })
}

export function setLayers(mode: ViewMode, layers: Partial<Record<LayerId, boolean>>): void {
  useUi.setState((state) => ({
    layersByMode: {
      ...state.layersByMode,
      [mode]: { ...(state.layersByMode[mode] ?? defaultLayers(mode)), ...layers },
    },
  }))
}

export function resetLayers(mode: ViewMode): void {
  useUi.setState((state) => ({ layersByMode: { ...state.layersByMode, [mode]: defaultLayers(mode) } }))
}

export function useLayers(mode: ViewMode): Record<LayerId, boolean> {
  return useUi((state) => state.layersByMode[mode]) ?? defaultLayers(mode)
}

export function setLaneHeight(lane: LaneId, height: number): void {
  useUi.setState((state) => ({
    laneHeights: { ...state.laneHeights, [lane]: Math.round(Math.max(24, Math.min(600, height))) },
  }))
}

export function resetLayout(): void {
  useUi.setState({
    sidebarWidth: 256,
    inspectorWidth: 348,
    bottomHeight: 250,
    sidebarOpen: true,
    inspectorOpen: true,
    bottomOpen: true,
    coachOpen: true,
    laneHeights: { ...DEFAULT_LANE_HEIGHTS },
  })
}
