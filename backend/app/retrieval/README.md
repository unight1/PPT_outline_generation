# RAG 检索模块使用说明

## 快速开始

```python
import asyncio
from app.retrieval import get_retriever, RetrievalRequest, RetrievalDepth

async def main():
    # 传入文档目录和 ChromaDB 持久化路径，创建检索器（单例）
    retriever = get_retriever(
        documents_dir="./sample_docs",
        chroma_persist_dir="./chroma_data",
    )

    # 构造请求
    request = RetrievalRequest(
        query="PPT大纲生成",
        depth=RetrievalDepth.L1,       # 可选 L0 / L1 / L2
        source_filter=None,            # 可选，按文件名过滤，如 ["intro.md"]
        max_results=None,              # 可选，覆盖档位默认召回数
    )

    # 执行检索
    result = await retriever.retrieve(request)

    # 读取结果
    print(f"深度: {result.depth}, 耗时: {result.latency_ms:.1f}ms, 命中: {len(result.hits)} 条")
    for hit in result.hits:
        print(f"  [{hit.source_id}] {hit.locator} | score={hit.score:.4f}")
        print(f"  {hit.snippet[:100]}")

asyncio.run(main())
```

## 命令行运行

```bash
cd backend
uv run python -m app.retrieval.cli <文档目录> <查询关键词>
```

## 深度档位说明

| 档位 | 召回数 | 重排序 | 超时 | 适用场景 |
|------|--------|--------|------|----------|
| `L0` | 5 | 否 | 5s | 快速预览，低延迟 |
| `L1` | 15 | 否 | 10s | 默认平衡模式 |
| `L2` | 30 | 是 | 20s | 深度检索，高质量要求 |

## RetrievalHit 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `snippet` | str | 命中的文本片段 |
| `source_id` | str | 来源文件名 |
| `locator` | str | 位置（如 `L12-L18`、`page 3, L1-L5`） |
| `score` | float? | 检索相关分数 |
| `confidence` | float? | 置信度 0-1（预留） |

## 运行测试

```bash
cd backend
uv run pytest tests/test_retrieval/ -v
```
