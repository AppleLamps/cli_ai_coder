"""Tests for embeddings retriever."""

import tempfile
import os
from pathlib import Path
import pytest
import numpy as np

from indexer.embeddings import build_or_load_embeddings, EmbIndex, chunk_file


class TestEmbeddingsRetriever:
    """Test embeddings retriever functionality."""

    def test_chunk_file_basic(self):
        """Test basic file chunking."""
        content = "line1\nline2\nline3\nline4\nline5\n"
        chunks = chunk_file("test.py", content, 20, chunk_tokens=2, overlap=1)

        assert len(chunks) > 0
        assert all(isinstance(chunk, tuple) for chunk in chunks)
        assert all(chunk.path == "test.py" for chunk in chunks)
        assert all(chunk.tokens > 0 for chunk in chunks)

    def test_chunk_file_overlap(self):
        """Test chunking with overlap."""
        content = "\n".join([f"line{i}" for i in range(20)])
        chunks = chunk_file("test.py", content, 80, chunk_tokens=3, overlap=1)

        # Should have multiple chunks with overlap
        assert len(chunks) > 1
        # Check that consecutive chunks overlap
        if len(chunks) >= 2:
            first_end = chunks[0].end_line
            second_start = chunks[1].start_line
            assert second_start <= first_end  # Some overlap

    def test_emb_index_init(self):
        """Test EmbIndex initialization."""
        index = EmbIndex()
        assert index.vectors is None
        assert index.model == ""
        assert index.dim == 0
        assert index.built_at == 0.0

    def test_build_embeddings_empty_project(self):
        """Test building embeddings on empty project."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create empty index dir
            index_dir = project_root / ".cli_ai_coder" / "index"
            index_dir.mkdir(parents=True)

            index = build_or_load_embeddings(project_root)
            assert isinstance(index, EmbIndex)
            assert index.vectors is None or len(index.vectors) == 0

    def test_build_embeddings_small_project(self):
        """Test building embeddings on small project."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create a small Python file
            test_file = project_root / "test.py"
            test_file.write_text("def hello():\n    print('hello world')\n    return True\n")

            # Create index
            index = build_or_load_embeddings(project_root, force=True)

            assert isinstance(index, EmbIndex)
            # Should have chunks (unless embedding fails)
            if index.vectors is not None:
                assert len(index.vectors) > 0
                assert index.dim > 0
                assert index.model != ""
                assert len(index.files) > 0

    def test_embeddings_persistence(self):
        """Test embeddings persistence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create test file
            test_file = project_root / "test.py"
            test_file.write_text("def func():\n    pass\n")

            # Build index
            index1 = build_or_load_embeddings(project_root, force=True)

            # Load again (should use cache)
            index2 = build_or_load_embeddings(project_root)

            assert index2.built_at == index1.built_at
            assert len(index2.files) == len(index1.files)

    def test_embeddings_search_no_vectors(self):
        """Test search when no vectors available."""
        index = EmbIndex()
        results = index.search("test query")
        assert results == []

    def test_embeddings_fallback_hash(self):
        """Test hash-based fallback embedding."""
        index = EmbIndex()
        vec = index._hash_bow("test text")
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (384,)
        assert np.all(vec >= 0)  # Non-negative
        assert np.linalg.norm(vec) > 0  # Non-zero