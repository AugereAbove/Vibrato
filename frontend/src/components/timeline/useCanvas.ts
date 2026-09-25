import { useEffect, useLayoutEffect, useRef, useState } from 'react'

export interface CanvasSize {
  width: number
  height: number
  dpr: number
}

export function useElementSize<T extends HTMLElement>(): [
  React.RefObject<T | null>,
  { width: number; height: number },
] {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect
      setSize((previous) =>
        Math.abs(previous.width - rect.width) < 0.5 && Math.abs(previous.height - rect.height) < 0.5
          ? previous
          : { width: rect.width, height: rect.height },
      )
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, size]
}

export function useCanvasDraw(
  width: number,
  height: number,
  draw: (ctx: CanvasRenderingContext2D, size: CanvasSize) => void,
): React.RefObject<HTMLCanvasElement | null> {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const element = canvas.current
    if (!element || width <= 0 || height <= 0) return
    const frame = window.requestAnimationFrame(() => {
      const dpr = Math.min(3, window.devicePixelRatio || 1)
      const pixelWidth = Math.round(width * dpr)
      const pixelHeight = Math.round(height * dpr)
      if (element.width !== pixelWidth || element.height !== pixelHeight) {
        element.width = pixelWidth
        element.height = pixelHeight
      }
      const ctx = element.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      draw(ctx, { width, height, dpr })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [width, height, draw])
  return canvas
}

export function cssVar(name: string, fallback = '#888'): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

export function withAlpha(color: string, alpha: number): string {
  const trimmed = color.trim()
  if (trimmed.startsWith('#')) {
    const hex = trimmed.slice(1)
    const full =
      hex.length === 3
        ? hex
            .split('')
            .map((c) => c + c)
            .join('')
        : hex.slice(0, 6)
    const r = parseInt(full.slice(0, 2), 16)
    const g = parseInt(full.slice(2, 4), 16)
    const b = parseInt(full.slice(4, 6), 16)
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  const match = trimmed.match(/rgba?\(([^)]+)\)/)
  if (match) {
    const [r, g, b] = match[1].split(',').map((v) => v.trim())
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  return trimmed
}
