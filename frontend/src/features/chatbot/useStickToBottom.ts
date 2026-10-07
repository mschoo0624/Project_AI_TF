import { useEffect, useRef } from 'react'

// 대화창 자동 스크롤. 사용자가 맨 아래를 보고 있을 때만 새 내용(스트리밍 답변 포함)을 따라 내려가고,
// 위로 스크롤해 읽는 중이면 그 자리에 둡니다. 새 질문을 보낼 때 follow()로 다시 따라가게 합니다.
const NEAR_BOTTOM_PX = 48

export function useStickToBottom(content: unknown) {
  const ref = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  useEffect(() => {
    const log = ref.current
    if (log && stick.current) log.scrollTop = log.scrollHeight
  }, [content])

  const onScroll = () => {
    const log = ref.current
    if (log) stick.current = log.scrollHeight - log.scrollTop - log.clientHeight < NEAR_BOTTOM_PX
  }
  const follow = () => { stick.current = true }

  return { ref, onScroll, follow }
}
