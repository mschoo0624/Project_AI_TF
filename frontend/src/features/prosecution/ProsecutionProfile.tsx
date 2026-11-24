import { useProsecutionQuery } from './useProsecutionQuery'
import type { ProsecutionTarget, ProsecutionTrainingProgress, ProsecutionTrainingRecord } from './types'

export default function ProsecutionProfile({ target, onClose }: { target: ProsecutionTarget; onClose: () => void }) {
  const { data, loading, error } = useProsecutionQuery<{
    progress: ProsecutionTrainingProgress[]; records: ProsecutionTrainingRecord[]
  }>(`/reservists/${encodeURIComponent(target.military_number)}/training-hours`)
  const progress = data?.progress ?? []
  const records = data?.records ?? []

  return <div className="rm-prosecution-profile" role="dialog" aria-modal="true" aria-label={`${target.name} 훈련 이력`}>
    <header>
      <div><p>PROSECUTION PROFILE</p><h2>{target.name}</h2><span>{target.military_number} · {target.service_year ?? '-'}년차 · {target.branch} · {target.rank ?? '-'}</span></div>
      <button type="button" onClick={onClose} aria-label="프로필 닫기">×</button>
    </header>
    <div className="rm-prosecution-profile-body">
      <div className="rm-prosecution-profile-reason"><strong>고발 사유</strong><span>{target.prosecution_reason ?? '훈련 미이수'}</span></div>
      {loading ? <p className="rm-list-message">훈련 정보를 불러오는 중입니다.</p>
        : error ? <p className="rm-list-message rm-error" role="alert">{error}</p> : <>
          <h3>연차별 훈련 현황</h3>
          <div className="rm-prosecution-progress">{progress.filter(item => item.service_year > 0).map(item =>
            <div className={item.prosecution_risk ? 'is-risk' : ''} key={item.service_year}>
              <span>{item.service_year}년차</span><small>{item.training_plan.map(plan => plan.name).join(', ') || '훈련 대상 아님'}</small>
              <b>{item.completed_hours}/{item.required_hours}시간 · {item.training_status}</b>
            </div>)}
          </div>
          <h3>훈련 기록</h3>
          {!records.length ? <p className="rm-list-message">등록된 훈련 기록이 없습니다.</p> :
            <div className="rm-prosecution-history"><table>
              <thead><tr>{['연차', '훈련연도', '종류', '차수', '출결', '시간'].map(label => <th key={label}>{label}</th>)}</tr></thead>
              <tbody>{records.map(record => <tr key={record.id}>
                <td>{record.education_year}년차</td><td>{record.training_year ?? '-'}</td><td>{record.training_type}</td>
                <td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.training_hours}시간</td>
              </tr>)}</tbody>
            </table></div>}
        </>}
    </div>
  </div>
}
