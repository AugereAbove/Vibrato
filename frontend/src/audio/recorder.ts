import { concatChunks } from '../lib/wav'
import { engine } from './engine'

export interface LevelReading {
  peak: number
  rms: number
  time: number
}

export interface CapturedAudio {
  samples: Float32Array
  sampleRate: number
  startTime: number
}

interface Chunk {
  frame: number
  samples: Float32Array
}

const loadedContexts = new WeakSet<BaseAudioContext>()

export async function listInputDevices(): Promise<MediaDeviceInfo[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return []
  const devices = await navigator.mediaDevices.enumerateDevices()
  return devices.filter((d) => d.kind === 'audioinput')
}

export function microphoneSupported(): boolean {
  return Boolean(navigator.mediaDevices?.getUserMedia) && typeof AudioWorkletNode !== 'undefined'
}

export class Recorder {
  private stream: MediaStream | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private node: AudioWorkletNode | null = null
  private monitor: GainNode | null = null
  private sink: GainNode | null = null
  analyser: AnalyserNode | null = null
  private chunks: Chunk[] = []
  private levelListeners = new Set<(level: LevelReading) => void>()
  private stopResolver: (() => void) | null = null
  deviceLabel = ''
  inputLatency = 0

  get context(): AudioContext {
    return engine.audioContext()
  }

  get isOpen(): boolean {
    return this.stream !== null
  }

  onLevel(listener: (level: LevelReading) => void): () => void {
    this.levelListeners.add(listener)
    return () => {
      this.levelListeners.delete(listener)
    }
  }

  async open(deviceId?: string | null, monitorLevel = 0): Promise<void> {
    if (!microphoneSupported()) {
      throw new Error(
        'This browser cannot record audio here. Use a current Chrome, Edge or Firefox on localhost.',
      )
    }
    this.close()
    const ctx = this.context
    if (ctx.state === 'suspended') await ctx.resume()
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        channelCount: 1,
      },
    })
    const track = stream.getAudioTracks()[0]
    this.deviceLabel = track?.label ?? ''
    const settings = (track?.getSettings?.() ?? {}) as MediaTrackSettings & { latency?: number }
    this.inputLatency = typeof settings.latency === 'number' ? settings.latency : 0
    if (!loadedContexts.has(ctx)) {
      await ctx.audioWorklet.addModule('/worklets/recorder-processor.js')
      loadedContexts.add(ctx)
    }
    this.stream = stream
    this.source = ctx.createMediaStreamSource(stream)
    this.node = new AudioWorkletNode(ctx, 'recorder-processor', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      channelCount: 1,
    })
    this.sink = ctx.createGain()
    this.sink.gain.value = 0
    this.monitor = ctx.createGain()
    this.monitor.gain.value = monitorLevel
    this.analyser = ctx.createAnalyser()
    this.analyser.fftSize = 2048
    this.source.connect(this.node)
    this.source.connect(this.analyser)
    this.source.connect(this.monitor)
    this.monitor.connect(ctx.destination)
    this.node.connect(this.sink)
    this.sink.connect(ctx.destination)
    this.node.port.onmessage = (event: MessageEvent) => {
      const message = event.data as {
        type: string
        frame?: number
        samples?: Float32Array
        peak?: number
        rms?: number
        time?: number
      }
      if (message.type === 'chunk' && message.samples) {
        this.chunks.push({ frame: message.frame ?? 0, samples: message.samples })
      } else if (message.type === 'level') {
        const reading = { peak: message.peak ?? 0, rms: message.rms ?? 0, time: message.time ?? 0 }
        for (const listener of this.levelListeners) listener(reading)
      } else if (message.type === 'stopped') {
        this.stopResolver?.()
        this.stopResolver = null
      }
    }
  }

  setMonitorLevel(level: number): void {
    if (this.monitor) this.monitor.gain.setTargetAtTime(level, this.context.currentTime, 0.03)
  }

  start(): void {
    if (!this.node) throw new Error('The microphone is not open.')
    this.chunks = []
    this.node.port.postMessage({ type: 'start' })
  }

  async stop(): Promise<CapturedAudio> {
    if (!this.node) throw new Error('The microphone is not open.')
    const done = new Promise<void>((resolve) => {
      this.stopResolver = resolve
    })
    this.node.port.postMessage({ type: 'stop' })
    await Promise.race([done, new Promise<void>((resolve) => window.setTimeout(resolve, 600))])
    const chunks = this.chunks
    this.chunks = []
    const sampleRate = this.context.sampleRate
    const startFrame = chunks.length ? chunks[0].frame : 0
    return {
      samples: concatChunks(chunks.map((c) => c.samples)),
      sampleRate,
      startTime: startFrame / sampleRate,
    }
  }

  close(): void {
    try {
      this.source?.disconnect()
      this.node?.disconnect()
      this.monitor?.disconnect()
      this.sink?.disconnect()
      this.analyser?.disconnect()
    } catch {
      this.source = null
    }
    if (this.node) this.node.port.onmessage = null
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
    this.source = null
    this.node = null
    this.monitor = null
    this.sink = null
    this.analyser = null
  }
}

export function trimCapture(capture: CapturedAudio, fromTime: number, toTime?: number): Float32Array {
  const start = Math.max(0, Math.round((fromTime - capture.startTime) * capture.sampleRate))
  const end =
    toTime === undefined
      ? capture.samples.length
      : Math.min(capture.samples.length, Math.round((toTime - capture.startTime) * capture.sampleRate))
  return capture.samples.slice(start, Math.max(start, end))
}

export function scheduleClick(ctx: AudioContext, at: number, accent = false, level = 0.4): void {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.frequency.value = accent ? 1480 : 990
  gain.gain.setValueAtTime(0, at)
  gain.gain.linearRampToValueAtTime(level, at + 0.003)
  gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.07)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(at)
  osc.stop(at + 0.09)
}
