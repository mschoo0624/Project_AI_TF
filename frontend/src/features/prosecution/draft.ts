import { documentTime } from './api'
import type { DraftFields, DraftSources, Training } from './types'

export type Field = [key: string, label: string]

export const fieldGroups: { title: string; fields: Field[] }[] = [
  { title: '문서 정보', fields: [['number', '문서번호'], ['date', '작성일'], ['police', '수신 경찰서']] },
  { title: '1. 고발인', fields: [['commander', '대표자·부대장'], ['complainant_address', '주소'], ['office_phone', '사무실 전화'], ['mobile_phone', '휴대폰']] },
  { title: '2. 피고발인', fields: [['name', '성명'], ['birth_digits', '주민번호 앞자리'], ['address', '현거주지'], ['phone', '휴대폰'], ['home_phone', '자택 전화'], ['work_phone', '사무실 전화'], ['reserve_unit', '예비군 소속부대'], ['rank', '예비역 계급'], ['military_number', '군번']] },
  { title: '4. 범죄사실', fields: [['offense', '범죄명'], ['law', '적용법조'], ['period', '훈련기간'], ['location', '훈련장소'], ['delivered_at', '소집통지서 전달일시'], ['deliverer', '전달자'], ['recipient', '수령자']] },
]

export const textFields: Field[] = [['summary', '범죄사실요약'], ['reason', '5. 고발이유'], ['evidence', '6. 증거자료']]
const linkedFields = new Set(['name', 'rank', 'reserve_unit', 'military_number', 'period', 'summary'])

export function createBlankDraft(): DraftFields {
  const fields = [...fieldGroups.flatMap(group => group.fields), ...textFields, ['repeat', '']]
  return Object.fromEntries(fields.map(([key]) => [key, '']))
}

export function fieldMaxLength(key: string) {
  if (textFields.some(([name]) => name === key)) return 6000
  return key === 'period' || key === 'reserve_unit' ? 1500 : 200
}

export function isLinkedField(key: string, sources: DraftSources | null, saved: boolean) {
  if (key === 'military_number') return true
  const values: DraftFields = sources?.person ?? {}
  return !saved && linkedFields.has(key) && (key === 'period' || key === 'summary' || Boolean(values[key]))
}

export const formatTraining = (record: Training) =>
  `${record.dates.join(', ') || '훈련일 미확인'} / ${record.training_type} ${record.training_round}차 / ${record.service_year}년차`

function trainingFacts(records: Training[]) {
  return records.map(record => [
    formatTraining(record),
    record.schedule_title ? `일정명: ${record.schedule_title}` : '',
    record.training_year != null ? `훈련연도: ${record.training_year}년` : '',
    `출결: ${record.attendance_status}`,
    record.completed_hours != null ? `이수시간: ${record.completed_hours}시간` : '',
    record.scheduled_hours != null ? `일정 인정시간 상한: ${record.scheduled_hours}시간` : '',
    `확정자: ${record.confirmed_by}`,
    record.confirmed_at ? `확정일시: ${documentTime(record.confirmed_at)}` : '',
  ].filter(Boolean).join(' / ')).join('\n')
}

export function applySources(current: DraftFields, sources: DraftSources, records: Training[], now = new Date()): DraftFields {
  const dates = [...new Set(records.flatMap(record => record.dates))].sort()
  return {
    ...current,
    ...sources.person,
    rank: sources.person.rank || current.rank,
    reserve_unit: sources.person.reserve_unit || current.reserve_unit,
    period: dates.join(', '),
    summary: trainingFacts(records),
    date: current.date || `${now.getFullYear()}년 ${now.getMonth() + 1}월 ${now.getDate()}일`,
    offense: current.offense || '예비군 훈련 불참',
    law: current.law || '예비군법 제15조 (세부 적용 조항 확인 필요)',
    reason: current.reason || `${sources.person.name}의 선택한 훈련에서 무단불참으로 확정된 기록을 근거로 고발을 검토합니다.\n소집통지서 전달 및 불참 사유 등 제출 근거를 확인하여 내용을 보완하십시오.`,
  }
}

export function draftSizeError(form: DraftFields, records: Training[]) {
  return records.length > 100 || form.period.length > fieldMaxLength('period') || form.summary.length > fieldMaxLength('summary')
    ? '선택한 훈련의 내용이 한 고발장의 저장 한도를 넘었습니다. 포함할 훈련을 줄여서 나누어 작성하세요.' : ''
}

export const fieldsEqual = (current: DraftFields, saved: DraftFields) =>
  Object.keys(current).every(key => current[key] === (saved[key] ?? ''))

const snapshotKey = (records: Training[]) => JSON.stringify([...records].sort((a, b) => a.id - b.id)
  .map(record => Object.fromEntries(Object.entries(record).sort(([a], [b]) => a.localeCompare(b)))))

export const sameTraining = (left: Training[], right: Training[]) => snapshotKey(left) === snapshotKey(right)
