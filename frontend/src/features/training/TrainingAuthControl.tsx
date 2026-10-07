import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiBase, authenticatedFetch, clearAuth, readAuth, storeAuth } from './auth'
import './TrainingAuthControl.css'

type TokenResponse = {
  access_token: string
  user: { id: number; username: string; role: 'viewer' | 'scheduler' | 'approver' }
}

export function TrainingLoginPage({ checkingSession, sessionError, onRetry }: {
  checkingSession: boolean
  sessionError: string
  onRetry: () => void
}) {
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
        body: JSON.stringify({ username, password }),
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
        body: JSON.stringify({ username, password }),
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
        <span>31사단 · 내부 업무 시스템</span>
        <h1>예비군<br />업무체계</h1>
        <p>통합 자원관리와 훈련 업무를 위한<br />인증된 사용자 전용 공간입니다.</p>
        <span className="training-login-mark" aria-hidden="true">31</span>
      </section>
      <form className="training-login-form" onSubmit={event => void (showBootstrap ? createFirstApprover(event) : submitLogin(event))}>
        <div className="training-login-heading">
          <span>SECURE ACCESS</span>
          <h2>{showBootstrap ? '첫 approver 계정 만들기' : '로그인'}</h2>
          <p>{showBootstrap ? '최초 approver 계정으로 사용할 사용자명과 비밀번호를 입력하세요.' : '계정 정보를 입력해 업무체계에 접속하세요.'}</p>
        </div>
        {checkingSession && <p className="training-login-notice" role="status">로그인 상태를 확인하고 있습니다.</p>}
        {sessionError && <div className="training-login-error" role="alert"><span>{sessionError}</span><button type="button" onClick={onRetry}>다시 확인</button></div>}
        <label>사용자명<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required disabled={busy} /></label>
        <label>비밀번호<input type="password" autoComplete={showBootstrap ? 'new-password' : 'current-password'} minLength={showBootstrap ? 12 : undefined} value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /></label>
        {error && <p className="training-login-error" role="alert">{error}</p>}
        <button className="training-login-submit" type="submit" disabled={busy || checkingSession}>{busy ? '처리 중…' : showBootstrap ? 'approver 계정 만들기' : '로그인'}</button>
        <button className="training-login-switch" type="button" onClick={() => { setShowBootstrap(value => !value); setError('') }} disabled={busy}>{showBootstrap ? '로그인으로 돌아가기' : '첫 approver 계정 만들기'}</button>
        <p className="training-login-footnote">첫 계정은 localhost에서 approver로 생성됩니다. 이후에는 approver로 로그인해 상단의 계정 생성 버튼에서 사용자명, 비밀번호, 권한을 지정하세요.</p>
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
  const [newRole, setNewRole] = useState<'viewer' | 'scheduler' | 'approver'>('viewer')
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
        body: JSON.stringify({ username: newUsername, password: newPassword, role: newRole }),
      })
      const payload = await response.json() as { username?: string; detail?: unknown }
      if (!response.ok) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : '사용자 계정을 만들지 못했습니다.')
      }
      setAccountMessage(`${payload.username ?? newUsername} 계정을 만들었습니다.`)
      setNewUsername('')
      setNewPassword('')
      setNewRole('viewer')
    } catch (cause) {
      setAccountError(cause instanceof Error ? cause.message : '사용자 계정을 만들지 못했습니다.')
    } finally {
      setAccountBusy(false)
    }
  }

  return <div className="training-auth-control">
    {auth
      ? <><span className="training-auth-identity">{auth.user.username} · {auth.user.role}</span>
        {auth.user.role === 'approver' && <button type="button" aria-expanded={open} onClick={() => { setOpen(value => !value); setAccountError(''); setAccountMessage('') }}>계정 생성</button>}
        <button type="button" onClick={() => void logout()}>로그아웃</button></>
      : <button type="button" aria-expanded={open} onClick={() => { setOpen(value => !value); setError('') }}>로그인</button>}
    {open && auth?.user.role === 'approver' && <form className="training-auth-popover training-account-form" onSubmit={event => void createUser(event)}>
      <strong>사용자 계정 생성</strong>
      <label>사용자명<input autoComplete="off" value={newUsername} onChange={event => setNewUsername(event.target.value)} required disabled={accountBusy} /></label>
      <label>임시 비밀번호<input type="password" autoComplete="new-password" minLength={12} value={newPassword} onChange={event => setNewPassword(event.target.value)} required disabled={accountBusy} /></label>
      <label>권한<select value={newRole} onChange={event => setNewRole(event.target.value as typeof newRole)} disabled={accountBusy}><option value="viewer">viewer · 조회</option><option value="scheduler">scheduler · 일정/결과</option><option value="approver">approver · 승인</option></select></label>
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