"""Record completed writes without changing business endpoints or retaining uploads."""
import json
import logging
from collections import Counter
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from user.app.database import SessionLocal
from user.app.worklog.events import build_event, capture_state, match_operation


logger = logging.getLogger(__name__)
JSON_LIMIT = 8 * 1024 * 1024


def _json(content):
    try:
        return json.loads(content) if content else {}
    except (UnicodeDecodeError, ValueError):
        return {}


class WorkLogMiddleware:
    def __init__(self, app, session_factory=SessionLocal, writer=None):
        self.app = app
        self.session_factory = session_factory
        self.writer = writer
        self.run_id = uuid4().hex
        self.pending_decisions = Counter()

    async def __call__(self, scope, receive, send):
        operation = match_operation(scope.get('method', ''), scope.get('path', '')) if scope['type'] == 'http' else None
        if operation is None:
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get('headers', [])}
        buffered, body, size = [], [], 0
        if b'application/json' in headers.get(b'content-type', b''):
            while True:
                message = await receive()
                buffered.append(message)
                chunk = message.get('body', b'')
                size += len(chunk)
                if size <= JSON_LIMIT:
                    body.append(chunk)
                if not message.get('more_body') or size > JSON_LIMIT:
                    break
        payload = _json(b''.join(body)) if size <= JSON_LIMIT else {}
        authorization = headers.get(b'authorization', b'').decode('latin1')
        try:
            before = await run_in_threadpool(capture_state, self.session_factory, operation, payload, None, authorization)
        except Exception:
            logger.exception('Could not prepare daily-log snapshot for %s', operation.action)
            before = None

        async def replay():
            return buffered.pop(0) if buffered else await receive()

        response_body, response_size, status = [], 0, 0
        parent_submission = before.get('decision_submission_id') if before else None
        if parent_submission:
            self.pending_decisions[parent_submission] += 1

        async def record_and_send(message):
            nonlocal status, response_size
            if message['type'] == 'http.response.start':
                status = message['status']
            elif message['type'] == 'http.response.body' and before is not None and 200 <= status < 300:
                chunk = message.get('body', b'')
                response_size += len(chunk)
                if response_size <= JSON_LIMIT:
                    response_body.append(chunk)
                if not message.get('more_body'):
                    if response_size > JSON_LIMIT:
                        logger.error('Daily-log response exceeded capture limit for %s', operation.action)
                    else:
                        try:
                            response = _json(b''.join(response_body))
                            after = await run_in_threadpool(capture_state, self.session_factory, operation, payload, response)
                            nested_decision = operation.action == 'document_decision' and self.pending_decisions[operation.params.get('id')]
                            event = None if nested_decision else build_event(operation, before, after, payload, response)
                            if event:
                                if event['dedupe_key']:
                                    event['dedupe_key'] = f"{self.run_id}:{event['dedupe_key']}"
                                if self.writer is None:
                                    from user.app.worklog.repository import append_event
                                    writer = append_event
                                else:
                                    writer = self.writer
                                await run_in_threadpool(writer, **event)
                        except Exception:
                            logger.exception('Daily-log recording failed after successful %s', operation.action)
            await send(message)

        try:
            await self.app(scope, replay, record_and_send)
        finally:
            if parent_submission:
                self.pending_decisions[parent_submission] -= 1
                if not self.pending_decisions[parent_submission]:
                    del self.pending_decisions[parent_submission]
