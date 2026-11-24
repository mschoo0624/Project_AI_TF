import { useEffect, useState } from 'react'
import { AUTO_LOGOUT_ENABLED, AUTO_LOGOUT_MS, getLastActivity, readAuth } from '../training/auth'
import { dongdaesOfAudit, unitName } from './orgData'
import { DEFAULT_SECURITY_INFO, EMPTY_PROFILE_EXTRA, PROFILE_EXTRA, SECURITY_INFO, WORK_STATUS } from './mypageData'
import './myPage.css'

const DAY_MS = 24 * 60 * 60 * 1000
const parseDate = (value: string) => { const [y, m, d] = value.split('-').map(Number); return new Date(y, m - 1, d) }
const formatDate = (value: string) => value.replace(/-/g, '.')

// 복무 진행률/D-day. 오늘 날짜 기준으로 계산합니다.
function servicePeriod(enlistDate: string, dischargeDate: string, now: Date) {
  const start = parseDate(enlistDate).getTime()
  const end = parseDate(dischargeDate).getTime()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const percent = Math.max(0, Math.min(100, Math.floor((today - start) / (end - start) * 100)))
  return { dday: Math.max(0, Math.ceil((end - today) / DAY_MS)), percent }
}

function AutoLogoutRemaining() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!AUTO_LOGOUT_ENABLED) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  if (!AUTO_LOGOUT_ENABLED) return <>꺼짐(개발 모드)</>
  const seconds = Math.max(0, Math.floor((AUTO_LOGOUT_MS - (now - getLastActivity())) / 1000))
  const pad = (value: number) => String(value).padStart(2, '0')
  return <>{pad(Math.floor(seconds / 3600))}:{pad(Math.floor(seconds % 3600 / 60))}:{pad(seconds % 60)}</>
}

export default function MyPage({ onCustomize, onLogout, onGoWorklog }: {
  onCustomize: () => void
  onLogout: () => void
  onGoWorklog: () => void
}) {
  const user = readAuth()?.user
  if (!user) return null
  const extra = PROFILE_EXTRA[user.username] ?? EMPTY_PROFILE_EXTRA
  const security = SECURITY_INFO[user.username] ?? DEFAULT_SECURITY_INFO
  const position = user.position || (user.role === 'approver' ? '동대장' : user.role === 'scheduler' ? '상근예비역' : '감사실')
  const work = WORK_STATUS[position]
  const name = extra.name ?? user.username
  const unit = unitName(user.unit_code)
  const period = position === '상근예비역' && extra.enlistDate && extra.dischargeDate
    ? servicePeriod(extra.enlistDate, extra.dischargeDate, new Date()) : null
  const dongdaes = position === '감사실' ? dongdaesOfAudit(user.unit_code) : []

  return <section className="mypage mp" aria-label="마이페이지">
    <header className="mp-header">
      <div>
        <h1>마이페이지</h1>
        <p>{work.description}</p>
      </div>
      <div className="mp-actions">
        <button type="button" className="mp-button is-primary" onClick={onCustomize}>대시보드 커스텀</button>
        <button type="button" className="mp-button" onClick={onLogout}>로그아웃</button>
      </div>
    </header>

    <section className="mp-card mp-profile" aria-labelledby="mp-profile-title">
      <div className="mp-profile-top">
        <div className="mp-avatar" aria-hidden="true">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.2 3.6-7 8-7s8 2.8 8 7" /></svg>
        </div>
        <div className="mp-profile-name">
          <h2 id="mp-profile-title"><span>{extra.rank !== '-' ? `${extra.rank} ` : ''}{name}</span><em className="mp-badge">{position}</em></h2>
          <span>{unit}</span>
        </div>
        {/* 연락처 수정·비밀번호 변경은 DB(연락처 컬럼)·계정 데이터 변경이 필요해 아직 연결하지 않았습니다. */}
        <div className="mp-actions">
          <button type="button" className="mp-button" disabled title="준비 중입니다 (연락처 저장 DB 필요)">연락처 수정</button>
          <button type="button" className="mp-button" disabled title="준비 중입니다">비밀번호 변경</button>
        </div>
      </div>
      <dl className="mp-info">
        <div><dt>계급</dt><dd>{extra.rank}</dd></div>
        <div><dt>이름</dt><dd>{name}</dd></div>
        <div><dt>군번</dt><dd>{user.service_number || '-'}</dd></div>
        <div><dt>권한</dt><dd>{position}</dd></div>
        <div><dt>소속부대</dt><dd>{unit}</dd></div>
        <div><dt>연락처</dt><dd>{extra.phone}</dd></div>
      </dl>
    </section>

    {period && extra.enlistDate && extra.dischargeDate && <section className="mp-card" aria-labelledby="mp-service-title">
      <div className="mp-card-head">
        <h2 id="mp-service-title">복무 기간</h2>
        <strong className="mp-dday">전역까지 D-{period.dday}</strong>
      </div>
      <div className="mp-tiles is-wide">
        <div className="mp-tile"><span>입대일자</span><strong>{formatDate(extra.enlistDate)}</strong></div>
        <div className="mp-tile"><span>전역일자</span><strong>{formatDate(extra.dischargeDate)}</strong></div>
      </div>
      <div className="mp-progress">
        <div><span>복무 진행률</span><strong>{period.percent}%</strong></div>
        <div className="mp-progress-bar" role="img" aria-label={`복무 진행률 ${period.percent}퍼센트`}><i style={{ width: `${period.percent}%` }} /></div>
      </div>
    </section>}

    {position === '감사실' && <section className="mp-card" aria-labelledby="mp-dong-title">
      <div className="mp-card-head is-column">
        <h2 id="mp-dong-title">담당 동대</h2>
        <span>감사실에 지정된 동대 목록입니다.</span>
      </div>
      <div className="mp-table-wrap">
        <table className="mp-table">
          <thead><tr><th scope="col">동대</th><th scope="col">동대장</th><th scope="col">상근예비역</th><th scope="col">최근 업무일지</th></tr></thead>
          <tbody>
            {dongdaes.map(unit => <tr key={unit.code}>
              <td>{unit.info?.shortName ?? unit.name}</td>
              <td>{unit.info?.commander ?? '-'}</td>
              <td>{unit.info ? `${unit.info.reservistCount}명` : '-'}</td>
              <td className={unit.info?.overdueDays ? 'is-warn' : undefined}>{unit.info ? `${unit.info.lastLogDate}${unit.info.overdueDays ? ` (미제출 ${unit.info.overdueDays}일)` : ''}` : '-'}</td>
            </tr>)}
            {dongdaes.length === 0 && <tr><td colSpan={4} className="mp-empty">담당 동대가 없습니다.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>}

    <section className="mp-card" aria-labelledby="mp-work-title">
      <div className="mp-card-head">
        <h2 id="mp-work-title">{work.sectionTitle}</h2>
        <button type="button" className="mp-link" onClick={onGoWorklog}>업무일지로 이동</button>
      </div>
      <div className="mp-tiles">
        {work.summary.map(item => <div className="mp-tile" key={item.label}>
          <span>{item.label}</span>
          <strong className={item.tone ? `is-${item.tone}` : undefined}>{item.value}<small> 건</small></strong>
        </div>)}
      </div>
      <div className="mp-table-wrap">
        <table className="mp-table">
          <thead><tr><th scope="col">업무</th><th scope="col">구분</th><th scope="col">기한</th><th scope="col">상태</th></tr></thead>
          <tbody>
            {work.rows.map(row => <tr key={row.task}>
              <td>{row.task}</td><td>{row.category}</td><td>{row.due}</td><td className={`is-${row.tone}`}>{row.status}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>

    <section className="mp-security" aria-label="계정 보안">
      <div className="mp-card"><span>최근 접속</span><strong>{security.lastLogin}</strong></div>
      <div className="mp-card"><span>자동 로그아웃까지</span><strong><AutoLogoutRemaining /></strong></div>
      <div className="mp-card"><span>비밀번호 변경일</span><strong>{security.passwordChangedAt}</strong></div>
    </section>
  </section>
}
