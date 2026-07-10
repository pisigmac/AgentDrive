"""Semantic and keyword search across vault."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from datetime import datetime, timezone

import yaml
from rich.console import Console

from .config import VaultConfig, find_vault_root

console = Console()


@dataclass
class SearchResult:
    path: str
    score: float
    snippet: str
    metadata: dict[str, Any]


class VaultSearch:
    """Search across all vault content. Keyword + lightweight semantic."""
    
    def __init__(self, vault_path: Path | None = None):
        self.vault_path = Path(vault_path) if vault_path else find_vault_root()
        self.config = VaultConfig.load(self.vault_path / ".vault" / "config.yaml")
        self._embeddings: dict[str, list[float]] | None = None
    
    def search(
        self,
        query: str,
        directories: list[str] | None = None,
        limit: int = 10,
        semantic: bool = False,
    ) -> list[SearchResult]:
        """Search vault by query."""
        results = []
        
        # Determine directories to search
        dirs_to_search = []
        if directories:
            for d in directories:
                dir_config = self.config.get_directory(d)
                if dir_config:
                    dirs_to_search.append(Path(dir_config.vault_path))
        else:
            for d in self.config.directories:
                dirs_to_search.append(Path(d.vault_path))
        
        # Keyword search
        for dir_path in dirs_to_search:
            if not dir_path.exists():
                continue
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                score, snippet, meta = self._score_file(file, query)
                if score > 0:
                    results.append(SearchResult(
                        path=str(file.relative_to(self.vault_path)),
                        score=score,
                        snippet=snippet,
                        metadata=meta,
                    ))
        
        # Semantic search (if enabled and available)
        if semantic:
            results = self._semantic_rerank(query, results)
        
        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def _score_file(self, file: Path, query: str) -> tuple[float, str, dict[str, Any]]:
        """Score a file against query. Returns (score, snippet, metadata)."""
        content = file.read_text(encoding="utf-8", errors="ignore")
        query_lower = query.lower()
        
        # Parse frontmatter
        meta = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except Exception:
                    pass
                content = parts[2] if len(parts) > 2 else ""
        
        # Scoring
        score = 0.0
        
        # Title match (highest weight)
        title = meta.get("title", "") or file.stem
        if query_lower in title.lower():
            score += 10.0
        
        # Tag match
        tags = meta.get("tags", []) or []
        for tag in tags:
            if query_lower in str(tag).lower():
                score += 8.0
        
        # Content match
        content_lower = content.lower()
        count = content_lower.count(query_lower)
        score += min(count * 2.0, 20.0)
        
        # Name match in path
        if query_lower in file.name.lower():
            score += 5.0
        
        # Extract snippet around first match
        snippet = self._extract_snippet(content, query)
        
        return score, snippet, meta
    
    def _extract_snippet(self, content: str, query: str, context: int = 80) -> str:
        """Extract text snippet around query match."""
        idx = content.lower().find(query.lower())
        if idx == -1:
            # Return first 200 chars
            return content[:200].replace("\n", " ")
        
        start = max(0, idx - context)
        end = min(len(content), idx + len(query) + context)
        snippet = content[start:end]
        
        # Clean up
        snippet = snippet.replace("\n", " ")
        snippet = re.sub(r"\s+", " ", snippet)
        
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        
        return snippet.strip()
    
    def _semantic_rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        """Rerank results using sentence embeddings."""
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            
            model = SentenceTransformer("all-MiniLM-L6-v2")
            
            query_emb = model.encode([query])[0]
            texts = [r.snippet for r in results]
            
            if not texts:
                return results
            
            doc_embs = model.encode(texts)
            
            # Cosine similarity
            for i, result in enumerate(results):
                sim = np.dot(query_emb, doc_embs[i]) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(doc_embs[i])
                )
                # Blend keyword and semantic scores
                result.score = result.score * 0.3 + float(sim) * 10 * 0.7
            
            return results
        except ImportError:
            console.print("[yellow]sentence-transformers not installed. Install with: pip install personal-vault[semantic][/yellow]")
            return results
    
    def build_index(self) -> dict[str, Any]:
        """Build search index for all vault content."""
        index = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entries": [],
        }
        
        for d in self.config.directories:
            dir_path = Path(d.vault_path)
            if not dir_path.exists():
                continue
            
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                content = file.read_text(encoding="utf-8", errors="ignore")
                meta = {}
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 2:
                        try:
                            meta = yaml.safe_load(parts[1]) or {}
                        except Exception:
                            pass
                
                index["entries"].append({
                    "path": str(file.relative_to(self.vault_path)),
                    "title": meta.get("title", file.stem),
                    "tags": meta.get("tags", []),
                    "status": meta.get("status", "unknown"),
                    "modified": meta.get("modified", ""),
                })
        
        # Save index
        index_path = self.vault_path / ".vault" / "index" / "search-index.yaml"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "w") as f:
            yaml.dump(index, f, default_flow_style=False, sort_keys=False)
        
        return index
    
    def find_related(self, path: str) -> list[SearchResult]:
        """Find files related to a given path by tags and links."""
        file_path = self.vault_path / path
        if not file_path.exists():
            return []
        
        content = file_path.read_text(encoding="utf-8")
        meta = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except Exception:
                    pass
        
        tags = set(meta.get("tags", []) or [])
        
        # Search by tags
        results = []
        for tag in tags:
            tag_results = self.search(str(tag), limit=20)
            for r in tag_results:
                if r.path != path:
                    results.append(r)
        
        # Deduplicate and sort
        seen = set()
        unique = []
        for r in results:
            if r.path not in seen:
                seen.add(r.path)
                unique.append(r)
        
        unique.sort(key=lambda x: x.score, reverse=True)
        return unique[:10]
