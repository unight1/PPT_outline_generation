import argparse
import asyncio

from app.retrieval import RetrievalDepth, RetrievalRequest, get_retriever


def parse_args():
    parser = argparse.ArgumentParser(description="RAG 检索模块 CLI")
    parser.add_argument("query", nargs="?", default="PPT大纲生成", help="查询关键词")
    parser.add_argument("--docs", default="sample_docs", help="文档目录路径")
    parser.add_argument("--depth", default=None, choices=["L0", "L1", "L2"], help="检索深度（默认输出全部档位）")
    parser.add_argument("--chroma-dir", default="./chroma_data", help="ChromaDB 持久化目录")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    retriever = get_retriever(
        documents_dir=args.docs,
        chroma_persist_dir=args.chroma_dir,
    )

    depths = (
        [RetrievalDepth(args.depth)] if args.depth else list(RetrievalDepth)
    )

    for depth in depths:
        request = RetrievalRequest(query=args.query, depth=depth)
        result = await retriever.retrieve(request)
        print(f"\n{'='*60}")
        print(f"Depth: {depth.value} | Hits: {len(result.hits)} | Latency: {result.latency_ms:.1f}ms")
        print(f"{'='*60}")
        for i, hit in enumerate(result.hits, 1):
            print(f"\n[{i}] source={hit.source_id}  locator={hit.locator}  score={hit.score:.4f}")
            print(f"    {hit.snippet[:120]}...")


if __name__ == "__main__":
    asyncio.run(main())
