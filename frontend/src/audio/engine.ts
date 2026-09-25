import { IDENTITY_MAP, type TimeMap } from '../lib/timemap'

export type Side = 'ref' | 'take' | 'synthetic'
export type ListenMode = 'ref' | 'take' | 'both' | 'split' | 'synthetic'

export interface TrackConfig {
  id: string
  url: string
  stretchUrl?: (speed: number) => string
  lufs: number | null
  timeline?: 'own' | 'reference'
}

interface Track extends TrackConfig {
  buffers: Map<number, AudioBuffer>
  pending: Map<number, Promise<AudioBuffer>>
}

interface Voice {
  source: AudioBufferSourceNode
  gain: GainNode
  side: Side
}

interface Segment {
  primary: Side
  ctxStart: number
  ctxEnd: number
  ownStart: number
  speed: number
  timelineStart: number
  timelineEnd: number
  voices: Voice[]
}

export interface EngineState {
  playing: boolean
  mode: ListenMode
  speed: number
  alternate: boolean
  gainMatch: boolean
  countIn: boolean
  volume: number
  loading: boolean
  error: string | null
  hasRef: boolean
  hasTake: boolean
  hasSynthetic: boolean
  lastPrimary: Side
}

const LOOKAHEAD_S = 0.35
const TICK_MS = 40
const FADE_S = 0.012
const MAX_MATCH_DB = 12
const COUNT_IN_BEATS = 3

let decoder: OfflineAudioContext | null = null

function decodeContext(): OfflineAudioContext {
  if (!decoder) decoder = new OfflineAudioContext(1, 1, 44100)
  return decoder
}

export class AudioEngine {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  private tracks: Partial<Record<Side, Track>> = {}
  private map: TimeMap = IDENTITY_MAP
  private aligned = true
  private segments: Segment[] = []
  private loop: { start: number; end: number } | null = null
  private range: { start: number; end: number } | null = null
  private nextTimeline = 0
  private nextCtx = 0
  private loopIndex = 0
  private finished = false
  private pausedAt = 0
  private timer: number | null = null
  private clicks: AudioScheduledSourceNode[] = []
  private listeners = new Set<() => void>()
  private endListeners = new Set<() => void>()
  private generation = 0
  state: EngineState = {
    playing: false,
    mode: 'ref',
    speed: 1,
    alternate: false,
    gainMatch: true,
    countIn: false,
    volume: 0.9,
    loading: false,
    error: null,
    hasRef: false,
    hasTake: false,
    hasSynthetic: false,
    lastPrimary: 'ref',
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  getState = (): EngineState => this.state

  onEnded(listener: () => void): () => void {
    this.endListeners.add(listener)
    return () => {
      this.endListeners.delete(listener)
    }
  }

  private setState(patch: Partial<EngineState>): void {
    this.state = { ...this.state, ...patch }
    for (const listener of this.listeners) listener()
  }

  private context(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext({ latencyHint: 'interactive' })
      this.master = this.ctx.createGain()
      this.master.gain.value = this.state.volume
      this.master.connect(this.ctx.destination)
    }
    return this.ctx
  }

  audioContext(): AudioContext {
    return this.context()
  }

  setTracks(tracks: Partial<Record<Side, TrackConfig | null>>): void {
    let changed = false
    for (const side of ['ref', 'take', 'synthetic'] as Side[]) {
      if (!(side in tracks)) continue
      const config = tracks[side]
      const current = this.tracks[side]
      if (!config) {
        if (current) {
          delete this.tracks[side]
          changed = true
        }
        continue
      }
      if (current && current.id === config.id && current.url === config.url) {
        current.lufs = config.lufs
        current.timeline = config.timeline
        continue
      }
      this.tracks[side] = { ...config, buffers: new Map(), pending: new Map() }
      changed = true
      void this.load(side, 1).catch(() => undefined)
    }
    if (changed) {
      this.stopPlayback(false)
      this.setState({
        hasRef: Boolean(this.tracks.ref),
        hasTake: Boolean(this.tracks.take),
        hasSynthetic: Boolean(this.tracks.synthetic),
        mode: this.validMode(this.state.mode),
      })
    }
  }

  private validMode(mode: ListenMode): ListenMode {
    if (mode === 'synthetic' && !this.tracks.synthetic) return this.tracks.take ? 'take' : 'ref'
    if ((mode === 'take' || mode === 'both' || mode === 'split') && !this.tracks.take) return 'ref'
    if (mode === 'ref' && !this.tracks.ref && this.tracks.take) return 'take'
    return mode
  }

  setTimeMap(map: TimeMap, aligned: boolean): void {
    const position = this.position()
    const wasPlaying = this.state.playing
    this.map = map
    this.aligned = aligned
    if (wasPlaying) this.restartAt(position)
  }

  duration(side: Side = 'ref'): number {
    const track = this.tracks[side]
    const buffer = track?.buffers.get(1)
    return buffer ? buffer.duration : 0
  }

  private async load(side: Side, speed: number): Promise<AudioBuffer> {
    const track = this.tracks[side]
    if (!track) throw new Error(`No ${side} recording is loaded.`)
    const key = Math.round(speed * 100) / 100
    const cached = track.buffers.get(key)
    if (cached) return cached
    const pending = track.pending.get(key)
    if (pending) return pending
    const url = key === 1 || !track.stretchUrl ? track.url : track.stretchUrl(key)
    const promise = (async () => {
      const response = await fetch(url)
      if (!response.ok) throw new Error(`Audio request failed (${response.status}).`)
      const data = await response.arrayBuffer()
      const buffer = await decodeContext().decodeAudioData(data)
      track.buffers.set(key, buffer)
      return buffer
    })()
    track.pending.set(key, promise)
    try {
      return await promise
    } finally {
      track.pending.delete(key)
    }
  }

  async preload(sides: Side[] = ['ref', 'take'], speed = this.state.speed): Promise<void> {
    await Promise.all(sides.filter((s) => this.tracks[s]).map((s) => this.load(s, speed)))
  }

  private toOwn(side: Side, t: number): number {
    if (!this.aligned) return t
    if (side === 'ref') return t
    if (side === 'synthetic' && this.tracks.synthetic?.timeline === 'reference') return t
    return this.map.refToUser(t)
  }

  private toTimeline(side: Side, own: number): number {
    if (!this.aligned) return own
    if (side === 'ref') return own
    if (side === 'synthetic' && this.tracks.synthetic?.timeline === 'reference') return own
    return this.map.userToRef(own)
  }

  timelineDuration(): number {
    const ref = this.duration('ref')
    const take = this.duration('take')
    if (this.aligned) return ref || this.toTimeline('take', take)
    return Math.max(ref, take, this.duration('synthetic'))
  }

  private sidesFor(mode: ListenMode, index: number): { primary: Side; sides: Side[] } {
    const base: Side = mode === 'synthetic' ? 'synthetic' : mode === 'take' ? 'take' : 'ref'
    if (mode === 'both' || mode === 'split') return { primary: 'ref', sides: ['ref', 'take'] }
    if (this.state.alternate && this.loop && !this.range && index % 2 === 1) {
      const other: Side = base === 'ref' ? (this.tracks.take ? 'take' : 'ref') : 'ref'
      return { primary: other, sides: [other] }
    }
    return { primary: base, sides: [base] }
  }

  private matchGain(side: Side): number {
    if (!this.state.gainMatch) return 1
    const levels = (['ref', 'take', 'synthetic'] as Side[])
      .map((s) => this.tracks[s]?.lufs)
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    const own = this.tracks[side]?.lufs
    if (levels.length < 2 || own == null || !Number.isFinite(own)) return 1
    const target = Math.min(...levels)
    const db = Math.max(-MAX_MATCH_DB, Math.min(MAX_MATCH_DB, target - own))
    return 10 ** (db / 20)
  }

  private scheduleSegment(): boolean {
    const ctx = this.context()
    const speed = this.state.speed
    const repeat = this.range ? null : this.loop
    const endTimeline = this.range ? this.range.end : repeat ? repeat.end : this.timelineDuration()
    const startTimeline = this.nextTimeline
    if (endTimeline - startTimeline < 0.005) return false
    const { primary, sides } = this.sidesFor(this.state.mode, this.loopIndex)
    const key = Math.round(speed * 100) / 100
    let primaryDuration = 0
    const voices: Voice[] = []
    for (const side of sides) {
      const buffer = this.tracks[side]?.buffers.get(key)
      if (!buffer) continue
      const ownStart = this.toOwn(side, startTimeline)
      const ownEnd = Math.min(this.toOwn(side, endTimeline), buffer.duration * key)
      const offset = ownStart / key
      const length = Math.max(0, (ownEnd - ownStart) / key)
      if (length <= 0.005 || offset >= buffer.duration) continue
      const source = ctx.createBufferSource()
      source.buffer = buffer
      const gain = ctx.createGain()
      const level = this.matchGain(side) * (sides.length > 1 ? 0.75 : 1)
      gain.gain.setValueAtTime(0, this.nextCtx)
      gain.gain.linearRampToValueAtTime(level, this.nextCtx + FADE_S)
      gain.gain.setValueAtTime(level, Math.max(this.nextCtx + FADE_S, this.nextCtx + length - FADE_S))
      gain.gain.linearRampToValueAtTime(0, this.nextCtx + length)
      source.connect(gain)
      if (this.state.mode === 'split') {
        const pan = ctx.createStereoPanner()
        pan.pan.value = side === 'ref' ? -1 : 1
        gain.connect(pan)
        pan.connect(this.master as GainNode)
      } else {
        gain.connect(this.master as GainNode)
      }
      source.start(this.nextCtx, offset, length)
      voices.push({ source, gain, side })
      if (side === primary || primaryDuration === 0) primaryDuration = Math.max(primaryDuration, length)
    }
    if (voices.length === 0 || primaryDuration <= 0) return false
    const segment: Segment = {
      primary: voices.some((v) => v.side === primary) ? primary : voices[0].side,
      ctxStart: this.nextCtx,
      ctxEnd: this.nextCtx + primaryDuration,
      ownStart: this.toOwn(voices.some((v) => v.side === primary) ? primary : voices[0].side, startTimeline),
      speed: key,
      timelineStart: startTimeline,
      timelineEnd: endTimeline,
      voices,
    }
    for (const voice of voices) {
      if (voice.side !== segment.primary) voice.source.stop(segment.ctxEnd)
    }
    this.segments.push(segment)
    this.nextCtx = segment.ctxEnd
    if (repeat) {
      this.nextTimeline = repeat.start
      this.loopIndex += 1
    } else {
      this.finished = true
    }
    return true
  }

  private tick = (): void => {
    const ctx = this.ctx
    if (!ctx || !this.state.playing) return
    const now = ctx.currentTime
    this.segments = this.segments.filter((segment) => segment.ctxEnd > now - 0.5)
    while (!this.finished && this.nextCtx < now + LOOKAHEAD_S) {
      if (!this.scheduleSegment()) {
        this.finished = true
        break
      }
    }
    const last = this.segments[this.segments.length - 1]
    if (this.finished && (!last || now >= last.ctxEnd)) {
      const end = last ? last.timelineEnd : this.nextTimeline
      const range = this.range
      this.range = null
      this.stopPlayback(false)
      this.pausedAt = range ? range.start : Math.min(end, this.timelineDuration())
      this.setState({})
      for (const listener of this.endListeners) listener()
    }
  }

  position(): number {
    const ctx = this.ctx
    if (!ctx || !this.state.playing || this.segments.length === 0) return this.pausedAt
    const now = ctx.currentTime
    const current =
      this.segments.find((s) => now >= s.ctxStart && now < s.ctxEnd) ??
      (now < this.segments[0].ctxStart ? null : this.segments[this.segments.length - 1])
    if (!current) return this.segments[0].timelineStart
    const own =
      current.ownStart + Math.min(now - current.ctxStart, current.ctxEnd - current.ctxStart) * current.speed
    return this.toTimeline(current.primary, own)
  }

  currentSide(): Side {
    const ctx = this.ctx
    if (!ctx || !this.state.playing) return this.state.lastPrimary
    const now = ctx.currentTime
    const current = this.segments.find((s) => now >= s.ctxStart && now < s.ctxEnd)
    return current ? current.primary : this.state.lastPrimary
  }

  private clearVoices(fade: boolean): void {
    const ctx = this.ctx
    for (const segment of this.segments) {
      for (const voice of segment.voices) {
        try {
          if (ctx && fade) {
            const now = ctx.currentTime
            voice.gain.gain.cancelScheduledValues(now)
            voice.gain.gain.setValueAtTime(voice.gain.gain.value, now)
            voice.gain.gain.linearRampToValueAtTime(0, now + FADE_S)
            voice.source.stop(now + FADE_S + 0.005)
          } else {
            voice.source.stop()
          }
        } catch {
          continue
        }
      }
    }
    this.segments = []
    for (const click of this.clicks) {
      try {
        click.stop()
      } catch {
        continue
      }
    }
    this.clicks = []
  }

  private stopPlayback(fade: boolean): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer)
      this.timer = null
    }
    const side = this.currentSide()
    this.clearVoices(fade)
    this.finished = false
    if (this.state.playing) this.setState({ playing: false, lastPrimary: side })
  }

  private scheduleCountIn(at: number): number {
    const ctx = this.context()
    const beat = 0.5
    for (let i = 0; i < COUNT_IN_BEATS; i += 1) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.frequency.value = i === 0 ? 1320 : 880
      const t = at + i * beat
      gain.gain.setValueAtTime(0, t)
      gain.gain.linearRampToValueAtTime(0.35, t + 0.004)
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.08)
      osc.connect(gain)
      gain.connect(this.master as GainNode)
      osc.start(t)
      osc.stop(t + 0.1)
      this.clicks.push(osc)
    }
    return at + COUNT_IN_BEATS * beat
  }

  private restartAt(position: number, countIn = false, startAt = 0): void {
    const ctx = this.context()
    this.clearVoices(true)
    this.finished = false
    this.loopIndex = 0
    let start = position
    if (!this.range && this.loop && (start < this.loop.start || start >= this.loop.end - 0.01))
      start = this.loop.start
    this.nextTimeline = start
    this.nextCtx = Math.max(ctx.currentTime + 0.03, startAt)
    if (countIn) this.nextCtx = this.scheduleCountIn(this.nextCtx)
    this.pausedAt = start
    if (this.timer === null) this.timer = window.setInterval(this.tick, TICK_MS)
    this.tick()
  }

  async play(position?: number, keepRange = false, startAt = 0): Promise<void> {
    if (!keepRange) this.range = null
    const ctx = this.context()
    const generation = ++this.generation
    if (ctx.state === 'suspended') await ctx.resume()
    const mode = this.validMode(this.state.mode)
    const sides: Side[] =
      mode === 'both' || mode === 'split' ? ['ref', 'take'] : [mode === 'synthetic' ? 'synthetic' : mode]
    if (this.state.alternate) sides.push('ref', 'take')
    const needed = [...new Set(sides)].filter((s) => this.tracks[s])
    if (needed.length === 0) {
      this.setState({ error: 'Nothing to play yet.' })
      return
    }
    const missing = needed.filter(
      (s) => !this.tracks[s]?.buffers.get(Math.round(this.state.speed * 100) / 100),
    )
    if (missing.length) {
      this.setState({ loading: true, error: null })
      try {
        await Promise.all(missing.map((s) => this.load(s, this.state.speed)))
      } catch (error) {
        this.setState({ loading: false, error: error instanceof Error ? error.message : String(error) })
        return
      }
      this.setState({ loading: false })
      if (generation !== this.generation) return
    }
    let start = position ?? this.pausedAt
    const total = this.timelineDuration()
    if (start >= total - 0.02) start = this.loop && !this.range ? this.loop.start : 0
    this.setState({ playing: true, mode, error: null })
    this.restartAt(start, this.state.countIn && startAt === 0, startAt)
  }

  pause(): void {
    if (!this.state.playing) return
    const position = this.position()
    this.stopPlayback(true)
    this.pausedAt = position
    this.setState({})
  }

  toggle(): void {
    if (this.state.playing) this.pause()
    else void this.play()
  }

  stop(returnTo = 0): void {
    this.generation += 1
    this.range = null
    this.stopPlayback(true)
    this.pausedAt = returnTo
    this.setState({})
  }

  seek(position: number): void {
    this.range = null
    const clamped = Math.max(0, Math.min(position, this.timelineDuration() || position))
    if (this.state.playing) this.restartAt(clamped)
    else {
      this.pausedAt = clamped
      this.setState({})
    }
  }

  setMode(mode: ListenMode): void {
    const next = this.validMode(mode)
    if (next === this.state.mode) return
    const position = this.position()
    this.setState({ mode: next })
    if (this.state.playing) void this.play(position, true)
  }

  toggleAB(includeSynthetic = false): void {
    const order: ListenMode[] =
      includeSynthetic && this.tracks.synthetic ? ['ref', 'take', 'synthetic'] : ['ref', 'take']
    const index = order.indexOf(this.state.mode)
    this.setMode(order[(index + 1) % order.length])
  }

  setLoop(loop: { start: number; end: number } | null): void {
    const normalized = loop && loop.end - loop.start >= 0.05 ? { ...loop } : null
    const same =
      (normalized === null && this.loop === null) ||
      (normalized &&
        this.loop &&
        Math.abs(normalized.start - this.loop.start) < 1e-4 &&
        Math.abs(normalized.end - this.loop.end) < 1e-4)
    if (same) return
    this.loop = normalized
    if (this.state.playing) this.restartAt(this.position())
  }

  setSpeed(speed: number): void {
    const next = Math.max(0.25, Math.min(1, Math.round(speed * 100) / 100))
    if (next === this.state.speed) return
    const position = this.position()
    this.setState({ speed: next })
    if (this.state.playing) void this.play(position)
  }

  setAlternate(alternate: boolean): void {
    this.setState({ alternate })
    if (this.state.playing) this.restartAt(this.position())
  }

  setGainMatch(gainMatch: boolean): void {
    this.setState({ gainMatch })
    if (this.state.playing) this.restartAt(this.position())
  }

  setCountIn(countIn: boolean): void {
    this.setState({ countIn })
  }

  setVolume(volume: number): void {
    const value = Math.max(0, Math.min(1, volume))
    if (this.master && this.ctx) this.master.gain.setTargetAtTime(value, this.ctx.currentTime, 0.02)
    this.setState({ volume: value })
  }

  async playRange(mode: ListenMode, start: number, end: number): Promise<void> {
    if (end - start < 0.02) return
    this.setState({ mode: this.validMode(mode) })
    this.range = { start, end }
    await this.play(start, true)
  }

  rangeActive(): boolean {
    return this.range !== null
  }

  release(): void {
    this.stopPlayback(false)
    void this.ctx?.close()
    this.ctx = null
    this.master = null
  }
}

export const engine = new AudioEngine()
