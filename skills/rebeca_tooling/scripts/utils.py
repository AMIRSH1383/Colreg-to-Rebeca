#!/usr/bin/env python3
"""Shared utilities for the rebeca_tooling library."""

import shutil
import sys
from pathlib import Path
from typing import IO
from urllib.parse import urlparse

ALLOWED_BASE = Path("/").resolve()


def safe_path(p: str) -> Path:
    """
    Resolve and validate a user-supplied path stays within ALLOWED_BASE.

    Returns the resolved Path on success.
    Prints an error and exits with code 1 if the path escapes ALLOWED_BASE.
    """
    resolved = Path(p).expanduser().resolve()
    if not str(resolved).startswith(str(ALLOWED_BASE)):
        print(f"Error: path '{p}' resolves outside allowed base '{ALLOWED_BASE}'", file=sys.stderr)
        sys.exit(1)
    return resolved


def safe_open(p: str, mode: str = 'r') -> IO:
    """
    Validate path with safe_path then open the file.

    Prevents path traversal by resolving and bounding the path before open().
    Returns the open file handle on success.
    """
    return open(safe_path(p), mode)


def validate_https_url(url: str) -> None:
    """Raise ValueError if url is not a valid https URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Unsafe URL scheme '{parsed.scheme}': only https is permitted")
    if not parsed.netloc:
        raise ValueError(f"Invalid URL (missing host): {url}")


def resolve_executable(name: str) -> str:
    """
    Resolve a program name to its absolute path using shutil.which.

    Prevents OS command injection via partial executable paths.
    Raises FileNotFoundError if the executable is not found on PATH.
    """
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(f"Executable '{name}' not found on PATH")
    return path
