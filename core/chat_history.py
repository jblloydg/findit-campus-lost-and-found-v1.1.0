"""Chat history in Messenger style (v1.1.1, CHG-005).

* Pages are sized by **bytes**, not by a fixed number of messages: each page holds about
  PAGE_BYTES of message data (at least 1, at most MAX_MESSAGES messages). Short messages
  fill a page with many; long messages with fewer. The database is read in small chunks
  and reading stops as soon as the budget is used.
* Directions: the newest page, older than a message, newer than a message, and the
  messages around one message (used when a search result is opened).
* Search inside one conversation: at least 2 characters, newest matches first, short
  snippets only. The typed text is sent to the database as a separate value
  (parameterized query), never as SQL.
* Every reader is rate-limited per person so scrolling or typing cannot flood the server.
"""
import hashlib

from django.core.cache import cache

PAGE_BYTES = 8 * 1024           # text per page; sized for ~1,600 people at once (10% of DOrSU)
MAX_MESSAGES = 50
CHUNK = 40
OVERHEAD_BYTES = 120          # name, time and ids sent with every message
SEARCH_MIN_CHARS = 2
SEARCH_MAX_CHARS = 100
SEARCH_RESULTS = 30
SNIPPET_CHARS = 160
SEARCHES_PER_MINUTE = 20
PAGES_PER_MINUTE = 120


def message_bytes(message):
    return len(message.text.encode("utf-8")) + OVERHEAD_BYTES


def _take(queryset, budget):
    """Read rows in small chunks until the byte budget is used. Returns (rows, more)."""
    rows, used, offset = [], 0, 0
    while True:
        chunk = list(queryset[offset:offset + CHUNK])
        for message in chunk:
            size = message_bytes(message)
            if rows and (used + size > budget or len(rows) >= MAX_MESSAGES):
                return rows, True
            rows.append(message)
            used += size
        if len(chunk) < CHUNK:
            return rows, False
        offset += CHUNK


def latest_page(messages, budget=PAGE_BYTES):
    rows, more = _take(messages.order_by("-pk"), budget)
    return rows[::-1], more


def older_page(messages, before_id, budget=PAGE_BYTES):
    rows, more = _take(messages.filter(pk__lt=before_id).order_by("-pk"), budget)
    return rows[::-1], more


def newer_page(messages, after_id, budget=PAGE_BYTES):
    return _take(messages.filter(pk__gt=after_id).order_by("pk"), budget)


def around_page(messages, message_id, budget=PAGE_BYTES):
    """The message itself, plus about half a page before and half after it."""
    target = messages.filter(pk=message_id).first()
    if target is None:
        return None
    before, has_older = older_page(messages, message_id, budget // 2)
    after, has_newer = newer_page(messages, message_id, budget // 2)
    return before + [target] + after, has_older, has_newer


def search(messages, query):
    query = (query or "").strip()[:SEARCH_MAX_CHARS]
    if len(query) < SEARCH_MIN_CHARS:
        return []
    rows = list(messages.filter(text__icontains=query).order_by("-pk")[:SEARCH_RESULTS])
    results = []
    for message in rows:
        text = message.text
        at = text.lower().find(query.lower())
        start = max(0, at - 50) if at >= 0 else 0
        snippet = text[start:start + SNIPPET_CHARS]
        results.append({
            "id": message.pk,
            "sender": message.sender.first_name or message.sender.username,
            "sent_at": message.sent_at.isoformat(),
            "snippet": ("…" if start else "") + snippet + ("…" if start + SNIPPET_CHARS < len(text) else ""),
        })
    return results


def over_rate_limit(user, kind, per_minute):
    """True when this person already made `per_minute` requests of this kind in the last minute."""
    key = "findit:chat-" + kind + ":" + hashlib.sha256(str(user.pk).encode()).hexdigest()[:24]
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 60)
        count = 1
    return count > per_minute
