#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module docstring: one sentence per line keeps diffs reviewable.
Each sentence gets its own line.
"""

import os  # noqa: F401


def fetch(url):
    """Fetch the URL and return its body.
    Retries use exponential backoff,
    and the caller sees only the final result.
    """
    s = "// this is a string literal, not a comment. Never flagged."
    d = """just a string expression,
        not a docstring because it does not follow a def or class"""
    return url, s, d, os
