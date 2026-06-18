"""Tests for the pure text helpers (email extraction + Gmail query building)."""

import pytest

from text_utils import extract_emails, build_query


# --------------------------------------------------------------------------
# extract_emails: pull addresses out of arbitrary pasted text.
# --------------------------------------------------------------------------

def test_extract_emails_from_mixed_text():
    text = "Contact a@b.com and c.d+x@e-f.co please"
    assert extract_emails(text) == ["a@b.com", "c.d+x@e-f.co"]


def test_extract_emails_from_names_and_punctuation():
    text = "John <john@x.com>, jane@y.org; bob@z.io"
    assert extract_emails(text) == ["john@x.com", "jane@y.org", "bob@z.io"]


def test_extract_emails_none_present():
    assert extract_emails("no emails in this line") == []


# --------------------------------------------------------------------------
# build_query: assemble a Gmail search query from optional parts.
# --------------------------------------------------------------------------

def test_build_query_all_parts_in_order():
    q = build_query(sender="s@x.com", subject="Hello", message_id="ID123")
    assert q == "rfc822msgid:ID123 from:(s@x.com) subject:(Hello)"


def test_build_query_sender_only():
    assert build_query(sender="s@x.com") == "from:(s@x.com)"


def test_build_query_subject_only():
    assert build_query(subject="Invoice") == "subject:(Invoice)"


def test_build_query_message_id_only():
    assert build_query(message_id="ABC") == "rfc822msgid:ABC"


def test_build_query_empty_when_no_args():
    assert build_query() == ""
