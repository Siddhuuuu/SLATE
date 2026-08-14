"""
think_filter.py — strips <think>...</think> spans out of a live token
stream, correctly handling the case where a tag's boundary lands across
two separate stream chunks (extremely common — a single delta is often
just a few characters).

Why this exists as a SEPARATE fix from the earlier delta.reasoning leak:
that fix (main.py, "only ever read delta.content") guards a distinct API
field some servers expose for reasoning. This guards against a model
writing literal <think> tags as plain text *inside* content itself —
confirmed happening with qwen3-vl over Ollama even with think=False
requested, since that flag controls how Ollama's server splits fields,
not what the underlying model was trained to generate. A model that
always emits literal tags needs its output filtered, not its API flags
tuned.

Applied universally across all providers (see main.py) as defense-in-depth
— it's a no-op when no tags are present, so it's harmless for providers
(confirmed: Gemini so far) that don't exhibit this behavior.
"""
from __future__ import annotations


class ThinkTagStripper:
    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_think = False

    def feed(self, chunk: str) -> str:
        """
        Feed the next raw chunk of model output. Returns the portion of
        VISIBLE (non-thinking) text that's safe to emit right now. Some
        text is always deliberately held back in the internal buffer in
        case it's the start of a tag that completes in a later chunk —
        call flush() once the stream ends to release anything left over
        that never turned out to be part of a tag.
        """
        self._buffer += chunk
        out: list[str] = []

        while True:
            if not self._in_think:
                idx = self._buffer.find(self.OPEN_TAG)
                if idx != -1:
                    out.append(self._buffer[:idx])
                    self._buffer = self._buffer[idx + len(self.OPEN_TAG) :]
                    self._in_think = True
                    continue
                # No open tag yet — hold back enough of the tail that a
                # partial "<thi" isn't emitted as visible text in case
                # the next chunk completes it into a real tag.
                safe_len = max(0, len(self._buffer) - (len(self.OPEN_TAG) - 1))
                out.append(self._buffer[:safe_len])
                self._buffer = self._buffer[safe_len:]
                break
            else:
                idx = self._buffer.find(self.CLOSE_TAG)
                if idx != -1:
                    # Discard everything up to and including the close
                    # tag — it's reasoning text, never shown.
                    self._buffer = self._buffer[idx + len(self.CLOSE_TAG) :]
                    self._in_think = False
                    continue
                # Still inside a think block. Discard the front of the
                # buffer now (it's reasoning we're never showing anyway)
                # but keep a tail long enough to catch a split close tag —
                # unbounded growth here would hold an entire long
                # reasoning block in memory for no reason.
                safe_len = max(0, len(self._buffer) - (len(self.CLOSE_TAG) - 1))
                self._buffer = self._buffer[safe_len:]
                break

        return "".join(out)

    def flush(self) -> str:
        """
        Call once the stream is done. Releases any text that was held
        back speculatively but never turned out to be a tag (e.g. the
        stream just ended with an ordinary '<' that wasn't a tag start).
        If the stream ended mid-think-block (truncated by max_tokens,
        say), there is nothing safe to show from an unclosed block —
        returns "" in that case rather than leaking partial reasoning.
        """
        if self._in_think:
            self._buffer = ""
            return ""
        remaining = self._buffer
        self._buffer = ""
        return remaining
