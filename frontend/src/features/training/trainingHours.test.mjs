import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildTrainingHourPresets,
  bulkHourExclusionReason,
  resolveTrainingHours,
} from './trainingHours.mjs'

test('hour presets follow configured sessions and cumulative totals', () => {
  const presetsFor = hours => buildTrainingHourPresets(
    hours.map((credited_hours, index) => ({ day_number: index + 1, credited_hours })),
  )

  assert.deepEqual(presetsFor([12, 8, 8]).map(preset => preset.label), [
    '12시간 · 1일차까지',
    '20시간 · 2일차까지',
    '28시간 · 3일차까지',
  ])
  assert.deepEqual(presetsFor([8, 8, 8, 8]).map(preset => preset.hours), [8, 16, 24, 32])
  assert.deepEqual(presetsFor([8]).map(preset => preset.hours), [8])
  assert.deepEqual(presetsFor([6, 6]).map(preset => preset.hours), [6, 12])
})

test('Type II completion hours respect enlisted, Air Force, cadre, and remaining-hour limits', () => {
  const resolved = [
    { requiredHours: 32, remainingHours: 32 },
    { requiredHours: 28, remainingHours: 28 },
    { requiredHours: 28, remainingHours: 32 },
    { requiredHours: 32, remainingHours: 32 },
    { requiredHours: 32, remainingHours: 20 },
    { requiredHours: 32, remainingHours: 16 },
    { requiredHours: 32, remainingHours: 4 },
  ].map(({ requiredHours, remainingHours }) => resolveTrainingHours({
    isTypeII: true,
    result: '이수',
    eventHours: 32,
    requiredHours,
    remainingHours,
    enteredHours: 8,
  }))

  assert.deepEqual(resolved.map(result => result.hours), [32, 28, 28, 32, 20, 16, 4])
  assert.deepEqual(resolved.map(result => result.capped), [false, true, true, false, true, true, true])
})

test('Type II automatic hours are not applied when an individual limit is unknown', () => {
  const resolved = resolveTrainingHours({
    isTypeII: true,
    result: '참석',
    eventHours: 32,
    requiredHours: null,
    remainingHours: 32,
    enteredHours: 8,
  })

  assert.equal(resolved.limitUnknown, true)
})

test('bulk presets above event or personal allowance are excluded', () => {
  assert.equal(bulkHourExclusionReason(32, 32, 20), 'annual_allowance')
  assert.equal(bulkHourExclusionReason(36, 32, 40), 'event_capacity')
  assert.equal(bulkHourExclusionReason(8, 32, null), 'unknown_remaining')
  assert.equal(bulkHourExclusionReason(20, 32, 20), null)
})

test('partial manual hours are preserved and zero-hour states stay zero', () => {
  assert.equal(resolveTrainingHours({
    isTypeII: false,
    result: '참석',
    eventHours: 28,
    requiredHours: 28,
    remainingHours: 12,
    enteredHours: 5,
  }).hours, 5)
  assert.equal(resolveTrainingHours({
    isTypeII: false,
    result: '무단불참',
    eventHours: 28,
    requiredHours: 28,
    remainingHours: 12,
    enteredHours: 5,
  }).hours, 0)
})
