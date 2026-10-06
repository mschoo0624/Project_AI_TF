import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// Compile only the two data adapters in memory; all HTTP responses below are explicit fixtures.
function compile(name, imports = {}) {
  const source = readFileSync(new URL(`../src/features/review/${name}.ts`, import.meta.url), 'utf8').replaceAll('import.meta.env', '({})')
  let js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  for (const [name, url] of Object.entries(imports)) js = js.replaceAll(`'${name}'`, `'${url}'`).replaceAll(`"${name}"`, `'${url}'`)
  return `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
}
const classifierUrl = compile('classifierApi')
const api = await import(compile('api', { './classifierApi': classifierUrl }))
const classifier = await import(classifierUrl)
let calls, events, rows
const person = { military_number: '22-1', name: 'DB 대상자', service_year: 3, branch: '육군', position: '행정병' }
const submission = (id, status = 'pending') => ({ id, filename: 'fixture.pdf', military_number: '22-1', applicant_name: '문서 대상자',
  application_type: 'policy.school_student', reason_category: '각급학교 학생', status, context: {}, created_at: '2026-05-01T00:00:00Z',
  extraction: { fields: { document_title: { value: '재학증명서' } } }, verification: { result: 'insufficient', result_label: '근거 부족', checks: [], related_provisions: [] } })
beforeEach(() => {
  calls = []; events = 0
  rows = [submission('qwen_pending'), { ...submission('qwen_confirmation'), confirmation_requested: true }, submission('qwen_approved', 'approved')]
  globalThis.window = { dispatchEvent: () => { events++ } }
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, ...options })
    if (options.method) return Response.json({ ok: true })
    if (url === '/classifier-api/submissions') return Response.json(rows)
    if (url === '/api/postponements') return Response.json(rows.map((row, i) => ({ id: i + 1, person_id: '22-1', classifier_submission_id: row.id, status: row.status, category: row.application_type, reason: '학생 신청', type: 'hold' })))
    if (url === '/api/persons/22-1') return Response.json(person)
    throw new Error(`Unexpected request: ${url}`)
  }
})

test('all views share real submissions and pending confirmation counts', async () => {
  const data = await api.fetchBootstrap()
  assert.equal(data.people.length, 1)
  assert.equal(data.people[0].name, person.name)
  assert.equal(data.people[0].classification, '방침보류')
  assert.equal(data.people[0].total_hours, null)
  assert.equal(data.people[0].documents.length, 3)
  assert.equal(api.countReviewDocuments(data.queue), 2)
  assert.equal(data.queue[1].status, '확인요청')
  assert.equal(data.queue[0].file_path, '/classifier-api/submissions/qwen_pending/pdf')
  assert.equal(data.queue[0].verification.result, 'insufficient')
  assert.ok(!calls.some(c => c.url.includes('data.json')))
})

test('old records cannot populate the empty new roster or inbox', async () => {
  const original = globalThis.fetch
  rows = []
  globalThis.fetch = async (url, options) => url === '/api/postponements'
    ? Response.json([{ id: 99, person_id: 'legacy-person', classifier_submission_id: 'old-id', status: 'approved' }])
    : original(url, options)
  const data = await api.fetchBootstrap()
  assert.deepEqual(data.people, [])
  assert.deepEqual(data.queue, [])
})

test('unlinked PDFs can be verified but cannot be approved', async () => {
  const item = { ...rows[0], military_number: '' }
  await classifier.verifySubmission(item, {})
  assert.ok(calls.some(c => c.url === `/classifier-api/submissions/${item.id}/verify`))
  await assert.rejects(classifier.decide(item, 'approved'), /대상자/)
})
test('human approval stays possible despite insufficient verification', async () => {
  await api.acceptDocument('qwen_pending', {})
  assert.ok(calls.some(c => c.url === '/api/postponements/1/approve' && c.method === 'PATCH'))
  assert.equal(events, 1)
})
test('rejection and confirmation notes are persisted', async () => {
  await api.rejectDocument('qwen_pending', 'OTHER', '기간 불일치')
  assert.deepEqual(JSON.parse(calls.find(c => c.method === 'PATCH').body), { note: '기간 불일치' })
  await api.verifyDocument('qwen_confirmation', 'DOCUMENT', '발급기관 확인')
  const sent = calls.find(c => c.url.endsWith('/request-confirmation'))
  assert.deepEqual(JSON.parse(sent.body), { note: '발급기관 확인' })
})
test('verification uses persisted submission and business DB identity route', async () => {
  await classifier.verifySubmission(rows[0], { training_end: { value: '2026-05-10', source: '일정 확인' } })
  const sent = calls.find(c => c.url === '/api/postponements/verify')
  assert.equal(JSON.parse(sent.body).submission_id, rows[0].id)
  assert.equal(JSON.parse(sent.body).person_id, person.military_number)
})
test('backend failure is surfaced instead of falling back to demo records', async () => {
  globalThis.fetch = async () => new Response('Unavailable', { status: 503 })
  await assert.rejects(api.fetchBootstrap(), /503/)
})
test('incomplete decision synchronization stays retryable in the business workflow', async () => {
  const fetchOriginal = globalThis.fetch
  globalThis.fetch = async (url, options) => url === '/api/postponements'
    ? Response.json([{ id: 3, classifier_submission_id: 'qwen_approved', status: 'pending' }])
    : fetchOriginal(url, options)
  const loaded = await classifier.loadSubmissions()
  assert.equal(loaded.find(s => s.id === 'qwen_approved').status, 'pending')
})
