import { useEffect, useRef } from 'react'
import ProsecutionDraft from './ProsecutionDraft'

/** 고발대상자 목록의 '고발서작성' 버튼으로 여는 팝업. 기존 고발장 작성 화면을 대상자 선택 상태로 보여줍니다. */
export default function ProsecutionDraftDialog({ revision, personId, name, onClose }: {
  revision: number; personId: string; name: string; onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal() }, [])
  return <dialog ref={dialog} className="prosecution-modal prosecution-draft-dialog" aria-labelledby="prosecution-draft-dialog-title"
    onCancel={event => { event.preventDefault(); onClose() }}>
    <header>
      <div><h2 id="prosecution-draft-dialog-title">고발서 작성 · {name}</h2><p>{personId}</p></div>
      <button type="button" onClick={onClose}>닫기</button>
    </header>
    <div className="prosecution-draft-dialog-body">
      <ProsecutionDraft revision={revision} initialPersonId={personId} />
    </div>
  </dialog>
}