import { create } from 'zustand'
import type { SegmentLevel } from '../api/types'

export type Side = 'ref' | 'take'

export interface SelectedSegment {
  kind: 'segment'
  level: SegmentLevel
  refId: string | null
  takeId: string | null
  start: number
  end: number
  label: string
}

export interface SelectedEvent {
  kind: 'event'
  side: Side
  eventId: string
  type: string
  start: number
  end: number
  label: string
}

export interface SelectedFinding {
  kind: 'finding'
  key: string
  start: number
  end: number
  label: string
}

export type Selection = SelectedSegment | SelectedEvent | SelectedFinding

export interface Region {
  start: number
  end: number
}

export interface Pin {
  id: number
  time: number
  label: string
  values: { name: string; ref: string; take: string }[]
}

interface WorkspaceState {
  selection: Selection | null
  region: Region | null
  view: Region
  duration: number
  hover: number | null
  loop: Region | null
  loopEnabled: boolean
  pins: Pin[]
  ruler: { a: number; b: number | null } | null
  rulerActive: boolean
  focusKey: string | null
  whyRegion: Region | null
  pulse: number
}

export const useWorkspace = create<WorkspaceState>(() => ({
  selection: null,
  region: null,
  view: { start: 0, end: 10 },
  duration: 10,
  hover: null,
  loop: null,
  loopEnabled: false,
  pins: [],
  ruler: null,
  rulerActive: false,
  focusKey: null,
  whyRegion: null,
  pulse: 0,
}))

let pinCounter = 0

export function nextPinId(): number {
  pinCounter += 1
  return pinCounter
}

export function resetWorkspace(duration: number): void {
  useWorkspace.setState({
    selection: null,
    region: null,
    view: { start: 0, end: Math.max(1, duration) },
    duration: Math.max(1, duration),
    hover: null,
    loop: null,
    loopEnabled: false,
    pins: [],
    ruler: null,
    rulerActive: false,
    focusKey: null,
    whyRegion: null,
  })
}

export function select(selection: Selection | null): void {
  useWorkspace.setState((state) => ({ selection, pulse: state.pulse + 1 }))
}

export function setRegion(region: Region | null): void {
  useWorkspace.setState({ region })
}

export function setLoop(loop: Region | null, enabled = loop !== null): void {
  useWorkspace.setState({ loop, loopEnabled: enabled })
}
