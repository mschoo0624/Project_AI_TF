const ZERO_HOUR_STATES = new Set(['무단불참', '연기', '보류'])
const TYPE_II_AUTO_STATES = new Set(['이수', '참석'])

export function buildTrainingHourPresets(sessions) {
  let totalHours = 0
  return [...sessions]
    .sort((left, right) => left.day_number - right.day_number)
    .flatMap(session => {
      totalHours += session.credited_hours
      return totalHours > 0
        ? [{ day_number: session.day_number, hours: totalHours, label: `${totalHours}시간 · ${session.day_number}일차까지` }]
        : []
    })
}

export function resolveTrainingHours({
  isTypeII,
  result,
  eventHours,
  requiredHours,
  remainingHours,
  enteredHours,
}) {
  if (ZERO_HOUR_STATES.has(result)) {
    return { hours: 0, automatic: true, capped: false, limitUnknown: false }
  }
  if (isTypeII && TYPE_II_AUTO_STATES.has(result)) {
    if (remainingHours === null || requiredHours === null) {
      return { hours: eventHours, automatic: true, capped: false, limitUnknown: true }
    }
    const hours = Math.min(eventHours, requiredHours, remainingHours)
    return { hours, automatic: true, capped: hours < eventHours, limitUnknown: false }
  }
  return { hours: enteredHours, automatic: false, capped: false, limitUnknown: false }
}

export function bulkHourExclusionReason(hours, eventHours, remainingHours) {
  if (remainingHours === null) return 'unknown_remaining'
  if (hours > eventHours) return 'event_capacity'
  if (hours > remainingHours) return 'annual_allowance'
  return null
}
