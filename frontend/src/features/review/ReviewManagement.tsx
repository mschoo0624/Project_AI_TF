import { useEffect, useMemo, useState } from 'react'
import {
  acceptDocument, fetchBootstrap, rejectDocument, verifyDocument,
  type Bootstrap, type Person, type QueueItem,
} from './api'

const CLASS_STYLE: Record<string, string> = {
  법규보류: 'text-emerald-800 border-emerald-800',
  방침보류: 'text-emerald-800 border-emerald-800',
  후순위조정: 'text-emerald-800 border-emerald-800',
  연기: 'text-amber-800 border-amber-800',
  일반: 'text-slate-500 border-slate-300',
}

function ClassChip({ label }: { label: string }) {
  const cls = CLASS_STYLE[label] ?? 'text-slate-500 border-slate-300'
  return <span className={`inline-block rounded border px-2 py-0.5 text-[12px] font-semibold ${cls}`}>{label}</span>
}

function Tabs({ tab, setTab, queueLeft }: { tab: 'roster' | 'inbox'; setTab: (t: 'roster' | 'inbox') => void; queueLeft: number }) {
  const base = 'px-3 py-1.5 text-[13.5px] border-b-2'
  return (
    <nav className="flex gap-1">
      <button className={`${base} ${tab === 'inbox' ? 'border-emerald-800 text-slate-900 font-semibold' : 'border-transparent text-slate-500'}`}
              onClick={() => setTab('inbox')}>
        검토함
        <span className="ml-1.5 rounded-full bg-slate-700 px-1.5 text-[11px] font-semibold text-white">{queueLeft}</span>
      </button>
      <button className={`${base} ${tab === 'roster' ? 'border-emerald-800 text-slate-900 font-semibold' : 'border-transparent text-slate-500'}`}
              onClick={() => setTab('roster')}>
        명부
      </button>
    </nav>
  )
}

function ReasonList({ title, items, tone }: { title: string; items: string[]; tone?: 'alert' }) {
  if (items.length === 0) return null
  return (
    <div className="mt-4">
      <h3 className={`mb-2 text-[12.5px] font-semibold ${tone === 'alert' ? 'text-amber-700' : 'text-slate-500'}`}>{title}</h3>
      <ul className={`space-y-1 text-[13px] ${tone === 'alert' ? 'text-amber-700' : 'text-slate-700'}`}>
        {items.map((r, i) => <li key={i}>{tone === 'alert' ? '! ' : '· '}{r}</li>)}
      </ul>
    </div>
  )
}

function PersonDetail({ person, onClose }: { person: Person; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-10 grid place-items-center bg-slate-900/45 p-6" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <section className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-300 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-4">
          <div>
            <p className="mb-0.5 text-[11px] font-semibold tracking-wide text-emerald-800">RESERVIST</p>
            <h2 className="text-2xl font-semibold tracking-tight">{person.name}</h2>
            <p className="num mt-1 text-[13px] text-slate-500">{person.person_id} · {person.occupation ?? '직업 미상'} · {person.branch}</p>
          </div>
          <button className="rounded p-1 text-2xl leading-none text-slate-400 hover:text-slate-700" onClick={onClose}>×</button>
        </div>

        <div className="px-6 py-5">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <ClassChip label={person.classification} />
            {person.rule_code && <span className="num text-[12px] text-slate-400">{person.rule_code}</span>}
            <span className="text-[13px] text-slate-500">{person.resource_year}년차 · 동원지정 {person.mobilization_designated ? 'O' : 'X'}</span>
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[
              ['동원훈련', person.mobilization],
              ['교육훈련', person.training],
              ['부과 시간', `${person.hours}h${person.makeup_hours ? ` +보충${person.makeup_hours}` : ''}`],
              ['이월', `${person.carryover}h`],
            ].map(([label, value]) => (
              <div key={label} className="rounded border border-slate-200 p-3">
                <div className="text-[11.5px] text-slate-400">{label}</div>
                <div className="num mt-0.5 font-semibold">{value}</div>
              </div>
            ))}
          </div>

          <ReasonList title="판정 근거" items={person.reasons} />
          <ReasonList title="알람" items={person.alerts} tone="alert" />

          {person.documents.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-[12.5px] font-semibold text-slate-500">제출 서류</h3>
              <div className="divide-y divide-slate-100 rounded border border-slate-200">
                {person.documents.map((d) => (
                  <div key={d.id} className="flex items-center justify-between px-3 py-2 text-[13px]">
                    <div>
                      <span className="font-medium">{d.type}</span>
                      <span className="ml-2 text-slate-400">{d.owner}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="num text-slate-400">발급 {d.issued}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[11.5px] font-semibold ${
                        d.status === '승인' ? 'bg-emerald-50 text-emerald-800'
                        : d.status === '반려' ? 'bg-rose-50 text-rose-700'
                        : d.status === '확인요청' ? 'bg-amber-50 text-amber-800'
                        : 'bg-slate-100 text-slate-600'}`}>{d.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function RosterView({ people, onSelect }: { people: Person[]; onSelect: (p: Person) => void }) {
  const [search, setSearch] = useState('')
  const [cls, setCls] = useState('')
  const [onlyPending, setOnlyPending] = useState(false)

  const filtered = useMemo(() => people.filter((p) => {
    const term = search.trim().toLowerCase()
    if (term && !p.name.toLowerCase().includes(term) && !p.person_id.includes(term)) return false
    if (cls && p.classification !== cls) return false
    if (onlyPending && p.pending_count === 0) return false
    return true
  }), [people, search, cls, onlyPending])

  return (
    <section className="rounded border border-slate-300 bg-white">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
        <input
          value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="성명 또는 군번 검색"
          className="w-56 rounded border border-slate-300 px-2.5 py-1.5 text-[13px] outline-emerald-800"
        />
        <select value={cls} onChange={(e) => setCls(e.target.value)} className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-[13px]">
          <option value="">전체 분류</option>
          {['법규보류', '방침보류', '후순위조정', '연기', '일반'].map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-[13px] text-slate-600">
          <input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
          검토 대기만
        </label>
        <span className="ml-auto text-[12.5px] text-slate-500 num">{filtered.length}명 표시 / 전체 {people.length}명</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="bg-slate-50 text-left text-[12px] font-semibold text-slate-500">
              {['군번', '성명', '직업', '연차', '분류', '훈련', '시간', '검토'].map((h) => (
                <th key={h} className="whitespace-nowrap border-b border-slate-200 px-3 py-2">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.person_id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => onSelect(p)}>
                <td className="num px-3 py-2">{p.person_id}</td>
                <td className="px-3 py-2 font-medium">{p.name}</td>
                <td className="px-3 py-2 text-slate-600">{p.occupation ?? '—'}</td>
                <td className="num px-3 py-2">{p.resource_year}년차</td>
                <td className="px-3 py-2"><ClassChip label={p.classification} /></td>
                <td className="px-3 py-2 text-slate-600">{p.training}</td>
                <td className="num px-3 py-2">{p.total_hours}h</td>
                <td className="px-3 py-2">
                  {p.pending_count > 0
                    ? <span className="rounded border border-slate-700 px-2 py-0.5 text-[11.5px] font-semibold text-slate-700">대기 {p.pending_count}</span>
                    : <span className="text-slate-300">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ReviewPanel({
  item, reasons, verifyReasons, onDone,
}: {
  item: QueueItem
  reasons: Bootstrap['reject_reasons']
  verifyReasons: Bootstrap['verify_reasons']
  onDone: (label: string, changed: boolean, message?: string) => void
}) {
  const [mode, setMode] = useState<'none' | 'reject' | 'verify'>('none')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const runAccept = async () => {
    setBusy(true)
    await acceptDocument(item.id, {})
    setBusy(false)
    onDone('승인', item.current_classification !== item.if_accepted_classification)
  }
  const runReject = async (code: string, message?: string) => {
    setBusy(true)
    await rejectDocument(item.id, code, message)
    setBusy(false)
    onDone('반려', false, message)
  }
  const runVerify = async (code: string, message?: string) => {
    setBusy(true)
    await verifyDocument(item.id, code, message)
    setBusy(false)
    onDone('확인요청', false, message)
  }

  return (
    <aside className="w-[340px] shrink-0 overflow-y-auto border-l border-slate-300 bg-white p-4">
      <dl className="mb-4 grid grid-cols-[60px_1fr] gap-y-1.5 text-[13px]">
        <dt className="text-slate-500">성명</dt><dd>{item.person_name}</dd>
        <dt className="text-slate-500">군번</dt><dd className="num">{item.person_id}</dd>
        <dt className="text-slate-500">직업</dt><dd>{item.occupation ?? '—'}</dd>
        <dt className="text-slate-500">구분</dt><dd>{item.owner}</dd>
        <dt className="text-slate-500">현재</dt><dd><ClassChip label={item.current_classification} /></dd>
      </dl>

      {item.verify_number ? (
        <div className="mb-4 rounded border border-emerald-200 bg-emerald-50 p-3 text-[12.5px]">
          <b className="mb-0.5 block">문서확인번호 {item.verify_number}</b>
          발급처에서 진위를 확인할 수 있습니다.
        </div>
      ) : (
        <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-[12.5px]">
          <b className="mb-0.5 block">문서확인번호 없음</b>
          발급처 대조가 불가능합니다. 의심되면 확인요청으로 넘기세요.
        </div>
      )}

      {item.file_path && (
        <a href={item.file_path} target="_blank" rel="noopener noreferrer"
           className="mb-4 block rounded border border-slate-300 px-3 py-2 text-center text-[13px] text-emerald-800 hover:bg-slate-50">
          원본 서류 열기 ↗
        </a>
      )}

      <div className="flex flex-col gap-2">
        <button disabled={busy} onClick={runAccept}
                className="rounded bg-emerald-800 px-3 py-2 text-[13.5px] font-semibold text-white disabled:opacity-50">
          승인
        </button>
        <button disabled={busy} onClick={() => setMode(mode === 'reject' ? 'none' : 'reject')}
                className="rounded border border-rose-700 px-3 py-2 text-[13.5px] font-semibold text-rose-700">
          반려
        </button>
        <button disabled={busy} onClick={() => setMode(mode === 'verify' ? 'none' : 'verify')}
                className="rounded border border-amber-700 px-3 py-2 text-[13.5px] font-semibold text-amber-800">
          확인요청
        </button>
      </div>

      {mode === 'reject' && (
        <div className="mt-3 space-y-1.5 rounded border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-[12.5px] text-slate-500">사유를 고르면 안내 문구가 함께 발송됩니다.</p>
          {reasons.map((r) => (
            <button key={r.code} onClick={() => r.code === 'OTHER' ? undefined : runReject(r.code, r.message)}
                    className="block w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-left text-[13px] hover:bg-slate-100">
              <span className="flex items-baseline justify-between gap-2">
                <span>{r.label}</span>
                <span className="shrink-0 text-[11px] text-slate-400">{r.can_resubmit ? '재제출 가능' : '재제출 불가'}</span>
              </span>
              {r.message && <small className="mt-0.5 block text-[11.5px] text-slate-500">{r.message}</small>}
            </button>
          ))}
          <div className="pt-1">
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="기타 사유 설명"
                      className="w-full rounded border border-slate-300 p-2 text-[13px]" rows={2} />
            <button disabled={!note.trim()} onClick={() => runReject('OTHER', note)}
                    className="mt-1.5 w-full rounded border border-slate-300 bg-white py-1.5 text-[13px] disabled:opacity-40">
              기타 사유로 반려
            </button>
          </div>
        </div>
      )}

      {mode === 'verify' && (
        <div className="mt-3 space-y-1.5 rounded border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-[12.5px] text-slate-500">판단하지 않고 발급기관 확인 대상으로 넘깁니다.</p>
          {verifyReasons.map((r) => (
            <button key={r.code} onClick={() => r.code === 'OTHER' ? undefined : runVerify(r.code)}
                    className="block w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-left text-[13px] hover:bg-slate-100">
              {r.label}
            </button>
          ))}
        </div>
      )}
    </aside>
  )
}

function InboxView({ queue, bootstrap }: { queue: QueueItem[]; bootstrap: Bootstrap }) {
  const [items, setItems] = useState(queue.map((q) => ({ ...q, done: null as null | string })))
  const [selectedId, setSelectedId] = useState<string | null>(items[0]?.id ?? null)
  const selected = items.find((i) => i.id === selectedId) ?? null

  const handleDone = (label: string, changed: boolean, message?: string) => {
    if (!selectedId) return
    setItems((prev) => prev.map((i) => i.id === selectedId ? { ...i, done: label } : i))
    const next = items.find((i) => i.id !== selectedId && !i.done)
    setTimeout(() => setSelectedId(next?.id ?? null), 700)
    if (message) console.log('발송 안내:', message)
    void changed
  }

  const left = items.filter((i) => !i.done).length

  return (
    <div className="flex h-[calc(100vh-180px)] min-h-[480px] overflow-hidden rounded border border-slate-300 bg-white">
      <div className="w-[280px] shrink-0 overflow-y-auto border-r border-slate-300">
        <div className="border-b border-slate-200 px-3.5 py-2.5 text-[12.5px] text-slate-500">
          검토 대기 <b className="num text-slate-900">{left}</b>건 · 제출 오래된 순
        </div>
        {items.length === 0 && <p className="p-4 text-[13px] text-slate-400">대기 중인 서류가 없습니다.</p>}
        {items.map((it) => (
          <button key={it.id} onClick={() => setSelectedId(it.id)}
                  className={`block w-full border-b border-slate-100 px-3.5 py-2.5 text-left ${
                    it.done ? 'opacity-40' : ''} ${selectedId === it.id ? 'bg-slate-50 border-l-2 border-l-emerald-800' : 'border-l-2 border-l-transparent hover:bg-slate-50'}`}>
            <div className="flex items-baseline gap-1.5">
              <span className={`text-[13.5px] font-semibold ${it.done ? 'line-through' : ''}`}>{it.person_name}</span>
              <span className="num text-[11.5px] text-slate-400">{it.person_id}</span>
            </div>
            <div className="text-[12.5px] text-slate-500">{it.type}</div>
            <div className="num text-[11.5px] text-slate-400">
              발급 {it.issued} · 대기 {it.waiting_days}일{it.done ? ` · ${it.done}` : ''}
            </div>
          </button>
        ))}
      </div>

      <div className="flex flex-1 items-center justify-center bg-slate-100">
        {selected?.file_path ? (
          <iframe title="서류 원본" src={selected.file_path} className="h-full w-full bg-white" />
        ) : (
          <p className="p-10 text-center text-[13.5px] text-slate-400">왼쪽에서 서류를 선택하세요.</p>
        )}
      </div>

      {selected && (
        <ReviewPanel key={selected.id} item={selected} reasons={bootstrap.reject_reasons} verifyReasons={bootstrap.verify_reasons} onDone={handleDone} />
      )}
    </div>
  )
}

export default function ReviewManagement() {
  const [data, setData] = useState<Bootstrap | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'roster' | 'inbox'>('inbox')
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null)

  useEffect(() => {
    fetchBootstrap().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : '불러오지 못했습니다'))
  }, [])

  if (error) {
    return (
      <div className="grid min-h-full place-items-center p-6">
        <div className="max-w-md rounded border border-rose-200 bg-white p-5">
          <p className="font-semibold text-rose-700">데이터를 불러오지 못했습니다</p>
          <p className="mt-1 text-[13px] text-slate-500">{error}</p>
        </div>
      </div>
    )
  }
  if (!data) return <div className="grid min-h-full place-items-center text-slate-400">불러오는 중…</div>

  return (
    <div className="min-h-full text-slate-900">
      <header className="flex items-center gap-6 border-b border-slate-300 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-emerald-800 font-mono text-[15px] font-bold text-white">31</span>
          <div>
            <p className="text-[11px] font-semibold tracking-wide text-emerald-800">RESERVE FORCE</p>
            <h1 className="text-[16px] font-semibold">보류·연기 판정 시스템</h1>
          </div>
        </div>
        <Tabs tab={tab} setTab={setTab} queueLeft={data.queue.length} />
        <span className="num ml-auto text-[12.5px] text-slate-500">기준일 {data.as_of} · 훈련일 {data.training_date}</span>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        {tab === 'roster'
          ? <RosterView people={data.people} onSelect={setSelectedPerson} />
          : <InboxView queue={data.queue} bootstrap={data} />}
      </main>

      {selectedPerson && <PersonDetail person={selectedPerson} onClose={() => setSelectedPerson(null)} />}
    </div>
  )
}