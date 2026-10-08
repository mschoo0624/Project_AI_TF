import { CLASSIFIER_BASE, type Check, type Verification } from './classifierApi'

const labels = { pass: '충족', fail: '불충족', missing: '정보 부족', review: '검토 필요' }
function Condition({ check }: { check: Check }) {
  return <li className={check.required_for_result === false ? 'review-condition-optional' : ''}>
    <strong>{check.label}</strong> <span className={`review-check-${check.status}`}>{labels[check.status]}</span>
    {check.required_for_result === false && <small> · 다른 대체 요건 충족</small>}
    {check.message && check.message !== check.label && !(check.id === 'birth_information_link' && check.status === 'pass') && <p>{check.message}</p>}
    {check.evidence?.map((proof, i) => <p key={i} className="review-proof">{proof.page ? `${proof.page}쪽 · ` : ''}{proof.quote ?? proof.source}</p>)}
    {check.children && <ul>{check.children.map((child, i) => <Condition key={`${child.id}-${i}`} check={child} />)}</ul>}
  </li>
}
export default function VerificationResult({ result }: { result: Verification | null }) {
  if (!result) return <p className="review-ai-alert">검증 전입니다. 추가 정보를 확인한 뒤 검증을 실행하세요.</p>
  return <section className="review-verification" aria-label="신청 근거 검증 결과">
    <h4>{result.result_label}</h4>
    <p>규칙 검증 결과입니다. 최종 승인·반려는 담당자가 결정합니다.</p>
    <details><summary>조건별 판단과 근거 ▼</summary><ul>{result.checks.map((check, i) => <Condition key={`${check.id}-${i}`} check={check} />)}</ul></details>
    {result.related_provisions.map(citation => <details key={`${citation.table}-${citation.page}`}>
      <summary>{citation.provision} · {citation.item} ▼</summary>
      <a href={`${CLASSIFIER_BASE}/verification-sources/${citation.table}#page=${citation.page}`} target="_blank" rel="noreferrer">기준표 {citation.page}쪽 열기 ↗</a>
      <pre>{citation.page_text}</pre>
    </details>)}
  </section>
}
