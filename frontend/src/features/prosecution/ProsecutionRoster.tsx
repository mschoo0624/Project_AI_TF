import { useState } from 'react'
import { RosterHeading, RosterSummary, RosterPagination } from '../../components/PersonnelRosterParts'
import ProsecutionProfile from './ProsecutionProfile'
import { useProsecutionQuery } from './useProsecutionQuery'
import type { ProsecutionTarget, TrainingReviewTarget } from './types'

const PAGE_SIZE = 20
const targetColumns = [['군번', 16], ['성명', 14], ['연차', 9], ['분대', 9], ['고발 사유', 26], ['연속 무단불참 (참고)', 12], ['작업', 14]] as const
const reviewColumns = [['군번', 22], ['성명', 22], ['연차', 16], ['미이수 연차', 24], ['잔여시간', 16]] as const
const count = (value: number) => `${value.toLocaleString('ko-KR')}명`

export default function ProsecutionRoster({ revision, onWrite, writingDisabled }: {
  revision: number; onWrite: (personId: string) => void; writingDisabled: boolean
}) {
  const targetsQuery = useProsecutionQuery<ProsecutionTarget[]>('/reservists/prosecution-targets', revision)
  const reviewQuery = useProsecutionQuery<TrainingReviewTarget[]>('/reservists/training-review-targets', revision)
  const targets = targetsQuery.data ?? []
  const reviewTargets = reviewQuery.data ?? []
  const [selectedTarget, setSelectedTarget] = useState<ProsecutionTarget | null>(null)
  const [search, setSearch] = useState('')
  const [branch, setBranch] = useState('')
  const [filters, setFilters] = useState({ search: '', branch: '' })
  const [list, setList] = useState<'targets' | 'training'>('targets')
  const [pages, setPages] = useState({ targets: 1, training: 1 })
  const term = filters.search.trim().toLowerCase()
  const matches = (person: { name: string; military_number: string; branch: string }) =>
    (!term || `${person.name} ${person.military_number}`.toLowerCase().includes(term)) && (!filters.branch || person.branch === filters.branch)
  const filtered = targets.filter(matches)
  const filteredReview = reviewTargets.filter(matches)
  const isTargets = list === 'targets'
  const { loading, error } = isTargets ? targetsQuery : reviewQuery
  const total = isTargets ? filtered.length : filteredReview.length
  const page = Math.min(pages[list], Math.max(1, Math.ceil(total / PAGE_SIZE)))
  const offset = (page - 1) * PAGE_SIZE
  const columns = isTargets ? targetColumns : reviewColumns
  const branches = [...new Set([...targets, ...reviewTargets].map(person => person.branch))].sort()
  const title = isTargets ? '고발대상자 목록' : '훈련 미이수 검토'
  const applyFilters = (next: typeof filters) => { setFilters(next); setPages({ targets: 1, training: 1 }) }
  const targetCount = (value: number) => targetsQuery.loading || targetsQuery.error ? '—' : count(value)

  return <main className="rm-roster-layout rm-managed-roster rm-prosecution-roster" aria-busy={targetsQuery.loading || reviewQuery.loading}>
    <div className="rm-roster-main">
      <RosterHeading>고발대상자 관리</RosterHeading>
      <RosterSummary metrics={[
        { label: '고발대상자', value: targetCount(targets.length), description: '고발 요건 확인 인원', color: 'blue' },
        { label: '미이수 검토', value: reviewQuery.loading || reviewQuery.error ? '—' : count(reviewTargets.length), description: '잔여시간 확인 대상', color: 'orange' },
        { label: '분대 편성', value: targetCount(targets.filter(person => person.squad_id != null).length), description: '소속 분대가 있는 대상자', color: 'blue' },
        { label: '미편성', value: targetCount(targets.filter(person => person.squad_id == null).length), description: '소속 분대가 없는 대상자', color: 'orange' },
      ]} />
      <form className="rm-search-controls" onSubmit={event => { event.preventDefault(); applyFilters({ search, branch }) }}>
        <label className="rm-query-input"><span aria-hidden="true">⌕</span>
          <input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="이름, 군번을 입력하세요." aria-label="고발대상자 성명 또는 군번 검색" />
        </label>
        <select value={branch} onChange={event => setBranch(event.target.value)} aria-label="군별">
          <option value="">전체 군별</option>{branches.map(value => <option key={value}>{value}</option>)}
        </select>
        <button type="submit" className="rm-btn rm-btn-primary">검색</button>
        <button type="button" className="rm-btn" onClick={() => { setSearch(''); setBranch(''); applyFilters({ search: '', branch: '' }) }}>초기화</button>
      </form>
      <section className={`rm-person-list rm-prosecution-list-panel${isTargets ? '' : ' rm-prosecution-training-review'}`} aria-label={title} aria-busy={loading}>
        <nav className="rm-group-tabs" aria-label="대상자 목록 구분">
          {([['targets', '고발대상자'], ['training', '훈련 미이수 검토']] as const).map(([id, label]) =>
            <button key={id} type="button" aria-current={list === id ? 'page' : undefined} className={list === id ? 'is-active' : ''} onClick={() => setList(id)}>{label}</button>)}
        </nav>
        <div className="rm-person-list-toolbar">
          <span>{isTargets ? '대상자를 선택하면 훈련 이력을 확인할 수 있습니다.' : '잔여시간 확인 목록이며 고발대상자 판정과 별도입니다.'}</span>
          <span className="rm-list-total">총 {count(total)}</span>
        </div>
        <div className="rm-list-scroll">
          <table className="rm-person-table rm-managed-table rm-prosecution-roster-table">
            <colgroup>{columns.map(([label, width]) => <col key={label} style={{ width: `${width}%` }} />)}</colgroup>
            <thead><tr>{columns.map(([label]) => <th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{!loading && !error && (isTargets
              ? filtered.slice(offset, offset + PAGE_SIZE).map(person => <tr key={person.military_number} tabIndex={0}
                onClick={() => setSelectedTarget(person)} onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedTarget(person) }
                }}>
                <td className="mono">{person.military_number}</td><td><strong>{person.name}</strong><small>{person.branch} · {person.rank ?? '-'}</small></td>
                <td>{person.service_year == null ? '—' : `${person.service_year}년차`}</td><td>{person.squad_id == null ? '미편성' : `${person.squad_id}분대`}</td>
                <td title={person.prosecution_reason ?? undefined}><span className="rm-prosecution-badge">{person.prosecution_reason ?? '훈련 요건 충족'}</span><small>{person.target_years.map(year => `${year}년차`).join(', ')}</small></td>
                <td>{person.consecutive_unexcused_absences}회</td>
                <td className="rm-prosecution-action">
                  <button type="button" className="rm-btn rm-btn-primary rm-prosecution-write" aria-label={`${person.name} 고발서작성`} disabled={writingDisabled}
                    onClick={event => { event.stopPropagation(); onWrite(person.military_number) }}
                    onKeyDown={event => event.stopPropagation()}>고발서작성</button>
                </td>
              </tr>)
              : filteredReview.slice(offset, offset + PAGE_SIZE).map(person => <tr key={person.military_number}>
                <td className="mono">{person.military_number}</td><td><strong>{person.name}</strong><small>{person.branch} · {person.rank ?? '-'}</small></td>
                <td>{person.service_year}년차</td><td>{person.review_years.map(year => `${year}년차`).join(', ')}</td><td>{person.remaining_hours}시간</td>
              </tr>))}</tbody>
          </table>
          {loading ? <p className="rm-list-message">목록을 불러오는 중입니다…</p>
            : error ? <p role="alert" className="rm-org-error">{error}</p>
              : !total && <p className="rm-list-message">{term || filters.branch ? '검색 결과가 없습니다.' : isTargets ? '현재 고발대상자가 없습니다.' : '검토할 미이수 훈련이 없습니다.'}</p>}
        </div>
        <RosterPagination total={total} page={page} pageSize={PAGE_SIZE} onPageChange={value => setPages(current => ({ ...current, [list]: value }))} label={`${title} 페이지`} />
      </section>
    </div>
    {selectedTarget && <ProsecutionProfile key={selectedTarget.military_number} target={selectedTarget} onClose={() => setSelectedTarget(null)} />}
  </main>
}
