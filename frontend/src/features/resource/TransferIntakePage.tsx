import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const branches = ['육군', '해군', '공군', '해병대']
const ranks = ['이병', '일병', '상병', '병장', '하사', '중사', '상사', '소위', '중위', '대위']
const mobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '일부보류', '해당없음']
const trainingTypes = ['기본훈련', '동원훈련Ⅰ형', '동원훈련Ⅱ형', '작계훈련(전·후반기)']

type TrainingRecord = {
  service_year: number
  training_year: number
  training_type: string
  training_round: number
  training_hours: number
  notes: string
}

type TransferForm = {
  military_number: string
  name: string
  branch: string
  rank: string
  unit: string
  specialty: string
  origin_type: string
  service_year: number
  position: string
  mobilization_status: string
  status: string
  training_records: TrainingRecord[]
}

type TransferItem = {
  id: number
  military_number: string
  person_details: Omit<TransferForm, 'training_records'>
  training_records: TrainingRecord[]
  status: 'pending' | 'confirmed' | 'rejected'
  assigned_squad_id: number | null
  submitted_at: string
  reviewed_at: string | null
}

type TransferStatus = TransferItem['status']

const emptyForm = (): TransferForm => ({
  military_number: '', name: '', branch: '육군', rank: '병장', unit: '', specialty: '',
  origin_type: '병사', service_year: 1, position: '소총수', mobilization_status: '동원미지정',
  status: 'active', training_records: [],
})

const sampleTransfers: TransferForm[] = [
  {
    military_number: 'TEST-TR-001', name: '샘플 전입 김훈련', branch: '육군', rank: '병장',
    unit: '제1연대', specialty: '소총', origin_type: '병사', service_year: 3,
    position: '소총수', mobilization_status: '동원지정', status: 'active',
    training_records: [
      { service_year: 1, training_year: 2024, training_type: '동원훈련Ⅰ형', training_round: 1, training_hours: 28, notes: '샘플: 1년차 이수' },
      { service_year: 2, training_year: 2025, training_type: '동원훈련Ⅰ형', training_round: 1, training_hours: 22, notes: '샘플: 2년차 일부 이수' },
    ],
  },
  {
    military_number: 'TEST-TR-002', name: '샘플 전입 이학생', branch: '육군', rank: '상병',
    unit: '제2연대', specialty: '통신', origin_type: '병사', service_year: 2,
    position: '통신병', mobilization_status: '학생예비군', status: 'active',
    training_records: [
      { service_year: 1, training_year: 2025, training_type: '기본훈련', training_round: 1, training_hours: 8, notes: '샘플: 학생예비군 이수' },
    ],
  },
  {
    military_number: 'TEST-TR-003', name: '샘플 신규 박이력없음', branch: '공군', rank: '일병',
    unit: '제3전대', specialty: '', origin_type: '병사', service_year: 1,
    position: '보급병', mobilization_status: '동원미지정', status: 'active', training_records: [],
  },
  {
    military_number: 'TEST-TR-004', name: '샘플 부사관 최해군', branch: '해군', rank: '하사',
    unit: '제2함대', specialty: '통신', origin_type: '부사관', service_year: 3,
    position: '통신병', mobilization_status: '동원지정', status: 'active',
    training_records: [
      { service_year: 1, training_year: 2024, training_type: '동원훈련Ⅰ형', training_round: 1, training_hours: 28, notes: '샘플: 부사관 1년차 이수' },
      { service_year: 2, training_year: 2025, training_type: '동원훈련Ⅰ형', training_round: 1, training_hours: 28, notes: '샘플: 부사관 2년차 이수' },
    ],
  },
  {
    military_number: 'TEST-TR-005', name: '샘플 전입 정공군', branch: '공군', rank: '병장',
    unit: '제10전투비행단', specialty: '정비', origin_type: '병사', service_year: 4,
    position: '병기취급병', mobilization_status: '동원미지정', status: 'active',
    training_records: [
      { service_year: 1, training_year: 2023, training_type: '기본훈련', training_round: 1, training_hours: 28, notes: '샘플: 1년차 이수' },
      { service_year: 2, training_year: 2024, training_type: '기본훈련', training_round: 1, training_hours: 28, notes: '샘플: 2년차 이수' },
      { service_year: 3, training_year: 2025, training_type: '기본훈련', training_round: 1, training_hours: 16, notes: '샘플: 3년차 일부 이수' },
    ],
  },
  {
    military_number: 'TEST-TR-006', name: '샘플 학생 이해병', branch: '해병대', rank: '상병',
    unit: '제1사단', specialty: '의무', origin_type: '병사', service_year: 2,
    position: '의무병', mobilization_status: '학생예비군', status: 'active',
    training_records: [
      { service_year: 1, training_year: 2025, training_type: '기본훈련', training_round: 1, training_hours: 8, notes: '샘플: 학생예비군 이수' },
    ],
  },
  {
    military_number: 'TEST-TR-007', name: '샘플 일부보류 장육군', branch: '육군', rank: '병장',
    unit: '제5사단', specialty: '소총', origin_type: '병사', service_year: 5,
    position: '소총수', mobilization_status: '일부보류', status: 'active',
    training_records: [
      { service_year: 5, training_year: 2026, training_type: '동원훈련Ⅱ형', training_round: 1, training_hours: 16, notes: '샘플: 일부보류 연차 일부 이수' },
    ],
  },
  {
    military_number: 'TEST-TR-008', name: '샘플 장교 윤대위', branch: '육군', rank: '대위',
    unit: '제7연대', specialty: '작전', origin_type: '장교', service_year: 2,
    position: '행정병', mobilization_status: '동원지정', status: 'active',
    training_records: [
      { service_year: 1, training_year: 2025, training_type: '동원훈련Ⅰ형', training_round: 1, training_hours: 28, notes: '샘플: 장교 1년차 이수' },
      { service_year: 2, training_year: 2026, training_type: '동원훈련Ⅰ형', training_round: 1, training_hours: 14, notes: '샘플: 장교 2년차 일부 이수' },
    ],
  },
]

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map(item => {
      if (typeof item !== 'object' || item === null || !('msg' in item)) return String(item)
      return String(item.msg)
    }).join('; ') || fallback
    return fallback
  } catch {
    return fallback
  }
}

export default function TransferIntakePage({ revision, onDataChanged, onPendingCountChange, highlightIds = [] }: {
  revision: number
  onDataChanged: () => void
  onPendingCountChange: (count: number) => void
  highlightIds?: string[]
}) {
  const [transfers, setTransfers] = useState<TransferItem[]>([])
  const [filter, setFilter] = useState<TransferStatus>('pending')
  const [loading, setLoading] = useState(true)
  const [workingId, setWorkingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<TransferForm>(emptyForm)
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [addingSamples, setAddingSamples] = useState(false)
  const highlightKey = highlightIds.join(',')

  // Copilot이 가리킨 전입자로 스크롤합니다.
  useEffect(() => {
    if (!highlightKey || loading) return
    document.querySelector('.rm-transfer-item.is-copilot-highlight')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [highlightKey, loading])
  const [sampleNotice, setSampleNotice] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetch(`${API_BASE}/transfers?status=all`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await responseError(response, '전입자 목록을 불러오지 못했습니다.'))
        return response.json() as Promise<TransferItem[]>
      })
      .then(result => {
        if (controller.signal.aborted) return
        setTransfers(result)
        onPendingCountChange(result.filter(transfer => transfer.status === 'pending').length)
        setError('')
      })
      .catch(cause => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '전입자 목록을 불러오지 못했습니다.')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision, onPendingCountChange])

  const updateTrainingRecord = (index: number, changes: Partial<TrainingRecord>) => {
    setForm(current => ({
      ...current,
      training_records: current.training_records.map((record, recordIndex) =>
        recordIndex === index ? { ...record, ...changes } : record),
    }))
  }

  const submitTransfer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormError('')
    if (form.service_year <= 0 || form.service_year > 8) {
      setFormError('복무연차는 1년차부터 8년차까지 입력하세요.')
      return
    }
    if (form.service_year <= 4 && form.mobilization_status === '해당없음') {
      setFormError('1~4년차는 유효한 동원상태를 선택해야 합니다.')
      return
    }
    if (form.training_records.some(record => record.service_year > form.service_year)) {
      setFormError('훈련 기록의 복무연차는 현재 복무연차보다 클 수 없습니다.')
      return
    }

    setSubmitting(true)
    try {
      const { military_number, training_records, ...person } = form
      const response = await fetch(`${API_BASE}/transfers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          person: { ...person, military_number: military_number.trim(), name: form.name.trim() },
          training_records: training_records.map(record => ({ ...record, notes: record.notes.trim() || null })),
        }),
      })
      if (!response.ok) throw new Error(await responseError(response, '전입자 접수에 실패했습니다.'))
      setFormOpen(false)
      setForm(emptyForm())
      setError('')
      onDataChanged()
    } catch (cause) {
      setFormError(cause instanceof Error ? cause.message : '전입자 접수에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const reviewTransfer = async (transfer: TransferItem, decision: 'confirm' | 'reject') => {
    const action = decision === 'confirm' ? '등록' : '반려'
    if (decision === 'confirm' && !window.confirm(`${transfer.person_details.name} 전입자를 등록하시겠습니까?`)) return
    setWorkingId(transfer.id)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/transfers/${transfer.id}/${decision}`, { method: 'PATCH' })
      if (!response.ok) throw new Error(await responseError(response, `전입자 ${action}에 실패했습니다.`))
      onDataChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `전입자 ${action}에 실패했습니다.`)
    } finally {
      setWorkingId(null)
    }
  }

  const addSampleData = async () => {
    setAddingSamples(true)
    setSampleNotice('')
    setError('')
    const existingNumbers = new Set(transfers.map(transfer => transfer.military_number))
    const missingSamples = sampleTransfers.filter(sample => !existingNumbers.has(sample.military_number))
    if (missingSamples.length === 0) {
      setSampleNotice('샘플 데이터가 이미 모두 등록되어 있습니다.')
      setFilter('pending')
      setAddingSamples(false)
      return
    }

    let added = 0
    try {
      for (const sample of missingSamples) {
        const { military_number, training_records, ...person } = sample
        const response = await fetch(`${API_BASE}/transfers`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            person: { ...person, military_number },
            training_records: training_records.map(record => ({ ...record, notes: record.notes || null })),
          }),
        })
        if (!response.ok) throw new Error(await responseError(response, '샘플 전입 데이터 추가에 실패했습니다.'))
        existingNumbers.add(military_number)
        added += 1
      }
      setSampleNotice(`${added}개의 테스트 전입 신청을 추가했습니다. 군번이 TEST-TR로 시작하는 가상 데이터입니다.`)
      setFilter('pending')
      onDataChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '샘플 전입 데이터 추가에 실패했습니다.')
      if (added > 0) onDataChanged()
    } finally {
      setAddingSamples(false)
    }
  }

  const visibleTransfers = transfers.filter(transfer => transfer.status === filter)
  const pendingCount = transfers.filter(transfer => transfer.status === 'pending').length

  return <main className="rm-transfer-page">
    <header className="rm-transfer-heading">
      <div><h1>전입자 검토</h1><p>개인정보와 이전 부대 훈련 이력을 확인하고 등록 여부를 결정합니다.</p></div>
      <div className="rm-transfer-heading-actions">
        <button type="button" className="rm-transfer-sample-button" disabled={addingSamples} onClick={() => void addSampleData()}>
          {addingSamples ? '샘플 추가 중...' : '샘플 데이터 추가'}
        </button>
        <button type="button" className="rm-transfer-submit-button" onClick={() => {
          setForm(emptyForm()); setFormError(''); setFormOpen(true)
        }}>+ 전입 정보 접수</button>
      </div>
    </header>
    <nav className="rm-transfer-filters" aria-label="전입자 상태 필터">
      {([
        ['pending', `확인 대기 (${pendingCount})`],
        ['confirmed', '등록 완료'],
        ['rejected', '반려'],
      ] as const).map(([value, label]) => <button key={value} type="button" className={filter === value ? 'is-active' : ''}
        aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}
    </nav>
    {sampleNotice && <p className="rm-transfer-sample-notice" role="status">{sampleNotice}</p>}
    {error && <p className="rm-transfer-error" role="alert">{error}</p>}
    {loading ? <p className="rm-transfer-empty">전입자 목록을 불러오는 중입니다.</p>
      : visibleTransfers.length === 0 ? <p className="rm-transfer-empty">{filter === 'pending' ? '확인 대기 중인 전입자가 없습니다.' : '해당 전입 내역이 없습니다.'}</p>
      : <div className="rm-transfer-list">{visibleTransfers.map(transfer => {
        const person = transfer.person_details
        const totalHours = transfer.training_records.reduce((total, record) => total + record.training_hours, 0)
        const highlighted = highlightIds.includes(transfer.military_number)
        return <article className={`rm-transfer-item${highlighted ? ' is-copilot-highlight' : ''}`} key={transfer.id}>
          <header><div><h2>{person.name}</h2><span>{person.military_number}</span></div>
            <div className="rm-transfer-status-group">
              {transfer.status === 'confirmed' && transfer.assigned_squad_id !== null && <span className="rm-transfer-assigned-squad">자동편성 {transfer.assigned_squad_id}번 분대</span>}
              <span className={`rm-transfer-status is-${transfer.status}`}>{transfer.status === 'pending' ? '확인 대기' : transfer.status === 'confirmed' ? '등록 완료' : '반려'}</span>
            </div>
          </header>
          <dl className="rm-transfer-person-details">
            <div><dt>군종 / 계급</dt><dd>{person.branch} / {person.rank ?? '미등록'}</dd></div>
            <div><dt>복무연차</dt><dd>{person.service_year}년차</dd></div>
            <div><dt>동원상태</dt><dd>{person.mobilization_status}</dd></div>
            <div><dt>출신 유형</dt><dd>{person.origin_type || '미등록'}</dd></div>
            <div><dt>소속 부대</dt><dd>{person.unit || '미등록'}</dd></div>
            <div><dt>직책 / 주특기</dt><dd>{person.position || '미등록'} / {person.specialty || '미등록'}</dd></div>
            <div><dt>상태</dt><dd>{person.status === 'active' ? '복무 중' : person.status === 'on_leave' ? '휴가 중' : person.status}</dd></div>
            <div><dt>접수일</dt><dd>{new Date(transfer.submitted_at).toLocaleDateString('ko-KR')}</dd></div>
          </dl>
          <section className="rm-transfer-training" aria-label={`${person.name} 훈련 이력`}>
            <header><h3>이전 훈련 이력</h3><strong>총 {totalHours}시간</strong></header>
            {transfer.training_records.length === 0 ? <p>등록된 이수 훈련 이력이 없습니다.</p> : <div className="rm-transfer-training-scroll">
              <table><thead><tr><th>복무연차</th><th>훈련연도</th><th>훈련종류</th><th>차수</th><th>이수시간</th><th>메모</th></tr></thead>
                <tbody>{transfer.training_records.map((record, index) => <tr key={`${record.service_year}-${record.training_year}-${index}`}>
                  <td>{record.service_year}년차</td><td>{record.training_year}년</td><td>{record.training_type}</td>
                  <td>{record.training_round}차</td><td>{record.training_hours}시간</td><td>{record.notes || '—'}</td>
                </tr>)}</tbody></table>
            </div>}
          </section>
          {transfer.status === 'pending' && <footer>
            <button type="button" className="rm-transfer-reject-button" disabled={workingId === transfer.id}
              onClick={() => void reviewTransfer(transfer, 'reject')}>{workingId === transfer.id ? '처리 중...' : '반려'}</button>
            <button type="button" className="rm-transfer-confirm-button" disabled={workingId === transfer.id}
              onClick={() => void reviewTransfer(transfer, 'confirm')}>{workingId === transfer.id ? '처리 중...' : '확인 후 인원 등록'}</button>
          </footer>}
        </article>
      })}</div>}

    {formOpen && <div className="rm-transfer-modal-backdrop" onMouseDown={event => {
      if (event.target === event.currentTarget && !submitting) setFormOpen(false)
    }}>
      <section className="rm-transfer-modal" role="dialog" aria-modal="true" aria-labelledby="rm-transfer-form-title">
        <header><div><span>TRANSFER INTAKE</span><h2 id="rm-transfer-form-title">전입 정보 접수</h2></div>
          <button type="button" aria-label="닫기" disabled={submitting} onClick={() => setFormOpen(false)}>×</button></header>
        <form onSubmit={submitTransfer}>
          <section><h3>개인정보</h3><div className="rm-transfer-form-grid">
            <label>군번 *<input required value={form.military_number} onChange={event => setForm(current => ({ ...current, military_number: event.target.value }))} /></label>
            <label>이름 *<input required value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} /></label>
            <label>군종<select value={form.branch} onChange={event => setForm(current => ({ ...current, branch: event.target.value }))}>{branches.map(value => <option key={value}>{value}</option>)}</select></label>
            <label>계급<select value={form.rank} onChange={event => setForm(current => ({ ...current, rank: event.target.value }))}>{ranks.map(value => <option key={value}>{value}</option>)}</select></label>
            <label>복무연차<input type="number" min="1" max="8" required value={form.service_year} onChange={event => setForm(current => ({ ...current, service_year: Number(event.target.value) }))} /></label>
            <label>동원상태<select value={form.mobilization_status} onChange={event => setForm(current => ({ ...current, mobilization_status: event.target.value }))}>{mobilizationStatuses.filter(value => form.service_year > 4 || value !== '해당없음').map(value => <option key={value}>{value}</option>)}</select></label>
            <label>출신 유형<select value={form.origin_type} onChange={event => setForm(current => ({ ...current, origin_type: event.target.value }))}><option>병사</option><option>부사관</option><option>장교</option></select></label>
            <label>직책 *<input required value={form.position} onChange={event => setForm(current => ({ ...current, position: event.target.value }))} /></label>
            <label>소속 부대<input value={form.unit} onChange={event => setForm(current => ({ ...current, unit: event.target.value }))} /></label>
            <label>주특기<input value={form.specialty} onChange={event => setForm(current => ({ ...current, specialty: event.target.value }))} /></label>
            <label>상태<select value={form.status} onChange={event => setForm(current => ({ ...current, status: event.target.value }))}><option value="active">복무 중</option><option value="on_leave">휴가 중</option></select></label>
          </div></section>
          <section className="rm-transfer-form-training"><header><div><h3>이전 훈련 이력</h3><p>실제로 이수한 기록만 입력하세요.</p></div>
            <button type="button" onClick={() => setForm(current => ({ ...current, training_records: [...current.training_records, {
              service_year: Math.min(current.service_year, 8), training_year: new Date().getFullYear(),
              training_type: '기본훈련', training_round: 1, training_hours: 1, notes: '',
            }] }))}>+ 훈련 기록</button></header>
            {form.training_records.map((record, index) => <div className="rm-transfer-record-form" key={index}>
              <label>복무연차<select value={record.service_year} onChange={event => updateTrainingRecord(index, { service_year: Number(event.target.value) })}>{Array.from({ length: Math.min(form.service_year, 8) }, (_, yearIndex) => yearIndex + 1).map(year => <option key={year} value={year}>{year}년차</option>)}</select></label>
              <label>훈련연도<input type="number" min="1" required value={record.training_year} onChange={event => updateTrainingRecord(index, { training_year: Number(event.target.value) })} /></label>
              <label>훈련종류<select value={record.training_type} onChange={event => updateTrainingRecord(index, { training_type: event.target.value })}>{trainingTypes.map(value => <option key={value}>{value}</option>)}</select></label>
              <label>차수<select value={record.training_round} onChange={event => updateTrainingRecord(index, { training_round: Number(event.target.value) })}><option value={1}>1차</option><option value={2}>2차</option><option value={3}>3차</option></select></label>
              <label>이수시간<input type="number" min="1" required value={record.training_hours} onChange={event => updateTrainingRecord(index, { training_hours: Number(event.target.value) })} /></label>
              <label>메모<input value={record.notes} onChange={event => updateTrainingRecord(index, { notes: event.target.value })} /></label>
              <button type="button" className="rm-transfer-remove-record" aria-label={`${index + 1}번째 훈련 기록 삭제`}
                onClick={() => setForm(current => ({ ...current, training_records: current.training_records.filter((_, recordIndex) => recordIndex !== index) }))}>기록 삭제</button>
            </div>)}
            {form.training_records.length === 0 && <p className="rm-transfer-no-records">이수 기록이 없으면 비워 두세요.</p>}
          </section>
          {formError && <p className="rm-transfer-error" role="alert">{formError}</p>}
          <footer><button type="button" disabled={submitting} onClick={() => setFormOpen(false)}>취소</button>
            <button type="submit" disabled={submitting}>{submitting ? '접수 중...' : '검토 목록에 접수'}</button></footer>
        </form>
      </section>
    </div>}
  </main>
}