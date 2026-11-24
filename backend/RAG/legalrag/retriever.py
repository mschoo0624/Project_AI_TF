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

from .chunker import Chunk, build_chunks
from .config import Config
from .parser import Article
from .references import find_article_mentions
from .store import chunk_search_text, clean_text, load_articles, load_embedding_model, load_embeddings
from .tokenizer import tokenize
from .utils import get_logger

logger = get_logger(__name__)

CURRENT, UPCOMING, SUPERSEDED = "현행", "시행 예정", "종전"


def _law_rank(law_type: str) -> int:
    """Lower = higher authority. Python's sort is stable, so relevance order is kept inside one level."""
    if "훈령" in law_type or "예규" in law_type:
        return 3
    if "법률" in law_type:
        return 0
    if "대통령령" in law_type:
        return 1
    return 2   # 부령 (시행규칙 등)


@dataclass
class Hit:
    article: Article
    score: float
    status: str                     # 현행 / 시행 예정
    via: str = "검색"                # 검색 / 조문 지정 / 참조
    detail: Dict[str, float] = field(default_factory=dict)
    chunks: List[Chunk] = field(default_factory=list)   # selected passages (항), in article order

    def passage_text(self) -> str:
        """Text of the selected passages only; '(중략)' / '(이하 생략)' mark what was left out."""
        cs = sorted(self.chunks, key=lambda c: c.order)
        if not cs:
            return self.article.text
        if cs[0].is_whole:
            return cs[0].text
        out: List[str] = []
        prev = -1
        for c in cs:
            if c.order != prev + 1:
                out.append("(중략)")
            out.append(c.text)
            prev = c.order
        if prev + 1 < cs[0].total:
            out.append("(이하 생략)")
        return "\n".join(out)

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
            "text": self.passage_text(),
            "passages": [c.label for c in self.chunks if c.label],
            "score": round(self.score, 4),
            "via": self.via,
            "detail": {k: round(v, 4) for k, v in self.detail.items()},
        }


class Retriever:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.articles = load_articles(cfg.processed_file)
        self.chunks = build_chunks(self.articles)
        self.chunk_article = np.array([c.article_idx for c in self.chunks], dtype=int)
        self.chunks_of: Dict[int, List[int]] = {}
        for ci, c in enumerate(self.chunks):
            self.chunks_of.setdefault(c.article_idx, []).append(ci)
        self.embeddings = load_embeddings(cfg, self.articles, self.chunks)
        logger.info("Loading embedding model %s ...", cfg.embedding_model)
        self.model = load_embedding_model(cfg.embedding_model)
        self.bm25 = BM25Okapi([
            tokenize(chunk_search_text(self.articles[c.article_idx], c.label, c.text)) for c in self.chunks
        ])
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
        logger.info("Retriever ready: %d articles (%d passages) from %d laws",
                    len(self.articles), len(self.chunks), len(self.law_names))

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

    def _select(self, i: int, cscores: Dict[int, float], dense_c: np.ndarray, limit: int) -> List[Chunk]:
        """Pick the most relevant passages (항) of article i, returned in article order."""
        cis = self.chunks_of[i]
        if len(cis) == 1:
            return [self.chunks[cis[0]]]
        ranked = sorted(cis, key=lambda ci: (cscores.get(ci, 0.0), float(dense_c[ci])), reverse=True)
        best = ranked[0]
        chosen = [best]
        top_score = cscores.get(best, 0.0)
        for ci in ranked[1:limit]:
            if top_score > 0:
                # keep a passage only if its fused score is close enough to the article's best passage
                keep = cscores.get(ci, 0.0) >= self.cfg.passage_min_ratio * top_score
            else:
                # article came in via reference / mention: no fused score, compare dense similarity
                keep = dense_c[ci] >= dense_c[best] - self.cfg.passage_dense_margin
            if keep:
                chosen.append(ci)
        return [self.chunks[ci] for ci in sorted(chosen)]

    def search(self, question: str, top_k: Optional[int] = None) -> List[Hit]:
        cfg = self.cfg
        top_k = top_k or cfg.top_k # 관련 조문 수
        n_cand = max(cfg.candidates, top_k) * 2   # candidates are passages, so take more of them
        per_art = max(1, cfg.passages_per_article)
        n_art = len(self.articles)

        # 1) dense : 질문과 각 항의 유사도
        q = self.model.encode([question], normalize_embeddings=True)[0]
        dense_c = self.embeddings @ q
        # 2) keyword : 각 항의 BM25 점수
        bm25_c = self.bm25.get_scores(tokenize(question))

        ok_art = {i for i in range(n_art) if self._searchable(i)}
        ok = [ci for ci in range(len(self.chunks)) if self.chunks[ci].article_idx in ok_art]
        dense_rank = sorted(ok, key=lambda ci: -dense_c[ci])[:n_cand]
        bm25_rank = [ci for ci in sorted(ok, key=lambda ci: -bm25_c[ci]) if bm25_c[ci] > 0][:n_cand]

        # 3) weighted reciprocal rank fusion (passage level)
        fused: Dict[int, float] = {}
        for w, ranking in ((cfg.dense_weight, dense_rank), (cfg.bm25_weight, bm25_rank)):
            for r, ci in enumerate(ranking, start=1):
                fused[ci] = fused.get(ci, 0.0) + w / (cfg.rrf_k + r)
        max_possible = (cfg.dense_weight + cfg.bm25_weight) / (cfg.rrf_k + 1)
        cscores = {ci: sc / max_possible for ci, sc in fused.items()}  # 1.0 = ranked first by both

        # article-level view: an article scores as its best passage
        dense = np.full(n_art, -1.0)
        np.maximum.at(dense, self.chunk_article, dense_c)
        bm25 = np.zeros(n_art)
        np.maximum.at(bm25, self.chunk_article, bm25_c)
        scores: Dict[int, float] = {}
        for ci, sc in cscores.items():
            i = self.chunks[ci].article_idx
            scores[i] = max(scores.get(i, 0.0), sc)

        hits: Dict[int, Hit] = {}
        for i, sc in scores.items():
            hits[i] = Hit(self.articles[i], sc, self.status[i], "검색",
                          {"dense": float(dense[i]), "bm25": float(bm25[i])},
                          self._select(i, cscores, dense_c, per_art))

        # 4) explicitly mentioned articles always come first (more passages: the user asked for it)
        for mention in find_article_mentions(question, self.law_names):
            for i in self._resolve(mention["law"], mention["article"]):
                hits[i] = Hit(self.articles[i], 1.0 + scores.get(i, 0.0), self.status[i], "조문 지정",
                              {"dense": float(dense[i]), "bm25": float(bm25[i])},
                              self._select(i, cscores, dense_c, per_art * 2))

        ranked = sorted(hits.values(), key=lambda h: -h.score)

        # 5) optional cross-encoder rerank
        if self.reranker is not None:
            pinned = [h for h in ranked if h.via == "조문 지정"]
            pool = [h for h in ranked if h.via != "조문 지정"][: max(20, top_k * 3)]
            if pool:
                ce = self.reranker.predict([(question, chunk_search_text(h.article, "", h.passage_text())) for h in pool])
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
            top += self._expand(top, scores, dense, cscores, dense_c)
        # 법령 위계 순서(법률 > 시행령 > 시행규칙 > 훈령)로 정렬: 작은 모델이 하위 규정을 근거로 삼는 것을 막는다
        return sorted(top, key=lambda h: _law_rank(h.article.law_type))

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

    def _expand(self, top: List[Hit], scores: Dict[int, float], dense: np.ndarray,
                cscores: Dict[int, float], dense_c: np.ndarray) -> List[Hit]:
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
            hit = Hit(self.articles[j], scores.get(j, 0.0), self.status[j], "참조", {"dense": float(dense[j])},
                      self._select(j, cscores, dense_c, max(1, self.cfg.passages_per_article)))
            if self._drop_duplicate_versions([hit]):
                out.append(hit)
            if len(out) >= self.cfg.max_reference_hits:
                break
        return out
