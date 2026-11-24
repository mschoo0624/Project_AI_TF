import { useMemo } from 'react'
import { documentTime } from './api'
import { fieldGroups, fieldMaxLength, formatTraining, isLinkedField, textFields } from './draft'
import { documentHtml } from './DraftDocument'
import useProsecutionDraft from './useProsecutionDraft'
import ProsecutionSavedDocuments from './ProsecutionSavedDocuments'
import ProsecutionPrintDialog from './ProsecutionPrintDialog'
import templateUrl from '../../assets/[별지 6] 예비군법 위반자 고발장(예비군 조직·편성과 운영에 관한 훈령).pdf?url'
import './prosecution.css'

export default function ProsecutionDraft({ revision }: { revision: number }) {
  const draft = useProsecutionDraft(revision)
  const { form, saved, sources, saving, loading, generated, dirty, canSave, showTemplate, printDocument } = draft
  const html = useMemo(() => documentHtml(form), [form])

  return <main className="prosecution-draft">
    <header>
      <div><h1>고발장 작성</h1><p>대상자를 선택하면 인원·훈련 정보를 자동 입력합니다. 내용을 보완한 뒤 저장하거나 인쇄할 수 있습니다.</p></div>
      <div className="prosecution-header-actions">
        <button type="button" disabled={saving} onClick={() => draft.selectPerson('')}>새 고발장</button>
        <button type="button" disabled={saving} onClick={() => draft.setSavedListOpen(true)}>저장된 고발장</button>
        <button type="button" onClick={draft.toggleTemplate}>{showTemplate ? '작성 미리보기' : '원본 양식 보기'}</button>
      </div>
    </header>
    {(draft.listError || draft.detailError) && <div role="alert" className="rm-org-error">
      {draft.listError && <p>{draft.listError}</p>}{draft.detailError && <p>{draft.detailError}</p>}
      <button type="button" disabled={draft.listLoading || loading} onClick={draft.reload}>다시 불러오기</button>
    </div>}
    {draft.saveError && <p role="alert" className="rm-org-error">{draft.saveError}</p>}
    {draft.limitError && <p role="alert" className="rm-org-error">{draft.limitError}</p>}
    {draft.notice && <p role="status" className="prosecution-save-notice">{draft.notice}</p>}
    <div className="prosecution-draft-layout">
      <section className="prosecution-draft-editor" aria-label="고발장 입력">
        {!saved && <label>고발대상자
          <select value={draft.personId} disabled={draft.listLoading || saving} onChange={event => draft.selectPerson(event.target.value)}>
            <option value="">{draft.listLoading ? '목록을 불러오는 중…' : '대상자 선택'}</option>
            {draft.targets.map(target => <option key={target.military_number} value={target.military_number}>{target.name} · {target.military_number}</option>)}
          </select>
        </label>}
        {!draft.listLoading && !draft.targets.length && !draft.listError && <p>현재 고발대상자가 없습니다.</p>}
        {loading && <p>훈련 기록을 불러오는 중…</p>}
        {sources && !saved && <>
          <p>{sources.reasons.join(' / ') || '현재 고발대상자로 분류되지 않은 인원입니다.'}</p>
          <fieldset><legend>초안에 포함할 훈련</legend>
            {!sources.records.length && <p>자동 작성에 사용할 확정된 과거 무단불참 기록이 없습니다.</p>}
            {sources.records.map(record => <label className="prosecution-training-choice" key={record.id}>
              <input type="checkbox" disabled={saving || loading} checked={draft.selected.includes(record.id)}
                onChange={event => draft.toggleTraining(record.id, event.target.checked)} />
              <span>{formatTraining(record)}<small>{record.schedule_title && `${record.schedule_title} · `}확정자: {record.confirmed_by}</small></span>
            </label>)}
          </fieldset>
          {!draft.selected.length && sources.records.length > 0 && <p>저장할 고발장에 포함할 훈련을 하나 이상 선택하세요.</p>}
        </>}
        {saved && <fieldset>
          <legend>저장된 작성 근거 · {saved.fields.name}</legend><p>{saved.person_id}</p>
          {draft.draftRecords.map(record => <p key={record.id}>{formatTraining(record)}</p>)}
          <p>저장 당시 선택한 훈련입니다. 다른 훈련으로 작성하려면 ‘새 고발장’을 선택하세요.</p>
        </fieldset>}
        {generated && <>
          {fieldGroups.map(group => <fieldset key={group.title} disabled={saving || (!saved && loading)}>
            <legend>{group.title}</legend>
            <div className="prosecution-fields">{group.fields.map(([key, label]) => <label key={key}>{label}
              <input value={form[key] ?? ''} readOnly={isLinkedField(key, sources, Boolean(saved))} maxLength={fieldMaxLength(key)}
                placeholder="확인 후 입력" inputMode={key === 'birth_digits' ? 'numeric' : undefined}
                onChange={event => draft.changeField(key, event.target.value)} />
            </label>)}</div>
          </fieldset>)}
          {textFields.map(([key, label]) => <label key={key}>{label}
            <textarea disabled={saving} readOnly={isLinkedField(key, sources, Boolean(saved))} rows={5} maxLength={fieldMaxLength(key)} value={form[key]}
              placeholder={key === 'evidence' ? '실제로 확보한 자료만 기재: 소집통지서 수령증, 예비군편성카드 사본 등' : ''}
              onChange={event => draft.changeField(key, event.target.value)} />
          </label>)}
          <label>7. 관련 사건의 초범 또는 재범 여부
            <select disabled={saving} value={form.repeat} onChange={event => draft.changeField('repeat', event.target.value)}>
              <option value="">미확인</option><option value="first">초범</option><option value="repeat">재범</option>
            </select>
          </label>
          <p>원본 양식의 모든 항목을 확인하세요. 정보가 없는 항목은 출력물에서 빈칸으로 남습니다. 서명·관인은 자동 생성하지 않습니다.</p>
        </>}
      </section>
      <section className="prosecution-draft-preview" aria-label="고발장 미리보기">
        <div className="prosecution-preview-toolbar">
          <div><strong>{showTemplate ? '원본 양식' : '검토용 초안'}</strong>
            {generated && <small>{dirty ? '저장하지 않은 변경사항' : '저장됨'}{saved && ` · ${documentTime(saved.updated_at)}`}</small>}
          </div>
          <div>
            <button type="button" className="prosecution-primary" disabled={!canSave || !dirty} onClick={() => void draft.save()}>{saving ? '저장 중…' : '저장'}</button>
            <button type="button" disabled={!canSave || showTemplate} onClick={() => void draft.save(true)}>{dirty ? '저장 후 인쇄' : '인쇄 미리보기'}</button>
          </div>
        </div>
        {showTemplate ? <iframe title="고발장 원본 양식" src={templateUrl} />
          : generated ? <iframe title="고발장 초안 미리보기" srcDoc={html} />
            : <p className="prosecution-draft-empty">대상자를 선택하면 연동된 인원·훈련 정보로 초안이 작성됩니다. 저장된 문서는 ‘저장된 고발장’에서 열 수 있습니다.</p>}
      </section>
    </div>
    {draft.savedListOpen && <ProsecutionSavedDocuments onClose={() => draft.setSavedListOpen(false)} onOpen={draft.openSaved} onPrint={draft.printSaved} />}
    {printDocument && <ProsecutionPrintDialog html={documentHtml(printDocument.fields)} title={printDocument.fields.name || printDocument.person_id}
      savedAt={documentTime(printDocument.updated_at)} onClose={draft.closePrint} />}
  </main>
}
