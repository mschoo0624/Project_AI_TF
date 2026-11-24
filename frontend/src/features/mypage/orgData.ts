// 소속 매핑 (임시 데이터). 부대코드는 "소속"만 뜻하고 권한과는 무관합니다.
// TODO(DB 연동): 실제 부대/동대 테이블이 생기면 이 파일의 UNITS, DONGDAE_INFO를 API 조회로 교체합니다.

export type UnitKind = 'audit' | 'dongdae'
export type UnitInfo = {
  code: string
  /** 화면에 표시하는 소속 이름 */
  name: string
  kind: UnitKind
  /** 동대일 때 상위 감사실 코드 */
  parentCode?: string
}

export const UNITS: UnitInfo[] = [
  { code: '3101', name: '31사단 예비군 감사실', kind: 'audit' },
  // 동대 코드는 임시 값입니다.
  { code: '310101', name: '31사단 503보병여단 삼각동대', kind: 'dongdae', parentCode: '3101' },
  { code: '310102', name: '31사단 503보병여단 한강동대', kind: 'dongdae', parentCode: '3101' },
  { code: '310103', name: '31사단 503보병여단 송정동대', kind: 'dongdae', parentCode: '3101' },
]

/** 동대 목록 표에 쓰는 임시 요약 정보 (동대 코드 기준) */
export type DongdaeInfo = {
  shortName: string
  commander: string
  reservistCount: number
  lastLogDate: string
  /** 업무일지 미제출 일수. 0이면 정상 */
  overdueDays: number
}
export const DONGDAE_INFO: Record<string, DongdaeInfo> = {
  '310101': { shortName: '삼각동대', commander: '대위 김민준', reservistCount: 3, lastLogDate: '2026.11.24', overdueDays: 0 },
  '310102': { shortName: '한강동대', commander: '소령 박지훈', reservistCount: 4, lastLogDate: '2026.11.23', overdueDays: 0 },
  '310103': { shortName: '송정동대', commander: '대위 최수아', reservistCount: 3, lastLogDate: '2026.11.19', overdueDays: 3 },
}

/** 부대코드 → 소속 이름. 매핑이 없으면 코드를 그대로 돌려줍니다. */
export function unitName(code: string | undefined): string {
  if (!code) return '-'
  return UNITS.find(unit => unit.code === code)?.name ?? code
}

/** 감사실이 담당하는 동대 목록 (동대 → 상위 감사실 관계에서 조회) */
export function dongdaesOfAudit(auditCode: string): (UnitInfo & { info?: DongdaeInfo })[] {
  return UNITS.filter(unit => unit.kind === 'dongdae' && unit.parentCode === auditCode)
    .map(unit => ({ ...unit, info: DONGDAE_INFO[unit.code] }))
}
