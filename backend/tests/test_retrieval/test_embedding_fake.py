from app.retrieval.embedding.fake import FakeEmbeddingProvider


def test_dimension():
    provider = FakeEmbeddingProvider(dimension=64)
    assert provider.dimension == 64


def test_embed_texts_shape():
    provider = FakeEmbeddingProvider(dimension=32)
    result = provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    for vec in result:
        assert len(vec) == 32


def test_deterministic():
    provider = FakeEmbeddingProvider(dimension=64)
    v1 = provider.embed_query("test query")
    v2 = provider.embed_query("test query")
    assert v1 == v2


def test_different_inputs_different_vectors():
    provider = FakeEmbeddingProvider(dimension=64)
    v1 = provider.embed_query("alpha")
    v2 = provider.embed_query("beta")
    assert v1 != v2


def test_normalized():
    provider = FakeEmbeddingProvider(dimension=64)
    vec = provider.embed_query("normalized test")
    norm = sum(x**2 for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-5
