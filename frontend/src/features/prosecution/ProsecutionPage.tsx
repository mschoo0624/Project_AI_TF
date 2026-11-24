import { useState } from 'react'
import WorkspaceTabs from '../../components/WorkspaceTabs'
import ProsecutionRoster from './ProsecutionRoster'
import ProsecutionDraft from './ProsecutionDraft'
import './prosecution.css'

export default function ProsecutionPage({ revision }: { revision: number }) {
  const [tab, setTab] = useState<'targets' | 'draft'>('targets')

  return <div className="review-management rm-prosecution-management">
    <WorkspaceTabs<'targets' | 'draft'> label="고발대상자 메뉴" value={tab} onChange={setTab}
      items={[{ id: 'targets', label: '고발대상자 목록' }, { id: 'draft', label: '고발장 작성' }]} />
    <div className="review-main-content rm-prosecution-content review-roster-content" hidden={tab !== 'targets'}>
      <ProsecutionRoster revision={revision} />
    </div>
    <div className="review-main-content rm-prosecution-content" hidden={tab !== 'draft'}>
      <ProsecutionDraft revision={revision} />
    </div>
  </div>
}

