import { useEffect, useRef, useState } from 'react'
import { errorMessage, jsonBody, prosecutionRequest } from './api'
import { applySources, createBlankDraft, draftSizeError, fieldsEqual, sameTraining } from './draft'
import type { DraftFields, DraftSources, SavedDocument, Target, Training } from './types'

export default function useProsecutionDraft(revision: number) {
  const [targets, setTargets] = useState<Target[]>([])
  const [personId, setPersonId] = useState('')
  const [sources, setSources] = useState<DraftSources | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [form, setForm] = useState<DraftFields>(createBlankDraft)
  const [draftRecords, setDraftRecords] = useState<Training[]>([])
  const [saved, setSaved] = useState<SavedDocument | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [notice, setNotice] = useState('')
  const [retryRevision, setRetryRevision] = useState(0)
  const [showTemplate, setShowTemplate] = useState(false)
  const [savedListOpen, setSavedListOpen] = useState(false)
  const [printDocument, setPrintDocument] = useState<SavedDocument | null>(null)
  const clientId = useRef('')
  const saveInFlight = useRef(false)
  const generated = Boolean(form.military_number)
  const dirty = generated && (!saved || !fieldsEqual(form, saved.fields))
  const limitError = saved ? '' : draftSizeError(form, draftRecords)
  const canSave = generated && !saving && !limitError && Boolean(saved || (!loading && sources?.is_target && draftRecords.length))

  useEffect(() => {
    if (!dirty && !saving) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const beforePageChange = (event: Event) => {
      if (saving) {
        event.preventDefault()
        setNotice('저장이 끝난 뒤 페이지를 이동하세요.')
      } else if (!window.confirm('저장하지 않은 고발장 변경사항이 있습니다. 변경사항을 버리고 이동하시겠습니까?')) {
        event.preventDefault()
      }
    }
    window.addEventListener('beforeunload', warn)
    window.addEventListener('app-before-page-change', beforePageChange)
    return () => {
      window.removeEventListener('beforeunload', warn)
      window.removeEventListener('app-before-page-change', beforePageChange)
    }
  }, [dirty, saving])

  useEffect(() => {
    const controller = new AbortController()
    setListLoading(true)
    setListError('')
    prosecutionRequest<Target[]>('/reservists/prosecution-targets', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setTargets(data) })
      .catch(cause => { if (!controller.signal.aborted) setListError(errorMessage(cause)) })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false) })
    return () => controller.abort()
  }, [revision, retryRevision])

  useEffect(() => {
    const controller = new AbortController()
    setSources(null)
    setDetailError('')
    if (!personId) {
      setLoading(false)
      return () => controller.abort()
    }
    setLoading(true)
    prosecutionRequest<DraftSources>(`/reservists/${encodeURIComponent(personId)}/prosecution-draft`, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return
        setSources(data)
        setSelected(current => clientId.current
          ? current.filter(id => data.records.some(record => record.id === id))
          : data.records.map(record => record.id))
      })
      .catch(cause => { if (!controller.signal.aborted) setDetailError(errorMessage(cause)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [personId, revision, retryRevision])

  useEffect(() => {
    if (!sources || saved || saving || sources.person.military_number !== personId) return
    const records = sources.records.filter(record => selected.includes(record.id))
    setForm(current => applySources(current, sources, records))
    setDraftRecords(records)
    if (!clientId.current) clientId.current = crypto.randomUUID()
  }, [sources, selected, personId, saved, saving])

  const discard = () => !dirty || window.confirm('저장하지 않은 변경사항이 있습니다. 변경사항을 버리고 계속하시겠습니까?')

  const selectPerson = (id: string) => {
    if (!discard()) return
    setForm(createBlankDraft())
    setSaved(null)
    setDraftRecords([])
    setSelected([])
    setSources(null)
    setSaveError('')
    setNotice('')
    setShowTemplate(false)
    clientId.current = ''
    setPersonId(id)
  }

  const changeField = (key: string, value: string) => {
    setNotice('')
    setForm(current => ({ ...current, [key]: key === 'birth_digits' ? value.replace(/\D/g, '').slice(0, 6) : value }))
  }

  const toggleTraining = (id: number, checked: boolean) => {
    setNotice('')
    setSaveError('')
    setSelected(current => checked ? [...current, id] : current.filter(value => value !== id))
  }

  const acceptSaved = (document: SavedDocument, message: string, printAfter: boolean) => {
    setSaved(document)
    setDraftRecords(document.training_snapshot)
    setNotice(message)
    if (printAfter) setPrintDocument(document)
  }

  const save = async (printAfter = false) => {
    if (!canSave || saveInFlight.current) return
    if (saved && !dirty) {
      if (printAfter) setPrintDocument(saved)
      return
    }
    saveInFlight.current = true
    setSaving(true)
    setSaveError('')
    setNotice('')
    try {
      const document = saved
        ? await prosecutionRequest<SavedDocument>(`/prosecution-documents/${saved.id}`, jsonBody('PUT', { fields: form, version: saved.version }))
        : await prosecutionRequest<SavedDocument>('/prosecution-documents', jsonBody('POST', {
          id: clientId.current, person_id: form.military_number, fields: form,
          training_record_ids: draftRecords.map(record => record.id), training_snapshot: draftRecords,
        }))
      acceptSaved(document, '고발장을 저장했습니다.', printAfter)
    } catch (cause) {
      // A failed response can still represent a committed save; recover without mixing training snapshots.
      try {
        const recovered = await prosecutionRequest<SavedDocument>(`/prosecution-documents/${saved?.id ?? clientId.current}`)
        const sameRecords = sameTraining(draftRecords, recovered.training_snapshot)
        if (fieldsEqual(form, recovered.fields) && sameRecords) {
          acceptSaved(recovered, '서버에 저장된 내용을 확인했습니다.', printAfter)
          return
        }
        if (!saved && recovered.person_id === form.military_number) {
          if (!sameRecords) {
            clientId.current = crypto.randomUUID()
            setSaveError('이전 훈련 선택으로 저장된 고발장이 확인되었습니다. 현재 선택은 새 고발장으로 유지했으니 다시 저장하세요.')
          } else {
            acceptSaved(recovered, '', false)
            setSaveError('최초 저장은 완료되었습니다. 화면의 수정 내용은 유지했으니 다시 저장하세요.')
          }
          return
        }
      } catch { /* Show the original failure if recovery also fails. */ }
      setSaveError(errorMessage(cause))
    } finally {
      saveInFlight.current = false
      setSaving(false)
    }
  }

  const openSaved = async (id: string) => {
    if (!discard()) return
    const document = await prosecutionRequest<SavedDocument>(`/prosecution-documents/${id}`)
    setSaved(document)
    setForm({ ...createBlankDraft(), ...document.fields })
    setDraftRecords(document.training_snapshot)
    setShowTemplate(false)
    setSaveError('')
    setNotice('저장된 고발장을 불러왔습니다.')
    setSavedListOpen(false)
  }

  const printSaved = async (id: string) => {
    const document = await prosecutionRequest<SavedDocument>(`/prosecution-documents/${id}`)
    setSavedListOpen(false)
    setPrintDocument(document)
  }

  return {
    targets, personId, sources, selected, form, draftRecords, saved, generated, dirty,
    saving, loading, listLoading, listError, detailError, saveError, limitError, notice, canSave,
    showTemplate, savedListOpen, printDocument,
    selectPerson, changeField, toggleTraining, save, openSaved, printSaved,
    reload: () => setRetryRevision(value => value + 1),
    toggleTemplate: () => setShowTemplate(value => !value),
    setSavedListOpen,
    closePrint: () => setPrintDocument(null),
  }
}
