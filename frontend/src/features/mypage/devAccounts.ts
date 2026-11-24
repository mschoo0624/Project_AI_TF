// TODO(배포 전 삭제): 개발용 가짜 사용자. 개발 모드(import.meta.env.DEV)에서만 쓰며 DB에는 존재하지 않습니다.
// 이름·계급·날짜는 임시 샘플이고, 계급 등 추가 정보는 mypageData.ts의 PROFILE_EXTRA(아이디 키)에 있습니다.
import type { AuthUser } from '../training/auth'

export const DEV_ACCOUNTS: AuthUser[] = [
  { id: -1, username: '김민준', role: 'approver', unit_code: '310101', position: '동대장', service_number: '00-00000000' },
  { id: -2, username: '이서준', role: 'viewer', unit_code: '3101', position: '감사실', service_number: '00-00000000' },
  { id: -3, username: '홍길동', role: 'scheduler', unit_code: '310101', position: '상근예비역', service_number: '00-00000000' },
]
