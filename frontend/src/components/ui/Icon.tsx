import type { CSSProperties } from 'react'

function circle(cx: number, cy: number, r: number): string {
  return `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`
}

const FILLED = new Set(['play', 'pause', 'stop', 'record', 'rewind', 'forward', 'more', 'star-filled', 'dot'])

const PATHS: Record<string, string[]> = {
  play: ['M8 5.5v13l10.5-6.5z'],
  pause: ['M7 5h3.5v14H7z', 'M13.5 5H17v14h-3.5z'],
  stop: ['M6.5 6.5h11v11h-11z'],
  record: [circle(12, 12, 6.5)],
  rewind: ['M11.5 6.5 5 12l6.5 5.5z', 'M19.5 6.5 13 12l6.5 5.5z'],
  forward: ['M12.5 6.5 19 12l-6.5 5.5z', 'M4.5 6.5 11 12l-6.5 5.5z'],
  loop: ['M17 2.5l3 3-3 3', 'M20 5.5H8a4 4 0 0 0-4 4V11', 'M7 21.5l-3-3 3-3', 'M4 18.5h12a4 4 0 0 0 4-4V13'],
  mic: [
    'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z',
    'M5.5 11a6.5 6.5 0 0 0 13 0',
    'M12 17.5V21',
    'M8.5 21h7',
  ],
  upload: ['M12 15V4', 'M7.5 8.5 12 4l4.5 4.5', 'M4.5 15v3.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V15'],
  download: ['M12 4v11', 'M7.5 10.5 12 15l4.5-4.5', 'M4.5 15v3.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V15'],
  plus: ['M12 5v14', 'M5 12h14'],
  minus: ['M5 12h14'],
  x: ['M6 6l12 12', 'M18 6 6 18'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  search: [circle(11, 11, 6.5), 'M20 20l-4.3-4.3'],
  sliders: ['M4 7h9', 'M17 7h3', 'M4 17h3', 'M11 17h9', circle(15, 7, 2), circle(9, 17, 2)],
  help: [circle(12, 12, 9), 'M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.8', 'M12 17.2v.1'],
  command: ['M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6z'],
  sun: [
    circle(12, 12, 4),
    'M12 2.5v2',
    'M12 19.5v2',
    'M4.6 4.6 6 6',
    'M18 18l1.4 1.4',
    'M2.5 12h2',
    'M19.5 12h2',
    'M4.6 19.4 6 18',
    'M18 6l1.4-1.4',
  ],
  moon: ['M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z'],
  monitor: ['M3.5 5.5h17v11h-17z', 'M9 20h6', 'M12 16.5V20'],
  'chevron-left': ['M14.5 6 8.5 12l6 6'],
  'chevron-right': ['M9.5 6l6 6-6 6'],
  'chevron-down': ['M6 9.5l6 6 6-6'],
  'chevron-up': ['M6 14.5l6-6 6 6'],
  star: ['M12 3.5l2.6 5.3 5.9.9-4.25 4.1 1 5.8L12 16.9l-5.25 2.7 1-5.8L3.5 9.7l5.9-.9z'],
  'star-filled': ['M12 3.5l2.6 5.3 5.9.9-4.25 4.1 1 5.8L12 16.9l-5.25 2.7 1-5.8L3.5 9.7l5.9-.9z'],
  folder: ['M3.5 7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z'],
  music: ['M9 18V5.5l10-2V16', circle(6.5, 18, 2.5), circle(16.5, 16, 2.5)],
  wave: ['M3 12h1.5', 'M7 8.5v7', 'M10.5 5v14', 'M14 8v8', 'M17.5 10v4', 'M21 12h-.5'],
  layers: ['M12 4 20.5 8.5 12 13 3.5 8.5z', 'M3.5 12.5 12 17l8.5-4.5', 'M3.5 16.5 12 21l8.5-4.5'],
  eye: ['M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z', circle(12, 12, 3)],
  'eye-off': [
    'M3 3l18 18',
    'M10.6 5.6A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.6 3.4',
    'M6.4 6.5C3.9 8.2 2.5 12 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.6-1.3',
    'M9.9 9.9a3 3 0 0 0 4.2 4.2',
  ],
  'zoom-in': [circle(11, 11, 6.5), 'M20 20l-4.3-4.3', 'M11 8.5v5', 'M8.5 11h5'],
  'zoom-out': [circle(11, 11, 6.5), 'M20 20l-4.3-4.3', 'M8.5 11h5'],
  fit: ['M4 9V4h5', 'M20 9V4h-5', 'M4 15v5h5', 'M20 15v5h-5'],
  target: [circle(12, 12, 8.5), circle(12, 12, 4.5), 'M12 11.9v.2'],
  activity: ['M3 12h4l3-7 4 14 3-7h4'],
  bars: ['M5 20V11', 'M12 20V4', 'M19 20v-7'],
  'trend-up': ['M3 17l6-6 4 4 8-8', 'M15 7h6v6'],
  'trend-down': ['M3 7l6 6 4-4 8 8', 'M15 17h6v-6'],
  alert: ['M12 3.5 21.5 20h-19z', 'M12 9.5v5', 'M12 17.3v.1'],
  info: [circle(12, 12, 9), 'M12 11v5.5', 'M12 7.7v.1'],
  lock: ['M6 10.5h12v10H6z', 'M8.5 10.5V7a3.5 3.5 0 0 1 7 0v3.5'],
  unlock: ['M6 10.5h12v10H6z', 'M8.5 10.5V7a3.5 3.5 0 0 1 6.8-1.2'],
  anchor: [circle(12, 5, 2), 'M12 7v14', 'M5 13a7 7 0 0 0 14 0', 'M8.5 10.5h7'],
  bookmark: ['M6.5 3.5h11V21L12 17l-5.5 4z'],
  trash: ['M4 7h16', 'M10 11v6', 'M14 11v6', 'M5.5 7l1 13h11l1-13', 'M9 7V4h6v3'],
  edit: ['M4 20h4L19 9l-4-4L4 16z', 'M13.5 6.5l4 4'],
  copy: ['M8.5 8.5h11v11h-11z', 'M15.5 8.5V4.5h-11v11h4'],
  headphones: ['M4 18v-5a8 8 0 0 1 16 0v5', 'M4 15.5h3v5H5a1 1 0 0 1-1-1z', 'M20 15.5h-3v5h2a1 1 0 0 0 1-1z'],
  gauge: ['M4.5 17a8 8 0 1 1 15 0', 'M12 13l4-4'],
  cpu: [
    'M7 7h10v10H7z',
    'M10 10h4v4h-4z',
    'M10 3v4',
    'M14 3v4',
    'M10 17v4',
    'M14 17v4',
    'M3 10h4',
    'M3 14h4',
    'M17 10h4',
    'M17 14h4',
  ],
  clock: [circle(12, 12, 9), 'M12 7v5l3.5 2'],
  list: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4.5 6h.1', 'M4.5 12h.1', 'M4.5 18h.1'],
  grid: ['M4 4h7v7H4z', 'M13 4h7v7h-7z', 'M4 13h7v7H4z', 'M13 13h7v7h-7z'],
  split: ['M12 3.5v17', 'M4 6.5h5v11H4z', 'M15 6.5h5v11h-5z'],
  undo: ['M9 14 4 9l5-5', 'M4 9h10.5a5.5 5.5 0 0 1 0 11H11'],
  redo: ['M15 14l5-5-5-5', 'M20 9H9.5a5.5 5.5 0 0 0 0 11H13'],
  refresh: [
    'M20 11a8 8 0 0 0-14.3-4.5L4 8.5',
    'M4 4v4.5h4.5',
    'M4 13a8 8 0 0 0 14.3 4.5L20 15.5',
    'M20 20v-4.5h-4.5',
  ],
  flag: ['M5 21V4', 'M5 4.5h11l-2 4 2 4H5'],
  more: [circle(6, 12, 1.4), circle(12, 12, 1.4), circle(18, 12, 1.4)],
  external: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'],
  flask: ['M9.5 3.5h5', 'M10.5 3.5v6L5 19a1.5 1.5 0 0 0 1.3 2h11.4A1.5 1.5 0 0 0 19 19l-5.5-9.5v-6'],
  shield: ['M12 3.5 19.5 6v6c0 4.5-3.2 7.6-7.5 9-4.3-1.4-7.5-4.5-7.5-9V6z'],
  database: [
    'M4.5 6c0-1.4 3.4-2.5 7.5-2.5s7.5 1.1 7.5 2.5-3.4 2.5-7.5 2.5S4.5 7.4 4.5 6z',
    'M4.5 6v12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5V6',
    'M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5',
  ],
  home: ['M4 11 12 4l8 7', 'M6 9.5V20h12V9.5'],
  user: [circle(12, 8, 3.5), 'M5 20a7 7 0 0 1 14 0'],
  users: [
    circle(9, 8.5, 3.2),
    'M3 19.5a6 6 0 0 1 12 0',
    'M15.5 5.6a3.2 3.2 0 0 1 0 5.8',
    'M17.5 13.8a6 6 0 0 1 3.5 5.7',
  ],
  dumbbell: ['M6.5 7v10', 'M17.5 7v10', 'M3.5 9.5v5', 'M20.5 9.5v5', 'M6.5 12h11'],
  compare: ['M8 7h9', 'M14 4l3 3-3 3', 'M16 17H7', 'M10 14l-3 3 3 3'],
  archive: ['M3.5 4.5h17v4h-17z', 'M5 8.5V19a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8.5', 'M10 12.5h4'],
  keyboard: ['M3 6.5h18v11H3z', 'M7 10h.1', 'M10.5 10h.1', 'M14 10h.1', 'M17.5 10h.1', 'M7.5 14h9'],
  volume: ['M4 9.5h3.5L12 5.5v13l-4.5-4H4z', 'M16 9a4 4 0 0 1 0 6', 'M18.5 6.5a7.5 7.5 0 0 1 0 11'],
  'volume-off': ['M4 9.5h3.5L12 5.5v13l-4.5-4H4z', 'M16 9.5l5 5', 'M21 9.5l-5 5'],
  ruler: ['M3 16.5 16.5 3 21 7.5 7.5 21z', 'M7 12.5l2 2', 'M10 9.5l2 2', 'M13 6.5l2 2'],
  pin: ['M12 21v-6', 'M8 3.5h8', 'M9.5 3.5v5L6.5 12h11l-3-3.5v-5'],
  timer: ['M10 2.5h4', 'M12 13V9', circle(12, 13, 8)],
  metronome: ['M8.5 3.5h7L19 20.5H5z', 'M12 16.5l4-9'],
  bulb: ['M9 18h6', 'M10 21h4', 'M12 3a6 6 0 0 0-3.5 10.9V16h7v-2.1A6 6 0 0 0 12 3z'],
  pitch: ['M3 16c2.5 0 3-8 6-8s3.5 8 6 8 3-5 6-5'],
  vowel: ['M4 12c2.5-3.5 13.5-3.5 16 0-2.5 4.5-13.5 4.5-16 0z'],
  vibrato: ['M3 12c1.5-3.5 3-3.5 4.5 0s3 3.5 4.5 0 3-3.5 4.5 0 3 3.5 4.5 0'],
  dynamics: ['M21 6 3 12l18 6'],
  phonation: ['M12 4v16', 'M8 7.5v9', 'M16 7.5v9', 'M4 10.5v3', 'M20 10.5v3'],
  articulation: ['M5 6h14', 'M12 6v13', 'M9 19h6'],
  breath: ['M3 9h11a3 3 0 1 0-3-3', 'M3 15h15a3 3 0 1 1-3 3', 'M3 12h8'],
  timbre: ['M4 20v-4', 'M8 20V9', 'M12 20v-7', 'M16 20V6', 'M20 20v-9'],
  dot: [circle(12, 12, 4)],
  sparkline: ['M3 15l4-3 3 2 5-6 3 3 3-2'],
  file: ['M6 3.5h8l4.5 4.5v12.5H6z', 'M13.5 3.5V8.5h5'],
  wand: ['M4 20 14.5 9.5', 'M16 3v3', 'M20.5 7.5h-3', 'M19.2 4.3l-2 2', 'M14.5 9.5l2 2'],
  history: ['M3.5 12a8.5 8.5 0 1 0 2.5-6', 'M3.5 4v4.5H8', 'M12 8v4.5l3 2'],
  calendar: ['M4 6h16v14H4z', 'M4 10h16', 'M8.5 3.5v4', 'M15.5 3.5v4'],
  logo: ['M4 12c1.2-3 2.4-3 3.6 0s2.4 3 3.6 0 2.4-3 3.6 0 2.4 3 3.6 0', 'M4 17.5h16', 'M4 6.5h16'],
}

export type IconName = keyof typeof PATHS

export function Icon({
  name,
  size = 16,
  className,
  style,
  title,
}: {
  name: string
  size?: number
  className?: string
  style?: CSSProperties
  title?: string
}) {
  const paths = PATHS[name] ?? PATHS.dot
  const filled = FILLED.has(name)
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className ? `icon ${className}` : 'icon'}
      style={style}
      fill={filled ? 'currentColor' : 'none'}
      stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
    >
      {title ? <title>{title}</title> : null}
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  )
}
