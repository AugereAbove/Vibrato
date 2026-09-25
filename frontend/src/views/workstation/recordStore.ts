import { create } from 'zustand'
import type { Region } from '../../state/workspace'

interface RecordState {
  open: boolean
  region: Region | null
  recording: boolean
}

export const useRecordStore = create<RecordState>(() => ({ open: false, region: null, recording: false }))

export function openRecorder(region: Region | null = null): void {
  useRecordStore.setState({ open: true, region })
}

export function closeRecorder(): void {
  useRecordStore.setState({ open: false, region: null, recording: false })
}
