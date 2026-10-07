export type ResourceTabId = 'roster' | 'organization' | 'hold' | 'travel' | 'prosecution'

export const resourceTabs: { id: ResourceTabId; label: string }[] = [
  { id: 'roster', label: '편성인원목록' },
  { id: 'organization', label: '전투편성기구도' },
  { id: 'hold', label: '보류자/연기자' },
  { id: 'travel', label: '출국자/귀국자' },
  { id: 'prosecution', label: '고발대상자' },
]
