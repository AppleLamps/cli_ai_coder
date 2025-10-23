"""Embeddings indexer for semantic search."""

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, NamedTuple
import numpy as np

from core.config import get_config

logger = logging.getLogger(__name__)


class Chunk(NamedTuple):
    """A text chunk with metadata."""
    path: str
    start_line: int
    end_line: int
    text: str
    tokens: int  # Estimated token count


class Hit(NamedTuple):
    """Search result hit."""
    path: str
    start_line: int
    end_line: int
    score: float


class EmbIndex:
    """Embeddings index for semantic search."""

    def __init__(self):
        self.vectors: Optional[np.ndarray] = None
        self.file_ids: Optional[np.ndarray] = None
        self.start_lines: Optional[np.ndarray] = None
        self.end_lines: Optional[np.ndarray] = None
        self.token_counts: Optional[np.ndarray] = None
        self.files: Dict[str, Dict] = {}  # path -> {id, mtime, hash, chunk_count}
        self.model: str = ""
        self.dim: int = 0
        self.built_at: float = 0.0
        self.chunk_tokens: int = 400
        self.overlap: int = 60

    def search(self, query: str, k: int = 10, lang_hint: Optional[str] = None) -> List[Hit]:
        """Search for similar chunks."""
        if self.vectors is None or len(self.vectors) == 0:
            return []

        query_vec = self._embed_query(query)
        if query_vec is None:
            return []

        # Compute similarities
        similarities = np.dot(self.vectors, query_vec) / (
            np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(query_vec)
        )

        # Filter by language if specified
        if lang_hint:
            mask = np.array([
                self._matches_language(path, lang_hint)
                for path in [self._get_path_by_id(fid) for fid in self.file_ids]
            ])
            similarities = np.where(mask, similarities, -np.inf)

        # Get top-k
        top_indices = np.argsort(similarities)[::-1][:k]
        results = []
        for idx in top_indices:
            if similarities[idx] > 0:  # Only positive similarities
                path = self._get_path_by_id(self.file_ids[idx])
                results.append(Hit(
                    path=path,
                    start_line=int(self.start_lines[idx]),
                    end_line=int(self.end_lines[idx]),
                    score=float(similarities[idx])
                ))

        return results

    def _embed_query(self, query: str) -> Optional[np.ndarray]:
        """Embed a query string."""
        # Try SentenceTransformers first
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self.model)
            return model.encode([query], convert_to_numpy=True)[0]
        except ImportError:
            pass

        # Fallback to TF-IDF
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            # This is a simplified fallback - in practice we'd need to store the vectorizer
            return None  # For now, skip TF-IDF fallback
        except ImportError:
            pass

        # Final fallback: hashed BoW
        return self._hash_bow(query)

    def _hash_bow(self, text: str) -> np.ndarray:
        """Simple hashed bag-of-words embedding."""
        words = re.findall(r'\b\w+\b', text.lower())
        vec = np.zeros(384, dtype=np.float32)  # Fixed dim
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
            idx = hash_val % 384
            vec[idx] += 1.0
        # L2 normalize
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _matches_language(self, path: str, lang_hint: str) -> bool:
        """Check if file matches language hint."""
        if lang_hint == 'python' and path.endswith('.py'):
            return True
        if lang_hint in ('javascript', 'typescript') and path.endswith(('.js', '.ts', '.jsx', '.tsx')):
            return True
        return False

    def _get_path_by_id(self, file_id: int) -> str:
        """Get file path by ID."""
        for path, info in self.files.items():
            if info['id'] == file_id:
                return path
        return ""

    def save_to_file(self, index_dir: Path):
        """Save index to files."""
        # Save vectors
        if self.vectors is not None:
            np.savez_compressed(
                index_dir / "embeddings.npz",
                vectors=self.vectors,
                file_ids=self.file_ids,
                start_lines=self.start_lines,
                end_lines=self.end_lines,
                token_counts=self.token_counts
            )

        # Save metadata
        meta = {
            "model": self.model,
            "dim": self.dim,
            "built_at": self.built_at,
            "chunk_tokens": self.chunk_tokens,
            "overlap": self.overlap,
            "files": self.files
        }
        with open(index_dir / "embeddings.meta.json", 'w') as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load_from_file(cls, index_dir: Path) -> 'EmbIndex':
        """Load index from files."""
        index = cls()

        meta_file = index_dir / "embeddings.meta.json"
        if not meta_file.exists():
            return index

        with open(meta_file, 'r') as f:
            meta = json.load(f)

        index.model = meta["model"]
        index.dim = meta["dim"]
        index.built_at = meta["built_at"]
        index.chunk_tokens = meta["chunk_tokens"]
        index.overlap = meta["overlap"]
        index.files = meta["files"]

        # Load vectors
        npz_file = index_dir / "embeddings.npz"
        if npz_file.exists():
            data = np.load(npz_file)
            index.vectors = data["vectors"]
            index.file_ids = data["file_ids"]
            index.start_lines = data["start_lines"]
            index.end_lines = data["end_lines"]
            index.token_counts = data["token_counts"]

        return index


def chunk_file(path: str, content: str, est_tokens: int, chunk_tokens: int = 400, overlap: int = 60) -> List[Chunk]:
    """Chunk a file into smaller pieces."""
    lines = content.splitlines()
    chunks = []
    current_chunk = []
    current_tokens = 0
    start_line = 0

    for i, line in enumerate(lines):
        line_tokens = len(line.split())  # Rough token estimate

        if current_tokens + line_tokens > chunk_tokens and current_chunk:
            # Create chunk
            chunk_text = '\n'.join(current_chunk)
            chunks.append(Chunk(
                path=path,
                start_line=start_line,
                end_line=i,
                text=chunk_text,
                tokens=current_tokens
            ))

            # Start new chunk with overlap
            overlap_lines = max(0, len(current_chunk) - overlap)
            current_chunk = current_chunk[overlap_lines:] + [line]
            current_tokens = sum(len(l.split()) for l in current_chunk)
            start_line = i - len(current_chunk) + 1
        else:
            current_chunk.append(line)
            current_tokens += line_tokens

    # Add final chunk
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        chunks.append(Chunk(
            path=path,
            start_line=start_line,
            end_line=len(lines),
            text=chunk_text,
            tokens=current_tokens
        ))

    return chunks


def build_or_load_embeddings(project_root: Path, force: bool = False) -> EmbIndex:
    """Build or load embeddings index."""
    config = get_config()
    if not config.index_enabled or not config.index_use_embeddings:
        return EmbIndex()

    index_dir = project_root / ".cli_ai_coder" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    index = EmbIndex()
    meta_file = index_dir / "embeddings.meta.json"

    # Check if rebuild needed
    needs_rebuild = force or not meta_file.exists()

    if not needs_rebuild:
        try:
            index = EmbIndex.load_from_file(index_dir)
            # Check for file changes
            for root, dirs, files in os.walk(project_root):
                # Skip ignored dirs
                dirs[:] = [d for d in dirs if not _is_ignored_dir(d, config.index_ignored_globs)]

                for file in files:
                    if _should_index_file(file, config.index_ignored_globs):
                        file_path = Path(root) / file
                        rel_path = str(file_path.relative_to(project_root))

                        if rel_path not in index.files:
                            needs_rebuild = True
                            break

                        current_mtime = file_path.stat().st_mtime
                        current_hash = _file_hash(file_path)
                        if (index.files[rel_path]["mtime"] != current_mtime or
                            index.files[rel_path]["hash"] != current_hash):
                            needs_rebuild = True
                            break
                if needs_rebuild:
                    break
        except Exception as e:
            logger.warning(f"Failed to load embeddings index: {e}")
            needs_rebuild = True

    if needs_rebuild:
        index = _build_embeddings_index(project_root, config)
        index.save_to_file(index_dir)

    return index


def _build_embeddings_index(project_root: Path, config) -> EmbIndex:
    """Build embeddings index from scratch."""
    index = EmbIndex()
    index.model = config.index_embeddings_model
    index.chunk_tokens = config.index_chunk_tokens
    index.overlap = config.index_chunk_overlap
    index.built_at = __import__('time').time()

    all_chunks = []
    file_id_counter = 0

    # Collect all chunks
    for root, dirs, files in os.walk(project_root):
        # Skip ignored dirs
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d, config.index_ignored_globs)]

        for file in files:
            if _should_index_file(file, config.index_ignored_globs):
                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(project_root))

                try:
                    if file_path.stat().st_size > config.index_max_bytes:
                        continue  # Skip large files

                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    est_tokens = len(content.split())  # Rough estimate

                    chunks = chunk_file(rel_path, content, est_tokens,
                                      index.chunk_tokens, index.overlap)
                    all_chunks.extend(chunks)

                    # Track file info
                    index.files[rel_path] = {
                        "id": file_id_counter,
                        "mtime": file_path.stat().st_mtime,
                        "hash": _file_hash(file_path),
                        "chunk_count": len(chunks)
                    }
                    file_id_counter += 1

                except Exception as e:
                    logger.warning(f"Failed to process {file_path}: {e}")
                    continue

    # Limit total chunks
    if len(all_chunks) > config.index_max_chunks:
        all_chunks = all_chunks[:config.index_max_chunks]

    # Generate embeddings
    if all_chunks:
        texts = [chunk.text for chunk in all_chunks]
        vectors = _embed_texts(texts, index.model)

        index.vectors = vectors
        index.file_ids = np.array([index.files[chunk.path]["id"] for chunk in all_chunks], dtype=np.int32)
        index.start_lines = np.array([chunk.start_line for chunk in all_chunks], dtype=np.int32)
        index.end_lines = np.array([chunk.end_line for chunk in all_chunks], dtype=np.int32)
        index.token_counts = np.array([chunk.tokens for chunk in all_chunks], dtype=np.int32)
        index.dim = vectors.shape[1] if vectors is not None else 0

    return index


def _embed_texts(texts: List[str], model_name: str) -> Optional[np.ndarray]:
    """Embed a list of texts."""
    if not texts:
        return None

    # Try SentenceTransformers
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    except ImportError:
        logger.info("SentenceTransformers not available, falling back to TF-IDF")

    # Fallback to TF-IDF
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(max_features=384, stop_words='english')
        return vectorizer.fit_transform(texts).toarray().astype(np.float32)
    except ImportError:
        logger.info("scikit-learn not available, falling back to hashed BoW")

    # Final fallback: hashed BoW
    vectors = []
    for text in texts:
        vec = np.zeros(384, dtype=np.float32)
        words = re.findall(r'\b\w+\b', text.lower())
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
            idx = hash_val % 384
            vec[idx] += 1.0
        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        vectors.append(vec)

    return np.array(vectors, dtype=np.float32)


def _should_index_file(filename: str, ignored_globs: List[str]) -> bool:
    """Check if file should be indexed."""
    from fnmatch import fnmatch

    # Skip binary files and common non-text extensions
    binary_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
                   '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                   '.zip', '.tar', '.gz', '.bz2', '.7z', '.exe', '.dll', '.so',
                   '.dylib', '.pyc', '.pyo', '.class', '.jar'}

    if any(filename.endswith(ext) for ext in binary_exts):
        return False

    # Check ignored globs
    for pattern in ignored_globs:
        if fnmatch(filename, pattern) or fnmatch('**/' + filename, pattern):
            return False

    return True


def _is_ignored_dir(dirname: str, ignored_globs: List[str]) -> bool:
    """Check if directory should be ignored."""
    from fnmatch import fnmatch

    for pattern in ignored_globs:
        if fnmatch(dirname, pattern) or fnmatch('**/' + dirname, pattern):
            return True
    return False


def _file_hash(file_path: Path) -> str:
    """Compute file hash for change detection."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def update_embeddings_for_paths(project_root: Path, paths: List[str]) -> EmbIndex:
    """
    Update embeddings for specific paths.

    Args:
        project_root: Project root path
        paths: List of relative paths to update

    Returns:
        Updated EmbIndex
    """
    config = get_config()
    if not config.index_enabled or not config.index_use_embeddings:
        return EmbIndex()

    index_dir = project_root / ".cli_ai_coder" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # Load existing index
    try:
        index = EmbIndex.load_from_file(index_dir)
    except Exception:
        index = EmbIndex()

    if not index.files:  # No existing index
        return build_or_load_embeddings(project_root, force=True)

    # Track which chunks to remove and add
    chunks_to_remove = set()
    new_chunks = []

    for rel_path in paths:
        file_path = project_root / rel_path

        # Remove existing chunks for this file
        if rel_path in index.files:
            file_id = index.files[rel_path]["id"]
            chunk_count = index.files[rel_path]["chunk_count"]

            # Find chunks belonging to this file
            file_chunk_indices = []
            for i, fid in enumerate(index.file_ids):
                if fid == file_id:
                    file_chunk_indices.append(i)

            # Mark for removal (in reverse order to maintain indices)
            for idx in sorted(file_chunk_indices, reverse=True):
                chunks_to_remove.add(idx)

        # Add new chunks if file exists
        if file_path.exists():
            try:
                if file_path.stat().st_size > config.index_max_bytes:
                    continue

                content = file_path.read_text(encoding='utf-8', errors='ignore')
                est_tokens = len(content.split())

                chunks = chunk_file(rel_path, content, est_tokens,
                                  index.chunk_tokens, index.overlap)
                new_chunks.extend(chunks)

                # Update file info
                index.files[rel_path] = {
                    "id": len(index.files),  # Will be reassigned
                    "mtime": file_path.stat().st_mtime,
                    "hash": _file_hash(file_path),
                    "chunk_count": len(chunks)
                }

            except Exception:
                # Remove file from index on error
                if rel_path in index.files:
                    del index.files[rel_path]
        else:
            # File deleted
            if rel_path in index.files:
                del index.files[rel_path]

    # Rebuild vectors if there are changes
    if chunks_to_remove or new_chunks:
        # Remove old chunks
        if chunks_to_remove:
            keep_indices = [i for i in range(len(index.vectors)) if i not in chunks_to_remove]
            if keep_indices:
                index.vectors = index.vectors[keep_indices]
                index.file_ids = index.file_ids[keep_indices]
                index.start_lines = index.start_lines[keep_indices]
                index.end_lines = index.end_lines[keep_indices]
                index.token_counts = index.token_counts[keep_indices]
            else:
                # All chunks removed
                index.vectors = None
                index.file_ids = None
                index.start_lines = None
                index.end_lines = None
                index.token_counts = None

        # Add new chunks
        if new_chunks:
            new_texts = [chunk.text for chunk in new_chunks]
            new_vectors = _embed_texts(new_texts, index.model)

            if new_vectors is not None:
                new_file_ids = np.array([index.files[chunk.path]["id"] for chunk in new_chunks], dtype=np.int32)
                new_start_lines = np.array([chunk.start_line for chunk in new_chunks], dtype=np.int32)
                new_end_lines = np.array([chunk.end_line for chunk in new_chunks], dtype=np.int32)
                new_token_counts = np.array([chunk.tokens for chunk in new_chunks], dtype=np.int32)

                if index.vectors is not None:
                    index.vectors = np.concatenate([index.vectors, new_vectors])
                    index.file_ids = np.concatenate([index.file_ids, new_file_ids])
                    index.start_lines = np.concatenate([index.start_lines, new_start_lines])
                    index.end_lines = np.concatenate([index.end_lines, new_end_lines])
                    index.token_counts = np.concatenate([index.token_counts, new_token_counts])
                else:
                    index.vectors = new_vectors
                    index.file_ids = new_file_ids
                    index.start_lines = new_start_lines
                    index.end_lines = new_end_lines
                    index.token_counts = new_token_counts

                index.dim = new_vectors.shape[1]

        # Reassign file IDs to be contiguous
        file_id_map = {}
        next_id = 0
        for rel_path, info in index.files.items():
            file_id_map[info["id"]] = next_id
            index.files[rel_path]["id"] = next_id
            next_id += 1

        # Update file_ids array
        if index.file_ids is not None:
            index.file_ids = np.array([file_id_map[fid] for fid in index.file_ids], dtype=np.int32)

        # Update metadata
        index.built_at = __import__('time').time()

        # Save updated index
        index.save_to_file(index_dir)

    return index
