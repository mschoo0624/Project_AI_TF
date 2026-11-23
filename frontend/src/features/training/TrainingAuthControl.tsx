import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiBase, authenticatedFetch, clearAuth, readAuth, storeAuth } from './auth'
import type { AuthUser } from './auth'
import ministryLogo from '../../assets/국방부 마크_컬러본.png'
import './TrainingAuthControl.css'

type TokenResponse = {
  access_token: string
  user: AuthUser
}

export function TrainingLoginPage({ checkingSession, sessionError, onRetry }: {
  checkingSession: boolean
  sessionError: string
  onRetry: () => void
}) {
  const [unitCode, setUnitCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showBootstrap, setShowBootstrap] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${apiBase()}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ unit_code: unitCode, username, password }),
      })
      const payload = await response.json() as TokenResponse | { detail?: string }
      if (!response.ok || !('access_token' in payload)) {
        throw new Error('detail' in payload ? payload.detail ?? '로그인에 실패했습니다.' : '로그인에 실패했습니다.')
      }
      storeAuth({ token: payload.access_token, user: payload.user })
      setPassword('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '로그인에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const createFirstApprover = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${apiBase()}/auth/bootstrap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ unit_code: unitCode, username, password }),
      })
      const payload = await response.json() as TokenResponse | { detail?: string }
      if (!response.ok || !('access_token' in payload)) {
        throw new Error('detail' in payload ? payload.detail ?? '계정을 만들지 못했습니다.' : '계정을 만들지 못했습니다.')
      }
      storeAuth({ token: payload.access_token, user: payload.user })
      setPassword('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '계정을 만들지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="training-login-page">
    <div className="training-login-panel">
      <section className="training-login-brand">
        <span>대한민국 국방부 · 내부 업무 시스템</span>
        <img className="training-login-logo" src={ministryLogo} alt="대한민국 국방부" />
        <h1>국방동원<br />정보체계 2.0</h1>
        <small>DEFENSE MOBILIZATION INFORMATION SYSTEM</small>
        <p>예비군 자원관리와 교육훈련 업무를 위한<br />인증된 사용자 전용 공간입니다.</p>
        <span className="training-login-mark" aria-hidden="true">2.0</span>
      </section>
      <form className="training-login-form" onSubmit={event => void (showBootstrap ? createFirstApprover(event) : submitLogin(event))}>
        <div className="training-login-heading">
          <span>SECURE ACCESS</span>
          <h2>{showBootstrap ? '첫 동대장 계정 만들기' : '로그인'}</h2>
          <p>{showBootstrap ? '최초 동대장 계정으로 사용할 부대코드, 아이디, 비밀번호를 입력하세요.' : '부대코드와 계정 정보를 입력해 접속하세요.'}</p>
        </div>
        {checkingSession && <p className="training-login-notice" role="status">로그인 상태를 확인하고 있습니다.</p>}
        {sessionError && <div className="training-login-error" role="alert"><span>{sessionError}</span><button type="button" onClick={onRetry}>다시 확인</button></div>}
        <label>부대코드<input autoComplete="organization" value={unitCode} onChange={event => setUnitCode(event.target.value)} required disabled={busy} /></label>
        <label>아이디<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required disabled={busy} /></label>
        <label>비밀번호<input type="password" autoComplete={showBootstrap ? 'new-password' : 'current-password'} minLength={showBootstrap ? 12 : undefined} value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /></label>
        {error && <p className="training-login-error" role="alert">{error}</p>}
        <button className="training-login-submit" type="submit" disabled={busy || checkingSession}>{busy ? '처리 중…' : showBootstrap ? '동대장 계정 만들기' : '로그인'}</button>
        <button className="training-login-switch" type="button" onClick={() => { setShowBootstrap(value => !value); setError('') }} disabled={busy}>{showBootstrap ? '로그인으로 돌아가기' : '첫 동대장 계정 만들기'}</button>
        <p className="training-login-footnote">첫 계정은 서버 PC(localhost)에서만 동대장으로 생성됩니다. 이후 계정은 동대장이 로그인해 상단의 계정 생성 버튼에서 만듭니다.</p>
      </form>
    </div>
  </main>
}

export default function TrainingAuthControl() {
  const [auth, setAuth] = useState(readAuth)
  const [open, setOpen] = useState(false)
  const [showBootstrap, setShowBootstrap] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPosition, setNewPosition] = useState<AuthUser['position']>('상근예비역')
  const [newUnitCode, setNewUnitCode] = useState('')
  const [accountError, setAccountError] = useState('')
  const [accountMessage, setAccountMessage] = useState('')
  const [accountBusy, setAccountBusy] = useState(false)

  useEffect(() => {
    const refresh = () => setAuth(readAuth())
    window.addEventListener('training-auth-change', refresh)
    return () => window.removeEventListener('training-auth-change', refresh)
  }, [])

  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${apiBase()}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const payload = await response.json() as TokenResponse | { detail?: string }
      if (!response.ok || !('access_token' in payload)) {
        throw new Error('detail' in payload ? payload.detail ?? '로그인에 실패했습니다.' : '로그인에 실패했습니다.')
      }
      storeAuth({ token: payload.access_token, user: payload.user })
      setPassword('')
      setOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '로그인에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const createFirstApprover = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${apiBase()}/auth/bootstrap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const payload = await response.json() as TokenResponse | { detail?: string }
      if (!response.ok || !('access_token' in payload)) {
        throw new Error('detail' in payload ? payload.detail ?? '계정을 만들지 못했습니다.' : '계정을 만들지 못했습니다.')
      }
      storeAuth({ token: payload.access_token, user: payload.user })
      setPassword('')
      setShowBootstrap(false)
      setOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '계정을 만들지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const logout = async () => {
    try { await authenticatedFetch(`${apiBase()}/auth/logout`, { method: 'POST' }) }
    finally { clearAuth(); setOpen(false) }
  }

  const createUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAccountBusy(true)
    setAccountError('')
    setAccountMessage('')
    try {
      const response = await authenticatedFetch(`${apiBase()}/auth/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          unit_code: auth?.user.position === '동대장' ? auth.user.unit_code : newUnitCode,
          username: newUsername, password: newPassword, position: newPosition,
        }),
      })
      const payload = await response.json() as { username?: string; detail?: unknown }
      if (!response.ok) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : '사용자 계정을 만들지 못했습니다.')
      }
      setAccountMessage(`${payload.username ?? newUsername} 계정을 만들었습니다.`)
      setNewUsername('')
      setNewPassword('')
      setNewPosition('상근예비역')
      setNewUnitCode('')
    } catch (cause) {
      setAccountError(cause instanceof Error ? cause.message : '사용자 계정을 만들지 못했습니다.')
    } finally {
      setAccountBusy(false)
    }
  }

  return <div className="training-auth-control">
    {auth
     ? <><span className="training-auth-identity">[{auth.user.unit_code}] {auth.user.username} · {auth.user.position}</span>
        {auth.user.role === 'approver' && <button type="button" aria-expanded={open} onClick={() => { setOpen(value => !value); setAccountError(''); setAccountMessage('') }}>계정 생성</button>}
        <button type="button" onClick={() => void logout()}>로그아웃</button></>
      : <button type="button" aria-expanded={open} onClick={() => { setOpen(value => !value); setError('') }}>로그인</button>}
    {open && auth?.user.role === 'approver' && <form className="training-auth-popover training-account-form" onSubmit={event => void createUser(event)}>
      <strong>사용자 계정 생성</strong>
      <label>부대코드<input autoComplete="off"
        value={auth.user.position === '동대장' ? auth.user.unit_code : newUnitCode}
        onChange={event => setNewUnitCode(event.target.value)}
        readOnly={auth.user.position === '동대장'} required disabled={accountBusy} /></label>
      <label>아이디<input autoComplete="off" value={newUsername} onChange={event => setNewUsername(event.target.value)} required disabled={accountBusy} /></label>
      <label>임시 비밀번호<input type="password" autoComplete="new-password" minLength={12} value={newPassword} onChange={event => setNewPassword(event.target.value)} required disabled={accountBusy} /></label>
      <label>구분<select value={newPosition} onChange={event => setNewPosition(event.target.value as AuthUser['position'])} disabled={accountBusy}>
        <option value="상근예비역">상근예비역</option>
        <option value="동대장">동대장</option>
        <option value="감사실">감사실</option>
      </select></label>
      {accountError && <p role="alert">{accountError}</p>}
      {accountMessage && <p className="training-account-success" role="status">{accountMessage}</p>}
      <button type="submit" disabled={accountBusy}>{accountBusy ? '생성 중…' : '계정 만들기'}</button>
    </form>}
    {open && !auth && <form className="training-auth-popover" onSubmit={event => void (showBootstrap ? createFirstApprover(event) : login(event))}>
      <label>사용자명<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required /></label>
      <label>비밀번호<input type="password" autoComplete={showBootstrap ? 'new-password' : 'current-password'} minLength={showBootstrap ? 12 : undefined} value={password} onChange={event => setPassword(event.target.value)} required /></label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? '처리 중…' : showBootstrap ? 'approver 계정 만들기' : '로그인'}</button>
      <button className="training-auth-switch" type="button" onClick={() => { setShowBootstrap(value => !value); setError('') }} disabled={busy}>{showBootstrap ? '로그인으로 돌아가기' : '첫 approver 계정 만들기'}</button>
    </form>}
  </div>
}