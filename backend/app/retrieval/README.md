# RAG 检索模块使用说明

## 快速开始

```python
import asyncio
from app.retrieval import get_retriever, RetrievalRequest, RetrievalDepth

async def main():
    # 传入文档目录和 ChromaDB 持久化路径，创建检索器（单例）
    # tavily_api_key 可选，传入后 L1/L2 深度会同时进行本地检索和网络搜索
    retriever = get_retriever(
        documents_dir="./sample_docs",
        chroma_persist_dir="./chroma_data",
        tavily_api_key="tvly-xxx",  # 可选，为空则仅使用本地检索
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
# 基本用法
python -m app.retrieval.cli "查询关键词" --docs <文档目录>

# 启用网络搜索
python -m app.retrieval.cli "AI in education" --depth L1 --web --tavily-key tvly-xxx
```

## 深度档位说明

| 档位 | 召回数 | 重排序 | 网络搜索 | Web 条数 | 超时 | 适用场景 |
|------|--------|--------|----------|----------|------|----------|
| `L0` | 5 | 否 | 否 | - | 5s | 快速预览，低延迟 |
| `L1` | 15 | 否 | 是 | 5 | 10s | 默认平衡模式 |
| `L2` | 30 | 是 | 是 | 8 | 20s | 深度检索，高质量要求 |

## 网络搜索（Tavily）

当传入 `tavily_api_key` 时，L1/L2 深度会并行执行本地向量检索和 Tavily 网络搜索，结果合并后返回。未传入 key 时自动降级为纯本地检索。

网络搜索结果在 `RetrievalHit` 中的字段映射：

| RetrievalHit 字段 | Tavily 字段 |
|-------------------|-------------|
| `snippet` | `content` |
| `source_id` | `url` |
| `locator` | `title` |
| `score` | `score` |

可通过 `source_id` 是否以 `http` 开头区分本地和网络来源。Tavily 调用失败时会静默降级，不影响本地检索。

### 配置方式

三选一，优先级从高到低：

1. **代码传参**：`get_retriever(tavily_api_key="tvly-xxx")`
2. **系统环境变量**：`export TAVILY_API_KEY=tvly-xxx`
3. **.env 文件**：在项目根目录或 `backend/` 下创建 `.env`，写入 `TAVILY_API_KEY=tvly-xxx`

免费额度：每月 1000 次请求，注册地址 https://tavily.com

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
pytest tests/test_retrieval/ -v
```
