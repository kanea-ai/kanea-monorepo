"""Phase 4 — pure-text mention extraction.

The extractor only cares about the body string; resolving handles to
users is the service's job. These tests pin the regex behaviour so we
can refactor confidently when the @-syntax evolves."""

from __future__ import annotations

from app.application.notifications.mentions import extract_handles


def test_extracts_simple_mention() -> None:
    assert extract_handles("hi @alice please look") == ["alice"]


def test_dedupes_repeats_preserves_order() -> None:
    assert extract_handles("@bob @alice @bob @charlie @alice") == ["bob", "alice", "charlie"]


def test_lowercases_handles() -> None:
    assert extract_handles("ping @Alice and @ALICE") == ["alice"]


def test_ignores_email_address_in_text() -> None:
    """An email address in prose shouldn't be parsed as a mention. The
    regex requires a non-word boundary before @."""
    assert extract_handles("contact alice@kanea.ai about this") == []


def test_handles_punctuation_and_dots_in_handle() -> None:
    assert extract_handles("ping @first.last for review") == ["first.last"]


def test_handles_after_comma_or_paren() -> None:
    assert extract_handles("for review (@alice, @bob)") == ["alice", "bob"]


def test_empty_or_none_body_returns_empty() -> None:
    assert extract_handles(None) == []
    assert extract_handles("") == []
    assert extract_handles("no mentions here, just text") == []
