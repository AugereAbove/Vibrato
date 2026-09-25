class RecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.recording = false
    this.chunkSize = 4096
    this.chunk = new Float32Array(this.chunkSize)
    this.filled = 0
    this.chunkFrame = 0
    this.peak = 0
    this.sumSquares = 0
    this.count = 0
    this.levelEvery = Math.round(sampleRate * 0.05)
    this.port.onmessage = (event) => {
      const message = event.data || {}
      if (message.type === 'start') {
        this.filled = 0
        this.recording = true
      } else if (message.type === 'stop') {
        this.flush()
        this.recording = false
        this.port.postMessage({ type: 'stopped' })
      }
    }
  }

  flush() {
    if (this.filled === 0) return
    const samples = this.chunk.slice(0, this.filled)
    this.port.postMessage({ type: 'chunk', frame: this.chunkFrame, samples }, [samples.buffer])
    this.filled = 0
  }

  process(inputs) {
    const input = inputs[0]
    const channel = input && input[0]
    if (!channel) return true
    const frame = currentFrame
    for (let i = 0; i < channel.length; i += 1) {
      const value = channel[i]
      const magnitude = value < 0 ? -value : value
      if (magnitude > this.peak) this.peak = magnitude
      this.sumSquares += value * value
      this.count += 1
    }
    if (this.count >= this.levelEvery) {
      this.port.postMessage({
        type: 'level',
        peak: this.peak,
        rms: Math.sqrt(this.sumSquares / this.count),
        time: currentTime,
      })
      this.peak = 0
      this.sumSquares = 0
      this.count = 0
    }
    if (this.recording) {
      let offset = 0
      while (offset < channel.length) {
        if (this.filled === 0) this.chunkFrame = frame + offset
        const take = Math.min(channel.length - offset, this.chunkSize - this.filled)
        this.chunk.set(channel.subarray(offset, offset + take), this.filled)
        this.filled += take
        offset += take
        if (this.filled === this.chunkSize) {
          const samples = this.chunk
          this.port.postMessage({ type: 'chunk', frame: this.chunkFrame, samples }, [samples.buffer])
          this.chunk = new Float32Array(this.chunkSize)
          this.filled = 0
        }
      }
    }
    return true
  }
}

registerProcessor('recorder-processor', RecorderProcessor)
