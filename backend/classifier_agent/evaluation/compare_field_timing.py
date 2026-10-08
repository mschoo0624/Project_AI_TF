"""One real PDF, batch versus individual fields; no business/submission writes."""
import csv
import argparse
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.request
from unittest.mock import patch

from backend.classifier_agent import extraction as ex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-only', action='store_true')
    parser.add_argument('--pdf', default='frontend/public/pdfs/홍길동.pdf')
    parser.add_argument('--application-type', default='postponement.illness')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    path = root/args.pdf
    out = Path(__file__).parent/'runs'/('field_timing_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    start = time.perf_counter()
    pdf = ex.extract_pdf(path)
    pdf_seconds = time.perf_counter()-start
    assert len(pdf['pages']) == 1
    page = pdf['pages'][0]
    app, fields = ex.selected_fields(args.application_type)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    titles = any(ex.compact(s['text']) in ('진단서','응시표','재학증명서','재직증명서') for s in ex.sources_for(page))
    fields = {k:v for k,v in fields.items() if k != 'document_title' or not titles}
    count = len(fields)
    save('pdf.json', pdf)
    save('manifest.json', {'file':str(path.relative_to(root)), 'sha256':digest,
        'extraction_code_sha256':hashlib.sha256(Path(ex.__file__).read_bytes()).hexdigest(),
        'model':os.getenv('CLASSIFIER_MODEL','qwen3:4b-instruct'), 'fields':fields,
        'pdf_seconds':pdf_seconds, 'application_type':args.application_type,
        'order':'warmup, batch' if args.batch_only else 'warmup, batch, single fields in specification order',
        'repetitions':1, 'retries':0, 'history':False,
        'note':'Same complete page sources every call. Model kept loaded; Ollama prefix cache may apply. Output limits follow production. Individual times include repeated input processing; not per-field shares of batch time.'})
    base = os.getenv('OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
    body = {'model':os.getenv('CLASSIFIER_MODEL','qwen3:4b-instruct'), 'keep_alive':'5m',
            'stream':False, 'options':{'num_ctx':16384}}
    start = time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request(base+'/api/generate',
            data=json.dumps(body).encode(), headers={'Content-Type':'application/json'}), timeout=180) as response:
        save('warmup.json', {'response':json.load(response), 'wall_seconds':time.perf_counter()-start})
    with urllib.request.urlopen(base+'/api/ps',timeout=10) as response:
        save('runtime.json',json.load(response))
    print('RESULT_DIR='+str(out), flush=True)
    results = []
    actual_urlopen = urllib.request.urlopen
    jobs = [('batch',fields)] + ([] if args.batch_only else [('single',{k:v}) for k,v in fields.items()])
    for index, (mode, requested) in enumerate(jobs):
        chunks, messages = ex.model_batches(requested, app, None, page)
        assert len(chunks) == 1
        inputs = messages(chunks[0])
        record = {'index':index,'mode':mode,'fields':list(requested),
                  'input_bytes':sum(len(m['content'].encode()) for m in inputs)}
        def capture(request, timeout):
            record['request'] = json.loads(request.data)
            with actual_urlopen(request, timeout=timeout) as response:
                data = response.read()
            record['ollama_response'] = json.loads(data)
            return io.BytesIO(data)
        print(f'START {index}/{count} {mode} '+','.join(requested), flush=True)
        save(f'{index:02d}.json',record | {'messages':inputs})
        start = time.perf_counter()
        try:
            with patch.object(ex.urllib.request,'urlopen',capture):
                raw = ex.ask_qwen(inputs)
            record['wall_seconds'] = round(time.perf_counter()-start,3)
            obj = json.loads(raw)
            allowed = {s['id']:s for s in chunks[0]}
            record['validated'] = {k:ex.validate_role(k,
                ex.resolve_field(obj.get(k), spec, page, digest, allowed),allowed)
                for k,spec in requested.items()}
        except Exception as exc:
            record.setdefault('wall_seconds',round(time.perf_counter()-start,3))
            record['error'] = type(exc).__name__+': '+str(exc)
        save(f'{index:02d}.json',record)
        metric = record.get('ollama_response',{})
        row = {'mode':mode,'field':','.join(requested) if mode=='single' else f'ALL_{count}',
               'label':next(iter(requested.values()))['label'] if mode=='single' else f'{count}개 일괄',
               'wall_seconds':record['wall_seconds'],
               **{k:metric.get(k) for k in ('prompt_eval_count','eval_count')},
               **{k+'_seconds':round(metric.get(k,0)/1e9,3) for k in ('load_duration','prompt_eval_duration','eval_duration')},
               'status':','.join(v['status'] for v in record.get('validated',{}).values()),
               'error':record.get('error','')}
        results.append(row)
        save('summary.json',results)
        with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(row)); writer.writeheader(); writer.writerows(results)
        print(f"DONE {index}/{count} seconds={row['wall_seconds']} output_tokens={row['eval_count']} error={row['error']}",flush=True)
        if record.get('error'):
            # A timed-out request may still run remotely: do not queue more work.
            break
    print('COMPLETE',flush=True)


if __name__ == '__main__':
    main()
