import pytest

from app.rag.chunking import chunk_text


def test_short_text_single_chunk():
    chunks = chunk_text("one two three", chunk_size_words=10, overlap_words=2)
    assert len(chunks) == 1
    assert chunks[0].content == "one two three"
    assert chunks[0].index == 0


def test_empty_text_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_overlap_between_consecutive_chunks():
    words = [f"w{i}" for i in range(50)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size_words=20, overlap_words=5)

    assert len(chunks) > 1
    first_words = chunks[0].content.split()
    second_words = chunks[1].content.split()
    assert first_words[-5:] == second_words[:5]


def test_covers_all_words_no_gaps():
    words = [f"w{i}" for i in range(100)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size_words=30, overlap_words=10)

    covered: set[str] = set()
    for c in chunks:
        covered.update(c.content.split())
    assert covered == set(words)


def test_chunk_indices_are_sequential():
    text = " ".join(f"w{i}" for i in range(100))
    chunks = chunk_text(text, chunk_size_words=30, overlap_words=10)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size_words=10, overlap_words=10)
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size_words=10, overlap_words=20)
