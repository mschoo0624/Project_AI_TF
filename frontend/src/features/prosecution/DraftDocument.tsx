import { renderToStaticMarkup } from 'react-dom/server'
import { fieldGroups } from './draft'
import type { Field } from './draft'
import type { DraftFields } from './types'

const printCss = `
@page { size:A4; margin:16mm; }
* { box-sizing:border-box; } body { margin:0; color:#111; font-family:'Malgun Gothic',sans-serif; font-size:9.5pt; line-height:1.3; }
article { max-width:178mm; margin:0 auto; padding:8mm 0; }
h1 { text-align:center; font-size:20pt; margin:8px 0; } h2 { font-size:12pt; margin:10px 0 4px; break-after:avoid; }
p { margin:6px 0; white-space:pre-wrap; overflow-wrap:anywhere; }
.meta { display:flex; justify-content:space-between; font-size:9pt; color:#555; }
table { width:100%; border-collapse:collapse; table-layout:fixed; break-inside:avoid; }
th,td { border:1px solid #333; padding:3px 6px; white-space:pre-wrap; overflow-wrap:anywhere; } th { width:18%; font-weight:400; background:#f6f6f6; }
.body-text { border:1px solid #333; min-height:35px; padding:7px; }
.footer { text-align:center; margin-top:16px; break-inside:avoid; } .footer p { margin:9px 0; }
@media print { article { padding:0; } }
`

function DraftDocument({ form }: { form: DraftFields }) {
  const value = (key: string) => form[key]?.trim() || ''
  const rows = (fields: Field[]) => <table><tbody>{fields.filter((_, index) => index % 2 === 0).map(([key, label], index) => {
    const next = fields[index * 2 + 1]
    return <tr key={key}><th>{label}</th><td colSpan={next ? 1 : 3}>{value(key)}</td>{next && <><th>{next[1]}</th><td>{value(next[0])}</td></>}</tr>
  })}</tbody></table>
  return <article>
    <div className="meta"><span>[별지 제6호서식] 기반 작성</span><strong>검토용 초안 · 제출 전 확인 필요</strong></div>
    <h1>예비군법 위반자 고발장</h1><p style={{ textAlign: 'right' }}>{value('number') && `[${value('number')}]`}</p>
    <h2>1. 고발인</h2>{rows(fieldGroups[1].fields)}
    <h2>2. 피고발인</h2>{rows(fieldGroups[2].fields)}
    <h2>3. 고발취지</h2><p>고발인은 피고발인을 예비군법 제15조 위반죄로 고발하니 처벌하여 주시기 바랍니다.</p>
    <h2>4. 범죄사실</h2>{rows(fieldGroups[3].fields)}<p className="body-text">범죄사실요약: {value('summary')}</p>
    <h2>5. 고발이유</h2><p className="body-text">{value('reason')}</p>
    <h2>6. 증거자료</h2><p className="body-text">{value('evidence')}</p>
    <h2>7. 관련 사건의 초범 또는 재범 여부</h2><p>{form.repeat === 'first' ? '☑ 초범　□ 재범' : form.repeat === 'repeat' ? '□ 초범　☑ 재범' : '□ 초범　□ 재범 (미확인)'}</p>
    <div className="footer"><p>{value('date')}</p><p>고발인　{value('commander')}　(관인)</p><p><strong>{value('police')} 귀중</strong></p></div>
  </article>
}

export const documentHtml = (form: DraftFields) => `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>고발장 검토용 초안</title><style>${printCss}</style></head><body>${renderToStaticMarkup(<DraftDocument form={form} />)}</body></html>`
