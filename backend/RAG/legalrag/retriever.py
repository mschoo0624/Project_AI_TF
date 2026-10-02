"""
Hybrid retriever for the 예비군 statutes.

search(question) does:
  1. Dense search   : embed the question, cosine similarity with every article vector
  2. Keyword search : BM25 over Korean tokens (see tokenizer.py)
  3. Fusion         : weighted Reciprocal Rank Fusion of the two ranked lists
  4. Exact mentions : "시행령 제10조" in the question -> that article is always included
  5. (optional) cross-encoder rerank of the top candidates
  6. Reference expansion : add articles the top hits cite / are cited by
                           (e.g. 예비군법 제6조 <-> 시행령 "법 제6조에 따라 ...")
  7. Versions       : superseded versions are dropped; if a law has a version that is not
                      in force yet (시행 예정) it is kept only when its text actually differs.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi

from legalrag.config import Config
from legalrag.parser import Article
from legalrag.references import find_article_mentions
from legalrag.store import clean_text, load_articles, load_embedding_model, load_embeddings, search_text
from legalrag.tokenizer import tokenize
from legalrag.utils import get_logger

logger = get_logger(__name__)

CURRENT, UPCOMING, SUPERSEDED = "현행", "시행 예정", "종전"


@dataclass
class Hit:
    article: Article
    score: float
    status: str                     # 현행 / 시행 예정
    via: str = "검색"                # 검색 / 조문 지정 / 참조
    detail: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        a = self.article
        return {
            "id": a.id,
            "title": a.display_name,
            "law_name": a.law_name,
            "law_type": a.law_type,
            "promulgation_no": a.promulgation_no,
            "effective_date": a.effective_date,
            "status": self.status,
            "chapter": a.chapter,
            "article_no": a.article_no,
            "text": a.text,
            "score": round(self.score, 4),
            "via": self.via,
            "detail": {k: round(v, 4) for k, v in self.detail.items()},
        }


class Retriever:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.articles = load_articles(cfg.processed_file)
        self.embeddings = load_embeddings(cfg, self.articles)
        logger.info("Loading embedding model %s ...", cfg.embedding_model)
        self.model = load_embedding_model(cfg.embedding_model)
        self.bm25 = BM25Okapi([tokenize(search_text(a)) for a in self.articles])
        self.status = self._version_status()
        self.by_key: Dict[Tuple[str, str, bool], List[int]] = {}
        for i, a in enumerate(self.articles):
            self.by_key.setdefault((a.law_name, a.article_no, a.is_addendum), []).append(i)
        self.law_names = sorted({a.law_name for a in self.articles})
        self.cited_by = self._reverse_references()
        self.reranker = None
        if cfg.enable_rerank:
            from sentence_transformers import CrossEncoder

            logger.info("Loading reranker %s ...", cfg.rerank_model)
            self.reranker = CrossEncoder(cfg.rerank_model)
        logger.info("Retriever ready: %d articles from %d laws", len(self.articles), len(self.law_names))

    # ------------------------------------------------------------------ versions
    def reference_date(self) -> str:
        return self.cfg.reference_date or dt.date.today().isoformat()

    def _version_status(self) -> List[str]:
        """For each law: newest version already in force = 현행, later ones = 시행 예정, older = 종전."""
        today = self.reference_date()
        versions: Dict[str, set] = {}
        for a in self.articles:
            versions.setdefault(a.law_name, set()).add((a.effective_date, a.promulgation_no))
        current: Dict[str, Tuple[str, str]] = {}
        for law, vs in versions.items():
            in_force = [v for v in vs if v[0] <= today]
            current[law] = max(in_force) if in_force else min(vs)
        out = []
        for a in self.articles:
            v = (a.effective_date, a.promulgation_no)
            cur = current[a.law_name]
            out.append(CURRENT if v == cur else (UPCOMING if v > cur else SUPERSEDED))
        return out

    def _resolve(self, law: Optional[str], article_no: str, prefer_version: Optional[str] = None) -> List[int]:
        """Article indices for (law, 제N조), current (and upcoming) versions only."""
        laws = [law] if law else self.law_names
        idx = [i for name in laws for i in self.by_key.get((name, article_no, False), [])
               if self.status[i] != SUPERSEDED]
        if prefer_version:
            # a reference inside one version of a law points to that same version
            same = [i for i in idx if self.articles[i].promulgation_no == prefer_version]
            if same:
                return same
        return idx

    def _reverse_references(self) -> Dict[int, List[int]]:
        cited_by: Dict[int, List[int]] = {}
        for i, a in enumerate(self.articles):
            for ref in a.refs:
                prefer = a.promulgation_no if ref["law"] == a.law_name else None
                for j in self._resolve(ref["law"], ref["article"], prefer):
                    cited_by.setdefault(j, []).append(i)
        return cited_by

    # ------------------------------------------------------------------ search
    def _searchable(self, i: int) -> bool:
        a = self.articles[i]
        if self.status[i] == SUPERSEDED or a.is_deleted:
            return False
        return self.cfg.include_addenda or not a.is_addendum

    def search(self, question: str, top_k: Optional[int] = None) -> List[Hit]:
        cfg = self.cfg
        top_k = top_k or cfg.top_k # 관련 조문 수
        n_cand = max(cfg.candidates, top_k)

        # 1) dense : 각 질문과 유사도 점수 반환
        q = self.model.encode([question], normalize_embeddings=True)[0]
        dense = self.embeddings @ q
        # 2) keyword : BM25 점수 반환
        bm25 = self.bm25.get_scores(tokenize(question))

        ok = [i for i in range(len(self.articles)) if self._searchable(i)]
        dense_rank = sorted(ok, key=lambda i: -dense[i])[:n_cand]
        bm25_rank = [i for i in sorted(ok, key=lambda i: -bm25[i]) if bm25[i] > 0][:n_cand]

        # 3) weighted reciprocal rank fusion
        fused: Dict[int, float] = {}
        for w, ranking in ((cfg.dense_weight, dense_rank), (cfg.bm25_weight, bm25_rank)):
            for r, i in enumerate(ranking, start=1):
                fused[i] = fused.get(i, 0.0) + w / (cfg.rrf_k + r)
        max_possible = (cfg.dense_weight + cfg.bm25_weight) / (cfg.rrf_k + 1)
        scores = {i: s / max_possible for i, s in fused.items()}  # 1.0 = ranked first by both

        hits: Dict[int, Hit] = {}
        for i, s in scores.items():
            hits[i] = Hit(self.articles[i], s, self.status[i], "검색",
                          {"dense": float(dense[i]), "bm25": float(bm25[i])})

        # 4) explicitly mentioned articles always come first
        for mention in find_article_mentions(question, self.law_names):
            for i in self._resolve(mention["law"], mention["article"]):
                hits[i] = Hit(self.articles[i], 1.0 + scores.get(i, 0.0), self.status[i], "조문 지정",
                              {"dense": float(dense[i]), "bm25": float(bm25[i])})

        ranked = sorted(hits.values(), key=lambda h: -h.score)

        # 5) optional cross-encoder rerank
        if self.reranker is not None:
            pinned = [h for h in ranked if h.via == "조문 지정"]
            pool = [h for h in ranked if h.via != "조문 지정"][: max(20, top_k * 3)]
            if pool:
                ce = self.reranker.predict([(question, search_text(h.article)) for h in pool])
                ce = 1 / (1 + np.exp(-np.asarray(ce, dtype="float64")))  # sigmoid -> 0..1
                for h, s in zip(pool, ce):
                    h.detail["rerank"] = float(s)
                    h.score = 0.3 * h.score + 0.7 * float(s)
                pool.sort(key=lambda h: -h.score)
            ranked = pinned + pool

        ranked = self._drop_duplicate_versions(ranked)
        top = ranked[:top_k]

        # 6) reference expansion (법 <-> 시행령 <-> 시행규칙)
        if cfg.expand_references and cfg.max_reference_hits > 0:
            top += self._expand(top, scores, dense)
        return top

    def _drop_duplicate_versions(self, ranked: List[Hit]) -> List[Hit]:
        """Keep an upcoming version only if its text differs from the current one."""
        current_text = {}
        for h in ranked:
            if h.status == CURRENT:
                a = h.article
                current_text[(a.law_name, a.article_no, a.is_addendum)] = clean_text(a.text)
        out = []
        for h in ranked:
            a = h.article
            if h.status == UPCOMING:
                key = (a.law_name, a.article_no, a.is_addendum)
                if a.is_addendum:
                    pass  # addenda of different versions are different texts anyway
                elif key in current_text and current_text[key] == clean_text(a.text):
                    continue
                elif key not in current_text:
                    cur_idx = [i for i in self.by_key.get(key, []) if self.status[i] == CURRENT]
                    if cur_idx and clean_text(self.articles[cur_idx[0]].text) == clean_text(a.text):
                        continue
            out.append(h)
        return out

    def _expand(self, top: List[Hit], scores: Dict[int, float], dense: np.ndarray) -> List[Hit]:
        index_of = {a.id: i for i, a in enumerate(self.articles)}
        have = {h.article.id for h in top}
        cand: Dict[int, float] = {}
        for h in top:
            src = index_of[h.article.id]
            linked = []
            for ref in h.article.refs:  # articles this hit cites
                prefer = h.article.promulgation_no if ref["law"] == h.article.law_name else None
                linked += self._resolve(ref["law"], ref["article"], prefer)
            linked += self.cited_by.get(src, [])  # articles citing this hit
            for j in linked:
                if self.articles[j].id in have or not self._searchable(j):
                    continue
                # prefer linked articles that are also relevant to the question
                cand[j] = max(cand.get(j, 0.0), float(dense[j]) + scores.get(j, 0.0))
        best = sorted(cand, key=lambda j: -cand[j])
        out = []
        for j in best:
            hit = Hit(self.articles[j], scores.get(j, 0.0), self.status[j], "참조", {"dense": float(dense[j])})
            if self._drop_duplicate_versions([hit]):
                out.append(hit)
            if len(out) >= self.cfg.max_reference_hits:
                break
        return out
