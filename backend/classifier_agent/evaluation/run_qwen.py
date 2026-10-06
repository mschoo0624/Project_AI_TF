"""Standalone Qwen evaluation with fixed PDF inputs and gold."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

from evaluation_common import score, summarize, build_messages

BASE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:11434/api/'


def api(route, body=None, timeout=120):
    req = urllib.request.Request(URL+route, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='qwen3:4b-instruct')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((BASE/'qwen_cases.json').read_text(encoding='utf-8'))
    fields = json.loads((BASE/'qwen_common_fields.json').read_text(encoding='utf-8'))['fields']
    tags = api('tags')
    installed = next(m for m in tags['models'] if m['name'] == args.model)
    show = api('show', {'model': args.model})
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ['cases.json', 'common_fields.json']:
        (args.output/name).write_bytes((BASE/('qwen_'+name)).read_bytes())
    (args.output/'runner_source.py.txt').write_bytes(Path(__file__).read_bytes())
    (args.output/'shared_scorer.py.txt').write_bytes(Path(__file__).with_name('evaluation_common.py').read_bytes())
    (args.output/'ollama_show.json').write_text(json.dumps(show, ensure_ascii=False, indent=2), encoding='utf-8')
    opts = {'temperature': 0, 'seed': 0, 'repeat_penalty': 1, 'num_ctx': 8192,
            'num_predict': 512, 'num_thread': 6, 'num_gpu': 0}
    metadata = {'started_at': datetime.now(timezone.utc).isoformat(), 'model': installed,
                'ollama_version': api('version'), 'options': opts, 'think': False,
                'keep_alive': 0, 'json_constraint': False,
                'comparison': 'Fixed PDF texts, gold and scoring; independent requests.',
                'cases_sha256': hashlib.sha256((args.output/'cases.json').read_bytes()).hexdigest(),
                'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'shared_scorer_sha256': hashlib.sha256(Path(__file__).with_name('evaluation_common.py').read_bytes()).hexdigest(),
                'timing': 'seconds = client wall time minus server load_duration; wall_seconds includes per-document cold model load. HTTP timeout 120s; no retry.',
                'timeout_seconds': 120}
    (args.output/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    # Start with an unloaded model, and unload after each request. Never pass past history/context.
    api('generate', {'model': args.model, 'keep_alive': 0, 'stream': False})
    results = []
    for i, case in enumerate(cases, 1):
        messages = build_messages(case, fields)
        request = {'model': args.model, 'messages': messages, 'think': False,
                   'stream': False, 'keep_alive': 0, 'options': opts}
        start = time.perf_counter()
        try:
            response = api('chat', request)
            error = None
        except Exception as exc:
            response, error = {}, f'{type(exc).__name__}: {exc}'
        wall = time.perf_counter()-start
        raw = response.get('message', {}).get('content', '')
        load_seconds = response.get('load_duration', 0)/1e9
        result = {'id': case['id'], 'messages': messages, 'request': request,
                  'raw_response': raw, 'server_response': response, 'error': error,
                  'input_tokens': response.get('prompt_eval_count', 0),
                  'output_tokens': response.get('eval_count', 0),
                  'seconds': max(wall-load_seconds, 0.000001), 'wall_seconds': wall,
                  'load_seconds': load_seconds,
                  'hit_token_limit': response.get('done_reason') == 'length',
                  'hit_time_limit': error is not None and wall >= 119,
                  'score': score(case, raw)}
        results.append(result)
        with (args.output/'results.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(result, ensure_ascii=False)+'\n')
        print(f'{i}/{len(cases)} {case["id"]}: pass={result["score"]["case_pass"]} '
              f'{result["seconds"]:.1f}s + load {load_seconds:.1f}s, tokens={result["output_tokens"]}, error={error}', flush=True)
        if error:
            # A timed-out server may still be running. Stop instead of queueing new work.
            raise RuntimeError(error)
    summary = summarize(results)
    summary['mean_wall_seconds'] = sum(r['wall_seconds'] for r in results)/len(results)
    summary['mean_load_seconds'] = sum(r['load_seconds'] for r in results)/len(results)
    metadata['finished_at'] = datetime.now(timezone.utc).isoformat()
    metadata['post_run_processes'] = api('ps')
    (args.output/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
