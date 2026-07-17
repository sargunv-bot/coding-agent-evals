#!/usr/bin/env python3
"""Accept secure archive-aware designs without requiring the gold patch's private API."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path("/app")
BRIDGE = ROOT / "src/github/sigstore.rs"
BACKEND = ROOT / "src/backend/github.rs"


def fail(message: str, *, unsupported: bool = False) -> None:
    print(f"alternative archive verifier rejected: {message}", file=sys.stderr)
    raise SystemExit(2 if unsupported else 1)


if not BRIDGE.is_file() or not BACKEND.is_file():
    fail("GitHub attestation bridge or backend is missing", unsupported=True)

bridge = BRIDGE.read_text()
backend = BACKEND.read_text()
normalized = re.sub(r"\s+", " ", bridge)

# An alternative design must actually connect archive-aware verification to the
# GitHub backend, not merely add dead helpers or tests.
if "verify_attestation_or_archive_contents" not in backend:
    fail("the GitHub backend does not call an archive-aware verifier", unsupported=True)
if not re.search(r"verify_attestation_or_archive_contents\s*\(", bridge):
    fail("the archive-aware verifier is not implemented in the GitHub bridge", unsupported=True)

# Preserve the existing trust decision: verify the archive itself first and
# enter content fallback only for the explicit no-attestations result.
if "verify_attestation" not in bridge or "AttestationError::NoAttestations" not in bridge:
    fail("archive-first verification with a NoAttestations-only fallback is absent")
if not re.search(
    r"archive_outcome\s*=.*?verify.*?if\s*!matches!\s*\(\s*archive_outcome\s*,\s*Err\s*\(\s*AttestationError::NoAttestations",
    normalized,
):
    fail("non-NoAttestations archive verification outcomes are not returned before fallback")

# The fallback needs a real archive walk and must distinguish regular files.
if not re.search(r"untar|ZipArchive|Archive::new|entries\s*\(", bridge):
    fail("archive contents are not extracted or enumerated")
if not re.search(r"is_file\s*\(\)|is_regular|EntryType::Regular", bridge):
    fail("regular archive members are not identified")
if not re.search(r"for\s+\w+\s+in\s+\w+", bridge):
    fail("archive members are not exhaustively iterated")

# Extraction/inspection errors are security decisions. Returning the original
# NoAttestations result lets callers downgrade to another verification path and
# is therefore not fail-closed.
if re.search(r"Err\s*\([^)]*\)\s*=>\s*\{[^{}]*return\s+archive_outcome", bridge, re.S):
    fail("archive extraction errors are downgraded to NoAttestations")

# Sampling one member cannot establish coverage of every installed regular
# file. In particular, an unattested first member must not make the verifier
# stop looking before discovering that later members are attested.
if "split_first" in bridge and re.search(
    r"Err\s*\(\s*AttestationError::NoAttestations\s*\)\s*=>\s*\{?\s*return\s+archive_outcome",
    bridge,
    re.S,
):
    fail("a single unattested probe bypasses verification of the remaining files")

# Once content-level verification is selected, every missing or invalid member
# attestation must become a terminal error rather than a successful/fallback
# result.
if not re.search(
    r"Err\s*\(\s*AttestationError::NoAttestations\s*\).*?Err\s*\(",
    normalized,
):
    fail("missing inner-file attestations are not converted to a terminal failure")

print("semantic alternative archive verifier checks passed")
