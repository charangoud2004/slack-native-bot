"""
Memory — per-user multi-turn conversation history.

Stores the last N Q&A exchanges so follow-up questions
like "tell me more" or "what about X?" work naturally.
"""

from collections import defaultdict

MAX_TURNS = 5

_history: dict[str, list[dict]] = defaultdict(list)


def get_history(user_id: str) -> list[dict]:
    """Return conversation history for a user."""
    return list(_history[user_id])


def add_turn(user_id: str, question: str, answer: str) -> None:
    """Append a Q&A turn and trim to MAX_TURNS."""
    _history[user_id].append({"role": "user", "content": question})
    _history[user_id].append({"role": "assistant", "content": answer})
    if len(_history[user_id]) > MAX_TURNS * 2:
        _history[user_id] = _history[user_id][-(MAX_TURNS * 2):]


def clear(user_id: str) -> None:
    """Reset conversation history for a user."""
    _history[user_id] = []
