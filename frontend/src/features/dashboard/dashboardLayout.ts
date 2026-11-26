import type { LayoutItem } from 'react-grid-layout'

// 격자는 1칸 = 1px입니다. 위젯 크기를 시안 그대로(282x300 등) 지정하기 위함입니다.
export const GRID_WIDTH = 1708
export const GRID_GAP = 16

export type WidgetId = 'user' | 'banner' | 'search' | 'calendar' | 'schedule' | 'today' | 'work' | 'contact' | 'shortcuts' | 'composition'
export type SizeKey = 'small' | 'normal' | 'large' | 'wide'

export const WIDGET_ORDER: WidgetId[] = ['user', 'banner', 'search', 'calendar', 'schedule', 'today', 'work', 'contact', 'shortcuts', 'composition']
export const WIDGET_LABELS: Record<WidgetId, string> = {
  user: '사용자 정보', banner: '배너·공지', search: '대상자 조회', calendar: '달력', schedule: '주요 일정',
  today: '오늘 현황', work: '업무 알림', contact: '연락 알림', shortcuts: '바로가기', composition: '대상자 구성',
}
// 이동·크기변경·숨김이 모두 불가능한 위젯
export const LOCKED_WIDGETS: WidgetId[] = ['user', 'banner']

type Size = { w: number; h: number }
const NOTIFY = { w: 399, h: 247 }
const NOTIFY_SIZES = [
  { key: 'small' as const, label: '작게', w: NOTIFY.w, h: NOTIFY.h },
  { key: 'wide' as const, label: '가로 2배', w: NOTIFY.w * 2 + GRID_GAP, h: NOTIFY.h },
  { key: 'large' as const, label: '가로·세로 2배', w: NOTIFY.w * 2 + GRID_GAP, h: NOTIFY.h * 2 + GRID_GAP },
]
// 크기를 고를 수 있는 위젯과 선택지
export const SIZE_OPTIONS: Partial<Record<WidgetId, { key: SizeKey; label: string; w: number; h: number }[]>> = {
  schedule: [
    { key: 'small', label: '작게', w: 282, h: 130 },
    { key: 'normal', label: '보통', w: 282, h: 212 },
    { key: 'large', label: '크게', w: 282, h: 300 },
  ],
  work: NOTIFY_SIZES,
  contact: NOTIFY_SIZES,
}
const DEFAULT_SIZE_KEY: Partial<Record<WidgetId, SizeKey>> = { schedule: 'normal', work: 'small', contact: 'small' }
const FIXED_SIZES: Partial<Record<WidgetId, Size>> = {
  user: { w: 282, h: 300 }, banner: { w: 1112, h: 300 }, search: { w: 282, h: 300 },
  calendar: { w: 282, h: 212 }, today: { w: 282, h: 247 }, composition: { w: 282, h: 500 },
}
const DEFAULT_POSITIONS: Record<WidgetId, { x: number; y: number }> = {
  user: { x: 0, y: 0 }, banner: { x: 298, y: 0 }, search: { x: 1426, y: 0 },
  calendar: { x: 0, y: 316 }, schedule: { x: 0, y: 544 },
  today: { x: 298, y: 316 }, work: { x: 596, y: 316 }, contact: { x: 1011, y: 316 },
  shortcuts: { x: 298, y: 579 }, composition: { x: 1426, y: 316 },
}

// 바로가기: 아이콘 칸 크기는 고정, 개수에 따라 카드 크기만 바뀝니다.
const SHORTCUT_CELL = { w: 128, h: 135 }
const SHORTCUT_GAP = 8
const SHORTCUT_PADDING = 16
export const SHORTCUT_MAX_COLUMNS = 8
export function shortcutsSize(count: number): Size {
  const total = Math.max(1, count)
  const columns = Math.min(total, SHORTCUT_MAX_COLUMNS)
  const rows = Math.ceil(total / SHORTCUT_MAX_COLUMNS)
  return {
    w: SHORTCUT_PADDING * 2 + columns * SHORTCUT_CELL.w + (columns - 1) * SHORTCUT_GAP,
    h: SHORTCUT_PADDING * 2 + rows * SHORTCUT_CELL.h + (rows - 1) * SHORTCUT_GAP,
  }
}

export type DashboardConfig = {
  version: 1
  positions: Partial<Record<WidgetId, { x: number; y: number }>>
  hidden: WidgetId[]
  sizes: Partial<Record<WidgetId, SizeKey>>
  hiddenShortcuts: string[]
}
export const defaultDashboardConfig = (): DashboardConfig => ({ version: 1, positions: {}, hidden: [], sizes: {}, hiddenShortcuts: [] })

function sizeOf(id: WidgetId, config: DashboardConfig, shortcutCount: number): Size {
  if (id === 'shortcuts') return shortcutsSize(shortcutCount)
  const options = SIZE_OPTIONS[id]
  if (options) {
    const key = config.sizes[id] ?? DEFAULT_SIZE_KEY[id]
    const found = options.find(option => option.key === key) ?? options[0]
    return { w: found.w, h: found.h }
  }
  return FIXED_SIZES[id] ?? { w: 282, h: 212 }
}

const collides = (a: LayoutItem, b: LayoutItem) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y

function findFreeSpot(placed: LayoutItem[], item: LayoutItem): { x: number; y: number } {
  for (let y = 0; y < 3000; y += 8) {
    for (let x = 0; x <= GRID_WIDTH - item.w; x += 8) {
      if (!placed.some(other => collides({ ...item, x, y }, other))) return { x, y }
    }
  }
  return { x: 0, y: 3000 }
}

// 저장된 위치 + 현재 크기/표시 상태로 격자 배치를 만듭니다. 겹치면 빈 자리로 옮깁니다.
export function buildLayout(config: DashboardConfig, shortcutCount: number): LayoutItem[] {
  const items: LayoutItem[] = []
  for (const id of WIDGET_ORDER) {
    const locked = LOCKED_WIDGETS.includes(id)
    if (!locked && config.hidden.includes(id)) continue
    const { w, h } = sizeOf(id, config, shortcutCount)
    const base = (locked ? undefined : config.positions[id]) ?? DEFAULT_POSITIONS[id]
    const x = Math.max(0, Math.min(GRID_WIDTH - w, Math.round(base.x)))
    const y = Math.max(0, Math.round(base.y))
    items.push({ i: id, x, y, w, h, static: locked })
  }
  const placed = items.filter(item => item.static)
  for (const item of items) {
    if (item.static) continue
    if (placed.some(other => collides(item, other))) Object.assign(item, findFreeSpot(placed, item))
    placed.push(item)
  }
  return items
}

// 기본 배치의 열/행 정렬선. 위젯을 놓으면 이 선이나 다른 위젯의 가장자리(+간격)에 붙습니다.
const GRID_LINES_X = [0, 298, 596, 1011, 1426]
const GRID_LINES_Y = [0, 316, 544, 579]

// 놓은 위치(x, y)를 가장 가까운 정렬 위치로 맞춥니다. 겹치면 가까운 순서로 빈 정렬 자리를 찾습니다.
export function snapPosition(layout: LayoutItem[], id: string, x: number, y: number): { x: number; y: number } {
  const me = layout.find(item => item.i === id)
  if (!me) return { x, y }
  const others = layout.filter(item => item.i !== id)
  const xs = new Set<number>([...GRID_LINES_X, GRID_WIDTH - me.w])
  const ys = new Set<number>(GRID_LINES_Y)
  for (const o of others) {
    xs.add(o.x); xs.add(o.x + o.w + GRID_GAP); xs.add(o.x + o.w - me.w); xs.add(o.x - GRID_GAP - me.w)
    ys.add(o.y); ys.add(o.y + o.h + GRID_GAP); ys.add(o.y + o.h - me.h); ys.add(o.y - GRID_GAP - me.h)
  }
  const near = (values: Set<number>, target: number, max: number) =>
    [...values].filter(value => value >= 0 && value <= max).sort((a, b) => Math.abs(a - target) - Math.abs(b - target)).slice(0, 12)
  const candidatesX = near(xs, x, GRID_WIDTH - me.w)
  const candidatesY = near(ys, y, 3000)
  const pairs = candidatesX.flatMap(cx => candidatesY.map(cy => ({ x: cx, y: cy })))
    .sort((a, b) => (a.x - x) ** 2 + (a.y - y) ** 2 - ((b.x - x) ** 2 + (b.y - y) ** 2))
  const free = pairs.find(pair => !others.some(o => collides({ ...me, ...pair }, o)))
  return free ?? { x: me.x, y: me.y }
}

// ---- 저장소: 지금은 localStorage(아이디별). 백엔드 저장으로 바꿀 때 이 객체만 교체하면 됩니다. ----
export type DashboardStore = {
  load(userKey: string): DashboardConfig | null
  save(userKey: string, config: DashboardConfig): void
}
const storageKey = (userKey: string) => `project-ai-tf.dashboard-layout.${userKey}`

function sanitize(raw: unknown): DashboardConfig | null {
  if (!raw || typeof raw !== 'object') return null
  const data = raw as Partial<DashboardConfig>
  const config = defaultDashboardConfig()
  const isId = (value: unknown): value is WidgetId => WIDGET_ORDER.includes(value as WidgetId)
  if (data.positions && typeof data.positions === 'object') {
    for (const [id, pos] of Object.entries(data.positions)) {
      if (isId(id) && pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) config.positions[id] = { x: pos.x, y: pos.y }
    }
  }
  if (Array.isArray(data.hidden)) config.hidden = data.hidden.filter(isId)
  if (data.sizes && typeof data.sizes === 'object') {
    for (const [id, key] of Object.entries(data.sizes)) {
      if (isId(id) && SIZE_OPTIONS[id]?.some(option => option.key === key)) config.sizes[id] = key as SizeKey
    }
  }
  if (Array.isArray(data.hiddenShortcuts)) config.hiddenShortcuts = data.hiddenShortcuts.filter((id): id is string => typeof id === 'string')
  return config
}

export const localDashboardStore: DashboardStore = {
  load(userKey) {
    try {
      const text = window.localStorage.getItem(storageKey(userKey))
      return text ? sanitize(JSON.parse(text)) : null
    } catch { return null }
  },
  save(userKey, config) {
    try { window.localStorage.setItem(storageKey(userKey), JSON.stringify(config)) } catch { /* 저장 실패는 무시 */ }
  },
}
