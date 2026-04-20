import shutil
from pathlib import Path

import pytest

from app.retrieval.embedding.fake import FakeEmbeddingProvider
from app.retrieval.index.chroma import ChromaVectorIndex
from app.retrieval.reranker.fake import FakeReranker
from app.retrieval.sources.local import LocalFileLoader


@pytest.fixture
def sample_docs_dir(tmp_path: Path) -> Path:
    """创建包含样例文档的临时目录。"""
    (tmp_path / "intro.md").write_text(
        "# 项目简介\n\n本系统用于自动生成 PPT 大纲。\n"
        "用户输入主题后，系统将利用大语言模型生成结构化的大纲骨架。\n\n"
        "## 核心功能\n\n- 主题理解与结构化\n"
        "- RAG 检索增强生成\n- 深度研究补充论据\n",
        encoding="utf-8",
    )
    (tmp_path / "tech.md").write_text(
        "# 技术方案\n\n## 后端架构\n\n"
        "后端采用 FastAPI 框架，使用 SQLAlchemy 作为 ORM。\n"
        "检索模块基于向量索引，支持 L0/L1/L2 三档深度。\n\n"
        "## 前端架构\n\nVue 3 + TypeScript。\n",
        encoding="utf-8",
    )
    (tmp_path / "notes.txt").write_text(
        "会议记录 2026-04-15\n\n"
        "讨论了项目的里程碑计划。\n"
        "第3-4周目标：各模块独立开发，弱对接。\n"
        "B 负责的 RAG 模块需要产出可独立运行的 Python 包。\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fake_embedding() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dimension=64)


@pytest.fixture
def fake_reranker() -> FakeReranker:
    return FakeReranker()


@pytest.fixture
def empty_docs_dir(tmp_path: Path) -> Path:
    empty = tmp_path / "empty"
    empty.mkdir()
    return empty
