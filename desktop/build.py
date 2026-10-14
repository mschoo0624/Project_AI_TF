"""Build a Windows demo folder. Source databases are opened read-only and backed up."""
from pathlib import Path
from datetime import datetime
from contextlib import closing
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from urllib.parse import quote
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / 'desktop'


def run(args, cwd):
    subprocess.run([str(x) for x in args], cwd=cwd, check=True,
                   env={**os.environ, 'PYTHONUTF8': '1',
                        'VITE_API_BASE_URL': '/api', 'VITE_CLASSIFIER_API_BASE_URL': '/classifier-api',
                        'VITE_RAG_API_BASE_URL': '/rag-api'})


def snapshot(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError(f'Invalid database: {source}')


def referenced_public_files(public, built):
    """Inspect emitted assets, not unused source files. Dynamic URLs need an explicit list."""
    text = '\n'.join(p.read_text(encoding='utf-8') for p in built.rglob('*')
                     if p.suffix in {'.html', '.js', '.css', '.json', '.svg'})
    manifest = json.loads((DESKTOP / 'public-assets.json').read_text(encoding='utf-8'))
    selected = set(manifest['include'])
    for file in public.rglob('*'):
        if not file.is_file():
            continue
        relative = file.relative_to(public).as_posix()
        if any(value in text for value in ('/' + relative, '/' + quote(relative),
                                          json.dumps('/' + relative, ensure_ascii=True)[1:-1])):
            selected.add(relative)
    for relative in selected:
        file = (public / relative).resolve()
        if not file.is_relative_to(public.resolve()) or not file.is_file():
            raise RuntimeError(f'Invalid public asset: {relative}')
        target = built / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    return sorted(selected)


def main():
    if sys.platform != 'win32':
        raise SystemExit('This build targets the existing Windows development PC.')
    backend = ROOT / 'backend'
    # Fail before packaging if legal data cannot be generated. Unchanged vectors are reused.
    run([sys.executable, '-m', 'scripts.preprocess'], backend / 'RAG')
    run([sys.executable, '-m', 'scripts.build_index', '--if-needed'], backend / 'RAG')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    stage = DESKTOP / '.stage' / stamp
    app = stage / 'app'
    resources = stage / 'resources'
    app.mkdir(parents=True)
    resources.mkdir()
    shutil.copy2(DESKTOP / 'loading.html', resources / 'loading.html')
    shutil.copy2(ROOT / 'frontend/src/assets/background.png', resources / 'background.png')
    shutil.copy2(ROOT / 'frontend/src/assets/appicon.png', resources / 'appicon.png')
    # Windows needs a multi-resolution ICO; preserve the source artwork's aspect ratio.
    with Image.open(ROOT / 'frontend/src/assets/appicon.png') as original:
        icon = ImageOps.pad(original.convert('RGBA'), (256, 256),
                            method=Image.Resampling.LANCZOS, color=(0, 0, 0, 0))
        icon.save(resources / 'app.ico', sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    for name in ('main.cjs', 'gateway.cjs'):
        shutil.copy2(DESKTOP / name, app / name)
    (app / 'package.json').write_text(json.dumps({'name': 'onbitnuri-demo', 'version': '1.0.0', 'main': 'main.cjs'}), encoding='utf-8')
    run(['npm.cmd', 'run', 'build', '--', '--mode', 'desktop', '--outDir', resources / 'frontend'], ROOT / 'frontend')
    public = ROOT / 'frontend/public'
    included = referenced_public_files(public, resources / 'frontend')
    excluded = [p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file() and p.relative_to(public).as_posix() not in included]
    target = resources / 'backend'
    # Package allowlist: no legacy agent, evaluation runs, source DBs, venvs or caches.
    patterns = {
        'user': ['**/*.py'],
        'classifier_agent': ['*.py', 'specifications/*.json'],
        'prediction_agent': ['*.py', 'data/*.csv', 'data/*.jsonl', 'dataset/*.csv'],
        'RAG': ['legalrag/*.py', 'ui/**/*', 'data/raw/*',
                'data/processed/laws.jsonl', 'data/index/embeddings.npy', 'data/index/index_info.json'],
    }
    for folder, globs in patterns.items():
        for pattern in globs:
            for source in (backend / folder).glob(pattern):
                if source.is_file() and '__pycache__' not in source.parts:
                    dest = target / source.relative_to(backend)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
    # PDF provisions are referenced by the rule catalog, not by the frontend bundle.
    spec = backend / 'classifier_agent/specifications'
    rules = json.loads((spec / 'verification_rules.json').read_text(encoding='utf-8'))
    def paths(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == 'path' and isinstance(v, str) and v.endswith('.pdf'):
                    yield v
                else:
                    yield from paths(v)
        elif isinstance(value, list):
            for v in value:
                yield from paths(v)
    for name in set(paths(rules)):
        source = (spec / name).resolve()
        if not source.is_relative_to(backend):
            raise RuntimeError(f'Rule PDF outside backend: {name}')
        dest = target / source.relative_to(backend)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    seed = resources / 'seed'
    snapshot(backend / 'project_ai_tf.db', seed / 'business.sqlite3')
    classifier = backend / 'classifier_agent/data'
    (seed / 'classifier').mkdir(parents=True)
    if (classifier / 'submissions.sqlite3').exists():
        snapshot(classifier / 'submissions.sqlite3', seed / 'classifier/submissions.sqlite3')
        with closing(sqlite3.connect(seed / 'classifier/submissions.sqlite3')) as db:
            for (identifier,) in db.execute('SELECT id FROM submissions'):
                if Path(identifier).name != identifier:
                    raise RuntimeError('Unsafe submission ID')
                pdf = classifier / (identifier + '.pdf')
                if not pdf.exists():
                    raise RuntimeError(f'Submission original PDF missing: {identifier}')
                shutil.copy2(pdf, seed / 'classifier' / pdf.name)
    config = {'python': str(backend / '.venv/Scripts/python.exe'), 'ollama': shutil.which('ollama'),
              'classifierModel': 'qwen3:4b-instruct', 'chatModel': 'qwen2.5:7b'}
    local = DESKTOP / 'runtime.local.json'
    if local.exists():
        config.update(json.loads(local.read_text(encoding='utf-8')))
    config['embeddingModel'] = json.loads((backend / 'RAG/data/index/index_info.json').read_text(encoding='utf-8'))['embedding_model']
    if not config['ollama'] or not Path(config['python']).is_file():
        raise RuntimeError('Python/Ollama not installed; set desktop/runtime.local.json')
    (resources / 'runtime.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    for folder in ('processed', 'index'):
        (target / 'RAG/data' / folder).mkdir(parents=True, exist_ok=True)
    warnings = []
    for name in ('processed/laws.jsonl', 'index/embeddings.npy', 'index/index_info.json'):
        if not (target / 'RAG/data' / name).exists():
            raise RuntimeError(f'RAG data missing: resources/backend/RAG/data/{name}')
    manifest = {'builtAt': stamp, 'initialState': 'snapshot of current business and classifier databases',
                'includedPublicFiles': included, 'excludedPublicFiles': excluded, 'warnings': warnings}
    (resources / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    out = ROOT / 'dist-desktop' / stamp
    run(['node', DESKTOP / 'package.cjs', app, resources, out], DESKTOP)
    folder = out / 'Onbitnuri-win32-x64'
    shutil.copy2(DESKTOP / 'RUN.txt', folder / 'RUN.txt')
    shutil.make_archive(str(out / 'Onbitnuri-demo'), 'zip', out, folder.name)
    print(json.dumps({'folder': str(folder), 'zip': str(out / 'Onbitnuri-demo.zip'), **manifest}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
