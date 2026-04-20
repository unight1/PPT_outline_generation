from pathlib import Path

from app.retrieval.interfaces import DocumentLoader
from app.retrieval.types import DocumentChunk

_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 100
_SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


class LocalFileLoader(DocumentLoader):
    """从本地目录加载 .md/.txt/.pdf 文件并分块。"""

    def __init__(
        self,
        documents_dir: str | Path,
        chunk_size: int = _CHUNK_SIZE,
        chunk_overlap: int = _CHUNK_OVERLAP,
    ) -> None:
        self._dir = Path(documents_dir)
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def load(self) -> list[DocumentChunk]:
        if not self._dir.is_dir():
            return []

        chunks: list[DocumentChunk] = []
        for path in sorted(self._dir.rglob("*")):
            if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue
            if path.suffix.lower() == ".pdf":
                chunks.extend(self._load_pdf(path))
            else:
                chunks.extend(self._load_text(path))
        return chunks

    def _load_text(self, path: Path) -> list[DocumentChunk]:
        text = path.read_text(encoding="utf-8", errors="replace")
        return self._chunk_text(text, source_id=path.name)

    def _load_pdf(self, path: Path) -> list[DocumentChunk]:
        try:
            from pypdf import PdfReader
        except ImportError:
            return []

        reader = PdfReader(str(path))
        chunks: list[DocumentChunk] = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            page_chunks = self._chunk_text(
                text,
                source_id=path.name,
                locator_prefix=f"page {page_num}",
            )
            chunks.extend(page_chunks)
        return chunks

    def _chunk_text(
        self,
        text: str,
        source_id: str,
        locator_prefix: str | None = None,
    ) -> list[DocumentChunk]:
        lines = text.split("\n")
        line_offsets: list[int] = []
        pos = 0
        for line in lines:
            line_offsets.append(pos)
            pos += len(line) + 1  # +1 for \n

        chunks: list[DocumentChunk] = []
        start = 0
        while start < len(text):
            end = min(start + self._chunk_size, len(text))
            snippet = text[start:end].strip()
            if snippet:
                start_line = self._find_line(line_offsets, start) + 1
                end_line = self._find_line(line_offsets, end - 1) + 1
                if locator_prefix:
                    locator = f"{locator_prefix}, L{start_line}-L{end_line}"
                else:
                    locator = f"L{start_line}-L{end_line}"
                chunks.append(
                    DocumentChunk(
                        content=snippet,
                        source_id=source_id,
                        locator=locator,
                    )
                )
            start += self._chunk_size - self._chunk_overlap
            if start >= len(text):
                break
        return chunks

    @staticmethod
    def _find_line(line_offsets: list[int], char_pos: int) -> int:
        lo, hi = 0, len(line_offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_offsets[mid] <= char_pos:
                lo = mid
            else:
                hi = mid - 1
        return lo
