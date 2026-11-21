"""Plain text from a chat model reply.

A reply's `content` can be a string or a list of content blocks. Current
Gemini models return blocks, e.g. [{"type": "text", "text": "...", "extras":
{...}}], and may add non-text blocks (thinking, tool calls). Code that parses
the reply needs only the text parts, in order.
"""

from typing import Any


def message_text(response: Any) -> str:
    """Text of a model reply (a message, its content, or a plain string)."""
    content = getattr(response, "content", response)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content)
