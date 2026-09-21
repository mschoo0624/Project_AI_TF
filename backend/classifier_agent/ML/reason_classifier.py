"""
Stage 2: 사유 분류기 (TF-IDF + scikit-learn).

extraction.py 의 record_reason_example() 이 reason_examples.jsonl 에 누적하는
{text, summary, label} 데이터를 학습에 사용합니다. 한국어는 교착어라 단어 단위
TF-IDF 가 형태소 분석기 없이는 잘 안 먹히므로, 형태소 분석기 의존 없이도 어느
정도 통하는 char n-gram(analyzer="char_wb") 방식을 씁니다.

pip install scikit-learn joblib
"""
import json
import re
from collections import Counter
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

try:
    from . import extraction
except ImportError:
    import extraction

REASON_EXAMPLES_PATH = Path(__file__).with_name("reason_examples.jsonl")
MODEL_PATH = Path(__file__).with_name("reason_classifier.joblib")

# 고정 카테고리. 사유확인서 표본(import-pdfs) 관측값 + 진단서에서 온 질병.
CATEGORIES = ["천재지변", "시험응시", "가족경조사", "국외체류", "질병", "기타"]

TARGET_EXAMPLES_PER_CLASS = 20  # 100~200건 목표 / 5개 카테고리

def load_labeled_examples() -> tuple[list[str], list[str]]:
    """레이블이 붙은 예시만 로드. (texts, labels)"""
    if not REASON_EXAMPLES_PATH.exists():
        return [], []

    texts, labels = [], []
    with REASON_EXAMPLES_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("label"):
                texts.append(entry["text"])
                labels.append(entry["label"])
    return texts, labels


def label_counts() -> Counter:
    _, labels = load_labeled_examples()
    return Counter(labels)


def _already_imported_files() -> set[str]:
    if not REASON_EXAMPLES_PATH.exists():
        return set()
    files = set()
    with REASON_EXAMPLES_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                files.add(json.loads(line).get("source_file"))
    return files


# 사유확인서는 '사유 구분'(=정답 라벨)과 '사유 내용'을 이미 구조화된 텍스트로 가지고 있어서,
# LLM 없이 정규식으로만 바로 파싱해 정확한 학습 데이터를 모을 수 있습니다.
REASON_FIELD_RE = re.compile(r"사유\s*구분\s*\n(.+?)\n사유\s*내용\s*\n(.+?)\n해당\s*기간", re.DOTALL)


def parse_reason_confirmation(doc_text: str) -> tuple[str, str] | None:
    """사유확인서 텍스트에서 (카테고리, 사유 내용)을 추출. 없으면 None."""
    match = REASON_FIELD_RE.search(doc_text)
    if not match:
        return None
    category, content = match.groups()
    return category.strip(), content.strip()


def import_reason_pdfs(folder: str | Path) -> int:
    """폴더 안 사유확인서 PDF를 파싱해 reason_examples.jsonl 에 누적. 이미 가져온 파일은 건너뜁."""
    already = _already_imported_files()
    imported = 0
    for path in sorted(Path(folder).glob("*.pdf")):
        if path.name in already:
            continue
        text = extraction.extract_text_from_pdf(path)
        parsed = parse_reason_confirmation(text)
        if not parsed:
            continue
        category, content = parsed
        extraction.record_reason_example(content, content, category, source_file=path.name)
        imported += 1
    return imported


# 진단서에는 '사유 구분'이 없지만, '(주 질병·부상)' 다음 줄이 곧 질병명이자 질병 카테고리의 ground truth.
DIAGNOSIS_FIELD_RE = re.compile(r"\(주\s*질병[·ㆍ ]*부상\)\s*\n(.+?)\n")


def parse_diagnosis(doc_text: str) -> str | None:
    """진단서 텍스트에서 주 질병명을 추출. 없으면 None."""
    match = DIAGNOSIS_FIELD_RE.search(doc_text)
    return match.group(1).strip() if match else None


def import_diagnosis_pdfs(folder: str | Path) -> int:
    """폴더 안 진단서 PDF에서 질병명을 추출해 '질병' 라벨로 누적. 이미 가져온 파일은 건너뜀."""
    already = _already_imported_files()
    imported = 0
    for path in sorted(Path(folder).glob("*.pdf")):
        if path.name in already:
            continue
        text = extraction.extract_text_from_pdf(path)
        diagnosis = parse_diagnosis(text)
        if not diagnosis:
            continue
        extraction.record_reason_example(diagnosis, diagnosis, "질병", source_file=path.name)
        imported += 1
    return imported


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def train() -> Pipeline:
    texts, labels = load_labeled_examples()
    if len(texts) < 10:
        raise RuntimeError(
            f"학습 데이터가 너무 적습니다 ({len(texts)}건). "
            f"extraction.py --reason-pdf ... --label ... 로 최소 10건 이상 쌓으세요."
        )

    pipeline = build_pipeline()
    pipeline.fit(texts, labels)
    joblib.dump(pipeline, MODEL_PATH)
    return pipeline


def evaluate() -> dict:
    """데이터가 적으므로 K-fold 교차검증으로 정확도를 추정 (홀드아웃 대신)."""
    texts, labels = load_labeled_examples()
    counts = Counter(labels)
    n_splits = min(5, min(counts.values())) if counts else 0
    if n_splits < 2:
        raise RuntimeError("교차검증을 하기엔 각 카테고리별 예시가 너무 적습니다 (최소 2건/카테고리 필요).")

    pipeline = build_pipeline()
    preds = cross_val_predict(pipeline, texts, labels, cv=StratifiedKFold(n_splits=n_splits))
    accuracy = sum(p == y for p, y in zip(preds, labels)) / len(labels)
    return {"accuracy": accuracy, "n_examples": len(labels), "n_splits": n_splits, "label_counts": dict(counts)}


def load_model() -> Pipeline:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("학습된 모델이 없습니다. 먼저 `python reason_classifier.py train` 을 실행하세요.")
    return joblib.load(MODEL_PATH)


def predict(text: str) -> str:
    pipeline = load_model()
    return pipeline.predict([text])[0]


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Stage 2: TF-IDF 사유 분류기")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stats", help="레이블별 누적 예시 수 확인")
    sub.add_parser("train", help="누적된 reason_examples.jsonl 로 모델 학습")
    sub.add_parser("evaluate", help="교차검증으로 정확도 추정")
    import_parser = sub.add_parser("import-pdfs", help="사유확인서 PDF 폴더에서 정답 라벨을 자동 추출해 누적")
    import_parser.add_argument("folder", help="사유확인서 PDF가 있는 폴더")
    import_diag_parser = sub.add_parser("import-diagnosis-pdfs", help="진단서 PDF 폴더에서 '질병' 카테고리를 자동 추출해 누적")
    import_diag_parser.add_argument("folder", help="진단서 PDF가 있는 폴더")
    predict_parser = sub.add_parser("predict", help="텍스트를 분류")
    predict_parser.add_argument("text", help="분류할 사유 텍스트")

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.command == "stats":
        counts = label_counts()
        total = sum(counts.values())
        print(f"누적 레이블 예시: {total}건 (목표 {TARGET_EXAMPLES_PER_CLASS * len(CATEGORIES)}건)")
        for category in CATEGORIES:
            n = counts.get(category, 0)
            print(f"  {category}: {n}/{TARGET_EXAMPLES_PER_CLASS}")
        unknown = set(counts) - set(CATEGORIES)
        if unknown:
            print(f"  (미등록 카테고리 발견: {sorted(unknown)})")

    elif args.command == "train":
        train()
        print(f"모델 저장 완료: {MODEL_PATH}")

    elif args.command == "evaluate":
        result = evaluate()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "import-pdfs":
        count = import_reason_pdfs(args.folder)
        print(f"{count}건 새로 누적함 (이미 있던 파일은 건너뜀)")

    elif args.command == "import-diagnosis-pdfs":
        count = import_diagnosis_pdfs(args.folder)
        print(f"{count}건 새로 누적함 (질병, 이미 있던 파일은 건너뜀)")

    elif args.command == "predict":
        label = predict(args.text)
        print(label)
