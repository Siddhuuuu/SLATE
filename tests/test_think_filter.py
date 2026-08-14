from think_filter import ThinkTagStripper


def run(chunks: list[str]) -> str:
    f = ThinkTagStripper()
    out = "".join(f.feed(c) for c in chunks)
    out += f.flush()
    return out


def test_no_tags_passthrough():
    assert run(["Hello ", "World"]) == "Hello World"


def test_single_chunk_full_tag():
    assert run(["before <think>hidden</think> after"]) == "before  after"


def test_tag_split_across_chunks_open_and_close():
    # The exact failure mode this filter exists for: tag boundaries land
    # in separate stream chunks, not one clean string.
    chunks = ["Hello ", "<thi", "nk>reasoning here</th", "ink> World"]
    assert run(chunks) == "Hello  World"


def test_close_tag_split_one_char_at_a_time():
    chunks = ["<think>secret</th", "i", "n", "k", ">", "visible"]
    assert run(chunks) == "visible"


def test_open_tag_split_one_char_at_a_time():
    chunks = ["<", "t", "h", "i", "n", "k", ">", "secret", "</think>", "visible"]
    assert run(chunks) == "visible"


def test_multiple_think_blocks():
    chunks = ["A<think>x</think>B<think>y</think>C"]
    assert run(chunks) == "ABC"


def test_unclosed_think_block_at_stream_end_shows_nothing_from_it():
    # e.g. truncated by max_tokens mid-reasoning — nothing safe to show
    chunks = ["visible text", "<think>reasoning that never closes"]
    assert run(chunks) == "visible text"


def test_less_than_sign_that_is_not_a_tag_is_not_eaten():
    assert run(["3 ", "<", " 5"]) == "3 < 5"


def test_empty_stream():
    assert run([]) == ""


def test_incremental_feed_matches_final_flush_concatenation():
    f = ThinkTagStripper()
    parts = []
    for chunk in ["no tags here", " at all"]:
        parts.append(f.feed(chunk))
    parts.append(f.flush())
    assert "".join(parts) == "no tags here at all"
