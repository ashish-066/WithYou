"""Early reply publishing.

The reply text is ready before per-turn scoring (response scorer, DSA
evaluator, skill-tree evidence extraction) runs. Graph nodes call
publish_reply_early() as soon as the reply exists, so the candidate hears it
while scoring continues; the worker skips its end-of-run publish if this fired.

The publisher is bound per message by the MessageProcessor via a ContextVar,
which LangGraph's node tasks inherit.
"""

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

logger = logging.getLogger(__name__)

ReplyPublisher = Callable[[str], Awaitable[None]]

_publisher: ContextVar[ReplyPublisher | None] = ContextVar("reply_publisher", default=None)


def bind_reply_publisher(publisher: ReplyPublisher | None):
    """Bind a publisher for the current message. Returns a token for reset."""
    return _publisher.set(publisher)


def reset_reply_publisher(token) -> None:
    _publisher.reset(token)


async def publish_reply_early(text: str) -> None:
    """Send the reply now if a publisher is bound (no-op otherwise)."""
    publisher = _publisher.get()
    if publisher is None or not text:
        return
    try:
        await publisher(text)
    except Exception as e:
        # The worker publishes at the end of the run if this didn't go out
        logger.warning(f"[REPLY] Early publish failed, will publish after run: {e}")
