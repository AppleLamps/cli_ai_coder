"""Tests for symbol graph."""

import tempfile
from pathlib import Path

from indexer.graph import build_or_load_graph, GraphIndex


class TestSymbolGraph:
    """Test symbol graph functionality."""

    def test_graph_index_init(self):
        """Test GraphIndex initialization."""
        graph = GraphIndex()
        assert graph.nodes == []
        assert graph.edges == []
        assert graph.built_at == 0.0
        assert graph.files == {}

    def test_build_graph_empty_project(self):
        """Test building graph on empty project."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            graph = build_or_load_graph(project_root)
            assert isinstance(graph, GraphIndex)
            assert len(graph.nodes) == 0

    def test_build_graph_small_project(self):
        """Test building graph on small multi-file project."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create main.py with imports
            main_file = project_root / "main.py"
            main_file.write_text("import utils\nfrom helper import func\n\ndef main():\n    func()\n")

            # Create utils.py
            utils_file = project_root / "utils.py"
            utils_file.write_text("def helper():\n    pass\n")

            # Create helper.py
            helper_file = project_root / "helper.py"
            helper_file.write_text("def func():\n    pass\n")

            graph = build_or_load_graph(project_root, force=True)

            assert isinstance(graph, GraphIndex)
            assert len(graph.nodes) >= 2  # At least main and one import
            assert len(graph.edges) >= 1  # At least one import relationship

    def test_neighbors_basic(self):
        """Test basic neighbor finding."""
        graph = GraphIndex()
        graph.nodes = ["a.py", "b.py", "c.py"]
        graph.node_map = {"a.py": 0, "b.py": 1, "c.py": 2}
        graph.edges = [(0, 1, 1.0), (1, 2, 1.0)]  # a->b->c

        # Neighbors of a
        neighbors = graph.neighbors(["a.py"], depth=1)
        assert "a.py" in neighbors  # Should include seed
        assert "b.py" in neighbors
        assert "c.py" not in neighbors  # Depth 1 only

        # Neighbors of a with depth 2
        neighbors = graph.neighbors(["a.py"], depth=2)
        assert "c.py" in neighbors

    def test_neighbors_max_nodes(self):
        """Test max_nodes limit."""
        graph = GraphIndex()
        graph.nodes = [f"{i}.py" for i in range(10)]
        graph.node_map = {f"{i}.py": i for i in range(10)}
        # Create a chain
        graph.edges = [(i, i+1, 1.0) for i in range(9)]

        neighbors = graph.neighbors(["0.py"], depth=10, max_nodes=3)
        assert len(neighbors) <= 3

    def test_graph_persistence(self):
        """Test graph persistence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create test files
            a_file = project_root / "a.py"
            a_file.write_text("import b\ndef func(): pass")
            b_file = project_root / "b.py"
            b_file.write_text("def other(): pass")

            # Build graph
            graph1 = build_or_load_graph(project_root, force=True)

            # Load again
            graph2 = build_or_load_graph(project_root)

            assert graph2.built_at == graph1.built_at
            assert len(graph2.nodes) == len(graph1.nodes)
            assert len(graph2.edges) == len(graph1.edges)