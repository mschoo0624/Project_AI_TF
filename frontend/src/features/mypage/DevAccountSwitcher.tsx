// TODO(배포 전 삭제): 개발용 계정 전환 드롭다운. 이 파일, DevAccountSwitcher.css, devAccounts.ts,
// auth.ts의 DEV_USER 관련 코드, App.tsx의 <DevAccountSwitcher />를 함께 지우면 됩니다.
// 개발 모드(import.meta.env.DEV)에서만 보이며, 백엔드를 호출하지 않고 화면에서 보이는 사용자 정보만 바꿉니다.
// (실제 로그인 토큰은 그대로라 다른 화면의 데이터 조회는 로그인한 실제 계정 권한으로 동작합니다.)
import { useEffect, useState } from 'react'
import { readDevUser, setDevUser } from '../training/auth'
import { DEV_ACCOUNTS } from './devAccounts'
import './DevAccountSwitcher.css'

export default function DevAccountSwitcher() {
  const [current, setCurrent] = useState(() => readDevUser()?.username ?? '')
  useEffect(() => {
    const refresh = () => setCurrent(readDevUser()?.username ?? '')
    window.addEventListener('training-auth-change', refresh)
    return () => window.removeEventListener('training-auth-change', refresh)
  }, [])
  if (!import.meta.env.DEV) return null
  return <label className="dev-switcher" title="개발용 임시 기능: 화면의 사용자 정보만 바뀝니다">
    <span>DEV 계정</span>
    <select value={current} onChange={event => setDevUser(DEV_ACCOUNTS.find(account => account.username === event.target.value) ?? null)}>
      <option value="">실제 로그인 계정</option>
      {DEV_ACCOUNTS.map(account => <option key={account.username} value={account.username}>{account.username} · {account.position}</option>)}
    </select>
  </label>
}
