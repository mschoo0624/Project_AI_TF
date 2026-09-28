import { useEffect, useState } from 'react'

type Draft = { name: string; military_number: string; unit: string; branch: string; status: string; mobilization_status: string; position: string; specialty: string }
type Profile = Omit<Draft, 'unit' | 'mobilization_status' | 'position' | 'specialty'> & {
  unit: string | null; mobilization_status: string | null; position: string | null; specialty: string | null
  rank: string | null; service_year: number | null
}
type Options = { branches: string[]; statuses: Record<string, string>; mobilization_statuses: string[]; specialties: Record<string, string[]> }
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const labels: Record<keyof Draft, string> = { name: '성명', military_number: '군번', unit: '소속 부대', branch: '군별', status: '상태', mobilization_status: '동원 상태', position: '직책', specialty: '주특기' }

export default function PersonProfileFields({ person, squadName, onSaved }: { person: Profile; squadName: string; onSaved: (person: Profile) => void }) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [options, setOptions] = useState<Options | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fields, setFields] = useState<Partial<Record<keyof Draft, string>>>({})
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/persons/profile-options`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('수정 기준표를 불러오지 못했습니다. 상세 정보를 다시 열어 주세요.')
      return response.json() as Promise<Options>
    }).then(result => { if (!controller.signal.aborted) setOptions(result) })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '수정 기준표 조회 실패') })
    return () => controller.abort()
  }, [])

  const save = async () => {
    if (!draft || busy) return
    setBusy(true); setError(''); setFields({})
    try {
      const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(person.military_number)}/profile`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft),
      })
      if (!response.ok) {
        const data = await response.json() as { detail?: string | { fields?: Partial<Record<keyof Draft, string>> } }
        if (typeof data.detail === 'object' && data.detail?.fields) {
          setFields(data.detail.fields)
          throw new Error('표시된 항목을 확인해 주세요. 변경사항은 저장되지 않았습니다.')
        }
        throw new Error(typeof data.detail === 'string' ? data.detail : '입력 내용을 확인해 주세요.')
      }
      const updated = await response.json() as Profile
      setDraft(null)
      onSaved(updated)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '저장에 실패했습니다.') }
    finally { setBusy(false) }
  }
  const field = (key: keyof Draft) => {
    const value = person[key]
    if (!draft) return key === 'status' ? ({ active: '복무 중', on_leave: '휴가 중', inactive: '비활성' }[person.status] ?? person.status) : value || '미등록'
    const choices = key === 'branch' ? options?.branches
      : key === 'status' ? Object.keys(options?.statuses ?? {})
      : key === 'mobilization_status' ? options?.mobilization_statuses
      : key === 'position' ? Object.keys(options?.specialties ?? {}) : undefined
    const props = { id: `profile-${key}`, 'aria-label': labels[key], 'aria-invalid': !!fields[key], 'aria-describedby': fields[key] ? `profile-error-${key}` : undefined, disabled: busy, value: draft[key],
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setDraft({ ...draft, [key]: event.target.value }) }
    return <>{choices ? <select {...props}>
      {!choices.includes(draft[key]) && <option value={draft[key]}>{draft[key] || '미등록'}</option>}
      {choices.map(choice => <option key={choice} value={choice}>{key === 'status' ? options?.statuses[choice] : choice}</option>)}
    </select> : <input {...props} maxLength={key === 'military_number' ? 50 : 100} list={key === 'specialty' ? 'profile-specialties' : undefined} />}
    {fields[key] && <small id={`profile-error-${key}`} className="rm-profile-field-error">{fields[key]}</small>}</>
  }
  return <form className="rm-profile-form" onSubmit={event => { event.preventDefault(); void save() }}>
    <div className="rm-profile-actions">{draft ? <>
      <button key="save" type="submit" disabled={busy}>{busy ? '저장 중…' : '확인'}</button>
      <button key="cancel" type="button" disabled={busy} onClick={() => { setDraft(null); setFields({}); setError('') }}>취소</button>
    </> : <button key="edit" type="button" disabled={!options} onClick={event => {
      // Cancel activation before editing replaces this control with a submit button.
      event.preventDefault()
      setFields({}); setError('')
      setDraft({ name: person.name, military_number: person.military_number, unit: person.unit ?? '', branch: person.branch, status: person.status, mobilization_status: person.mobilization_status ?? '', position: person.position ?? '', specialty: person.specialty ?? '' })
    }}>수정</button>}</div>
    {error && <p className="rm-profile-error" role="alert">{error}</p>}
    <dl className="rm-detail-fields">
      {(['name', 'military_number', 'unit'] as const).map(key => <div key={key}><dt>{labels[key]}</dt><dd>{field(key)}</dd></div>)}
      <div><dt>편성 분대</dt><dd>{squadName}{draft && <small className="rm-profile-readonly">수정 불가</small>}</dd></div>
      <div><dt>군별</dt><dd>{field('branch')}</dd></div>
      <div><dt>계급</dt><dd>{person.rank ?? '미등록'}{draft && <small className="rm-profile-readonly">수정 불가</small>}</dd></div>
      {(['status', 'mobilization_status', 'position', 'specialty'] as const).map(key => <div key={key}><dt>{labels[key]}</dt><dd>{field(key)}</dd></div>)}
      <div><dt>연차</dt><dd>{person.service_year === null ? '미등록' : `${person.service_year}년차`}{draft && <small className="rm-profile-readonly">수정 불가</small>}</dd></div>
    </dl>
    <datalist id="profile-specialties">{[...new Set(Object.values(options?.specialties ?? {}).flat())].map(code => <option key={code} value={code} />)}</datalist>
  </form>
}
