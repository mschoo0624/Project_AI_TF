// 마이페이지 임시 데이터. DB에 없는 값(계급·연락처·입대/전역일·업무 현황·보안 정보)을 한 곳에 모았습니다.
// 이름·계급·날짜·건수는 모두 임시 샘플입니다.
// TODO(DB 연동): 아래 값이 DB/API로 옮겨지면 이 파일을 삭제하고 MyPage.tsx의 조회부만 교체합니다.
//   필요한 변경(참고, 이번 작업에서는 하지 않음):
//   - app_user: 계급(rank), 연락처(phone), 입대일자(enlist_date), 전역일자(discharge_date), 비밀번호 변경일(password_changed_at)
//   - 최근 접속 시각: auth_session 또는 app_user에 last_login_at (/auth/me 응답 확장)
//   - 개인업무현황: 업무/결재/점검 항목 테이블 또는 기존 업무일지·검토함에서 집계하는 API
//   - 이름(실명): app_user에 name 컬럼 (현재는 아이디를 이름으로 표시)
import type { AuthUser } from '../training/auth'

export type Position = AuthUser['position']

export type ProfileExtra = {
  /** 실명. 없으면 아이디를 이름으로 씁니다. */
  name?: string
  rank: string
  phone: string
  /** YYYY-MM-DD (상근예비역만) */
  enlistDate?: string
  dischargeDate?: string
}

/** 계정 아이디 → 추가 정보 */
export const PROFILE_EXTRA: Record<string, ProfileExtra> = {
  김민준: { rank: '대위', phone: '010-0000-0000' },
  이서준: { rank: '중령', phone: '010-0000-0000' },
  홍길동: { rank: '상병', phone: '010-0000-0000', enlistDate: '2025-06-10', dischargeDate: '2027-03-09' },
  // 개발용 DB 시드 계정(아이디 1234)용 샘플
  '1234': { rank: '대위', phone: '010-0000-0000' },
}
export const EMPTY_PROFILE_EXTRA: ProfileExtra = { rank: '-', phone: '-' }

export type SecurityInfo = { lastLogin: string; passwordChangedAt: string }
export const SECURITY_INFO: Record<string, SecurityInfo> = {}
export const DEFAULT_SECURITY_INFO: SecurityInfo = { lastLogin: '2026.11.24 08:51', passwordChangedAt: '2026.09.02' }

export type StatusTone = 'warn' | 'info' | 'muted'
export type WorkStatus = {
  description: string
  sectionTitle: string
  summary: { label: string; value: number; tone?: 'warn' | 'good' }[]
  rows: { task: string; category: string; due: string; status: string; tone: StatusTone }[]
}

/** 권한(직책)별 개인업무현황 더미 */
export const WORK_STATUS: Record<Position, WorkStatus> = {
  상근예비역: {
    description: '내 인적 사항과 복무 기간, 오늘 처리할 업무를 확인합니다.',
    sectionTitle: '개인업무현황',
    summary: [
      { label: '진행 중', value: 5 },
      { label: '오늘 마감', value: 2, tone: 'warn' },
      { label: '검토 요청', value: 3 },
      { label: '이번 달 완료', value: 18, tone: 'good' },
    ],
    rows: [
      { task: '대상자 조회 및 명부 정리', category: '대상자 관리', due: '오늘', status: '오늘 마감', tone: 'warn' },
      { task: '출국자/귀국자 확인', category: '대상자 관리', due: '오늘', status: '오늘 마감', tone: 'warn' },
      { task: '훈련 결과 입력', category: '교육훈련', due: '11.27', status: '진행 중', tone: 'info' },
      { task: '업무일지 작성', category: '업무일지', due: '11.28', status: '작성 전', tone: 'muted' },
    ],
  },
  동대장: {
    description: '내 인적 사항과 동대 승인·결재 업무 현황을 확인합니다.',
    sectionTitle: '개인업무현황',
    summary: [
      { label: '결재 대기', value: 4 },
      { label: '오늘 마감', value: 1, tone: 'warn' },
      { label: '검토 대기', value: 3 },
      { label: '이번 달 처리', value: 26, tone: 'good' },
    ],
    rows: [
      { task: '보류/연기자 검토 승인', category: '검토함', due: '오늘', status: '오늘 마감', tone: 'warn' },
      { task: '상근예비역 업무일지 결재', category: '업무일지', due: '11.25', status: '결재 대기', tone: 'info' },
      { task: '훈련 부과 승인', category: '교육훈련', due: '11.28', status: '결재 대기', tone: 'info' },
      { task: '고발대상자 확인', category: '대상자 관리', due: '11.30', status: '검토 대기', tone: 'muted' },
    ],
  },
  감사실: {
    description: '내 인적 사항과 담당 동대, 감사 업무 현황을 확인합니다.',
    sectionTitle: '감사 업무 현황',
    summary: [
      { label: '점검 중', value: 6 },
      { label: '오늘 마감', value: 1, tone: 'warn' },
      { label: '시정 요청', value: 2 },
      { label: '이번 달 완료', value: 11, tone: 'good' },
    ],
    rows: [
      { task: '동대 업무일지 점검', category: '업무일지', due: '오늘', status: '오늘 마감', tone: 'warn' },
      { task: '고발대상자 처리 검토', category: '대상자 관리', due: '11.26', status: '점검 중', tone: 'info' },
      { task: '훈련 결과 감사', category: '교육훈련', due: '11.30', status: '점검 중', tone: 'info' },
      { task: '송정동대 시정 요청 확인', category: '업무일지', due: '12.02', status: '시정 요청', tone: 'muted' },
    ],
  },
}
