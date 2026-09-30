# ROLE
You are a senior backend engineer and NLP engineer. Design and implement a voice-to-task module: it records speech, transcribes it with Naver CLOVA Speech, extracts keywords and the speaker's reasoning, and adds them to the user's to-do list after human confirmation.

# GOAL
Reduce human error in manual note-taking and task entry. Voice replaces typing, and a confirmation step keeps mistakes from entering the system silently.

# CONTEXT
- Language: mainly Korean, sometimes mixed Korean-English and military/administrative terms (예비군, 전투편성, 보류, 연기, 결재, 교육시간, unit names, ranks).
- Stack: Python 3.11, FastAPI, PostgreSQL, SQLAlchemy, Pydantic v2, Alembic.
- Constraint: NO external LLM APIs (no OpenAI, etc.). The extraction step must use a local/on-premise open-source model (e.g., a Korean-capable model served via Ollama or vLLM) behind an interface.
- Constraint: the STT layer must be an abstract interface (`SpeechToTextProvider`) with a `ClovaSpeechProvider` as the default implementation. Also add a stub for a local provider (e.g., faster-whisper) so the cloud dependency can be replaced later without changing other code.
- Secrets (CLOVA Invoke URL, Secret Key) come from environment variables only. Never hardcode them or expose them to the frontend.

# PIPELINE
1. Audio input: accept an upload (mp3/wav/m4a/webm) with a max size and duration limit. Validate the type and size.
2. STT: call CLOVA Speech (`POST {INVOKE_URL}/recognizer/upload`, header `X-CLOVASPEECH-API-KEY`) with params: language `ko-KR` (option `enko` for mixed speech), completion `sync` for short clips and `async` (callback) for long ones, `wordAlignment: true`, `fullText: true`, optional `diarization`, and `boosting` with a custom vocabulary loaded from a config file.
3. Normalize the STT result into our own JSON schema (below). Keep the raw CLOVA response stored separately for audit.
4. Extraction: send the transcript to the local LLM with a strict JSON-only prompt to extract keywords, reasoning, and candidate tasks.
5. Validation: validate the LLM output with Pydantic. On failure, retry up to 2 times with the validation error, then mark the item `needs_manual_review`.
6. Human confirmation: show the user the transcript, extracted keywords, reasoning, and proposed tasks. Only after the user approves or edits them are they written to the to-do list.
7. Audit: log every step (who, when, original transcript, edits made, final tasks).

# JSON SCHEMAS
Transcript (normalized):
{
  "transcript_id": "uuid",
  "language": "ko-KR",
  "duration_sec": 0.0,
  "full_text": "string",
  "segments": [
    {"start_ms": 0, "end_ms": 0, "speaker": "string|null", "text": "string", "confidence": 0.0}
  ],
  "provider": "clova_speech",
  "created_at": "ISO-8601"
}
(Verify the field names against the real CLOVA response and adapt the mapping.)

Extraction result:
{
  "keywords": [{"term": "string", "importance": 0.0, "evidence_segment_ids": [0]}],
  "reasoning": [{"statement": "string", "reason": "string", "evidence_text": "exact quote from transcript"}],
  "tasks": [
    {
      "title": "string (short, imperative)",
      "description": "string",
      "reason": "why this task is needed, in the user's own words",
      "due_date": "ISO-8601|null",
      "priority": "low|medium|high|null",
      "confidence": 0.0,
      "source_segment_ids": [0]
    }
  ],
  "uncertain_items": ["string"]
}

# EXTRACTION RULES (put these in the LLM prompt)
- Use ONLY information present in the transcript. Never invent names, dates, numbers, or tasks.
- Every task and reasoning item must cite `evidence_text` or `source_segment_ids` from the transcript.
- If a date, person, or quantity is ambiguous or missing, set it to null and add it to `uncertain_items`.
- Resolve relative dates ("다음 주 화요일") using a reference date passed in the prompt; keep the original phrase too.
- Distinguish a task (an action to do) from a reason (why it's needed) and from a plain statement.
- Output valid JSON only, no commentary. Korean text stays in Korean.
- Low-confidence STT segments (below a configurable threshold) must be flagged, not silently trusted.

# ERROR-REDUCTION FEATURES (core of the idea)
- Show low-confidence words in the UI so the user can correct them before extraction.
- Custom vocabulary (boosting) for domain terms and a post-processing correction dictionary for frequent misrecognitions.
- Never auto-commit tasks: require explicit approval; support edit, merge, delete.
- Duplicate detection against existing to-do items (similarity check) with a warning.
- Store the original audio hash, the transcript, and the user's edits so mistakes can be traced.
- Handle STT failures gracefully: timeouts, retries with backoff, clear user-facing errors.

# API (FastAPI)
- POST /voice/transcriptions (upload audio -> transcript_id, status)
- GET  /voice/transcriptions/{id}
- POST /voice/transcriptions/{id}/extract (run keyword/reason/task extraction)
- POST /voice/transcriptions/{id}/confirm (user-approved tasks -> to-do list)
- GET/POST/PATCH/DELETE /todos
- POST /voice/callback/clova (async result, verify authenticity)

# DATABASE (PostgreSQL)
Tables: users, audio_files, transcripts, extractions, todos (with reason, source_transcript_id, status, due_date, priority), audit_logs. Include timestamps, foreign keys, and indexes. Provide Alembic migrations.

# SECURITY
- Enforce authentication and role checks in the BACKEND, not just by hiding UI elements.
- Audio may contain sensitive personal information: encrypt at rest, restrict access, define a retention/deletion policy, and never log full transcripts to plain application logs.
- Rate-limit the upload endpoint.

# DELIVERABLES
1. Short architecture summary and folder structure.
2. Working code: provider interface, CLOVA client, extraction service with prompt templates, Pydantic models, routes, DB models and migrations.
3. Unit tests with mocked STT and mocked LLM, plus tests for malformed LLM output, low-confidence segments, and ambiguous dates.
4. A small evaluation script: given a folder of audio and expected task lists, report word error rate, task precision/recall, and how often the user had to correct output.
5. README with setup, environment variables, and how to swap the STT provider.

# WORKING STYLE
- First list your assumptions and any open questions, then build in phases: (1) STT client + schema, (2) extraction, (3) confirmation flow + to-do integration, (4) auditing + tests.
- Keep functions small and typed. Explain any design choice that trades off accuracy against simplicity.
