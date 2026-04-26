from pathlib import Path

from app.retrieval.sources.local import LocalFileLoader


def test_load_text_files(sample_docs_dir: Path):
    loader = LocalFileLoader(sample_docs_dir)
    chunks = loader.load()
    assert len(chunks) > 0
    sources = {c.source_id for c in chunks}
    assert "intro.md" in sources
    assert "tech.md" in sources
    assert "notes.txt" in sources


def test_chunks_have_locators(sample_docs_dir: Path):
    loader = LocalFileLoader(sample_docs_dir)
    chunks = loader.load()
    for chunk in chunks:
        assert chunk.locator.startswith("L")
        assert chunk.content.strip() != ""


def test_empty_directory(empty_docs_dir: Path):
    loader = LocalFileLoader(empty_docs_dir)
    chunks = loader.load()
    assert chunks == []


def test_nonexistent_directory(tmp_path: Path):
    loader = LocalFileLoader(tmp_path / "no_such_dir")
    chunks = loader.load()
    assert chunks == []


def test_unsupported_files_ignored(tmp_path: Path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "data.json").write_text("{}")
    (tmp_path / "readme.md").write_text("hello world", encoding="utf-8")
    loader = LocalFileLoader(tmp_path)
    chunks = loader.load()
    assert len(chunks) > 0
    assert all(c.source_id == "readme.md" for c in chunks)


def test_chunk_size_respected(tmp_path: Path):
    long_text = "A" * 1000
    (tmp_path / "long.txt").write_text(long_text, encoding="utf-8")
    loader = LocalFileLoader(tmp_path, chunk_size=200, chunk_overlap=50)
    chunks = loader.load()
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= 200
