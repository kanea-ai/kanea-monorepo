from __future__ import annotations

import re

# Match @handle where the handle is the email local-part. Restricted
# to the same character set RFC 5321 lets through (alpha-num plus
# . _ - + ) so a stray "@team's" doesn't pull in a phantom apostrophe
# match. The leading boundary is a non-word char OR start-of-string,
# preventing email addresses inside text (alice@kanea.ai) from
# accidentally turning into a mention.
_MENTION_RE = re.compile(r"(?:^|[\s,(\[])@([a-zA-Z0-9._+\-]+)")


def extract_handles(body: str | None) -> list[str]:
    """Returns the lower-cased, deduped, order-preserving list of
    @handles in the body. Non-text inputs (None, empty) return [].

    Order preservation matters because the UI shows the first mention
    in the notification preview; keeping the order consistent across
    re-runs makes that preview deterministic."""
    if not body:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _MENTION_RE.finditer(body):
        handle = match.group(1).lower()
        if handle in seen:
            continue
        seen.add(handle)
        out.append(handle)
    return out
