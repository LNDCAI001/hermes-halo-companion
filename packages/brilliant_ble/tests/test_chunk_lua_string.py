"""
Unit tests for chunk_lua_string. No device required: run with pytest, or
directly with python test_chunk_lua_string.py.
"""

from brilliant_ble.brilliant_ble import chunk_lua_string


def escape_lua(file_contents: str) -> str:
    """Applies the same escaping that upload_file_from_string performs before chunking."""
    return (file_contents.replace("\r", "")
                         .replace("\\", "\\\\")
                         .replace("\n", "\\n")
                         .replace("\t", "\\t")
                         .replace("'", "\\'")
                         .replace('"', '\\"'))


def assert_valid_chunks(escaped: str, max_chunk_bytes: int):
    chunks = chunk_lua_string(escaped.encode(), max_chunk_bytes)

    # Reassembles to the original
    assert "".join(chunks) == escaped

    for chunk in chunks:
        # Every chunk fits the byte budget
        assert len(chunk.encode()) <= max_chunk_bytes

        # No chunk ends mid-escape: an odd run of trailing backslashes
        # would leave the closing quote of f:write("...") escaped
        trailing = 0
        while trailing < len(chunk) and chunk[len(chunk) - 1 - trailing] == "\\":
            trailing += 1
        assert trailing % 2 == 0, f"chunk ends mid-escape: ...{chunk[-trailing:]}"


def test_multibyte_characters_never_split_or_exceed_budget():
    # 45° repeated: each ° is 2 bytes in UTF-8, so character-based
    # chunking would overshoot the budget (the original bug)
    script = "\n".join(['print("45°")'] * 50)
    assert_valid_chunks(escape_lua(script), 20)


def test_emoji_survive_chunking_at_awkward_budgets():
    script = "\U0001F600" * 30
    for budget in range(4, 10):
        assert_valid_chunks(script, budget)


def test_escape_sequences_not_split_across_chunks():
    script = escape_lua("a'b\"c\\d\ne" * 20)
    for budget in range(3, 13):
        assert_valid_chunks(script, budget)


def test_runs_of_escaped_backslashes_split_between_pairs():
    script = escape_lua("\\" * 10)
    for budget in range(2, 8):
        assert_valid_chunks(script, budget)


def test_plain_ascii_chunks_at_exactly_the_budget():
    assert chunk_lua_string(b"a" * 10, 4) == ["aaaa", "aaaa", "aa"]


def test_empty_payload_yields_no_chunks():
    assert chunk_lua_string(b"", 10) == []


def test_budget_too_small_raises():
    for payload, budget in (("°°".encode(), 1), (b"ab", 0)):
        try:
            chunk_lua_string(payload, budget)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for budget {budget}")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"Passed: {name}")
    print("All tests passed")
