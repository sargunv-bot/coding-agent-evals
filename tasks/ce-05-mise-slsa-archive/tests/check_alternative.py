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


def without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"//[^\n]*", " ", source)


bridge_code = without_comments(bridge)
backend_code = without_comments(backend)
implementation = ""

# An alternative design must actually connect archive-aware verification to the
# GitHub backend, not merely add dead helpers or tests. Accept a dedicated bridge
# entry point, an archive-aware implementation of the existing bridge chokepoint,
# or an archive-aware backend wrapper around the existing single-blob verifier.
dedicated_entrypoint = "verify_attestation_or_archive_contents" in backend and re.search(
    r"verify_attestation_or_archive_contents\s*\(", bridge
)
existing_chokepoint = (
    re.search(r"sigstore::verify_attestation\s*\(", backend)
    and re.search(r"pub\s+async\s+fn\s+verify_attestation\s*\(", bridge)
    and re.search(r"untar|ZipArchive|Archive::new|entries\s*\(", bridge)
)
backend_wrapper = (
    re.search(r"sigstore::verify_attestation\s*\(", backend)
    and re.search(r"untar|ZipArchive|Archive::new|entries\s*\(|WalkDir::new", backend)
    and len(re.findall(r"verify_github_attestations_for_path\s*\(", backend)) >= 3
)
if dedicated_entrypoint or existing_chokepoint:
    implementation = bridge_code
elif backend_wrapper:
    implementation = backend_code
else:
    fail("the GitHub backend does not reach an archive-aware verifier", unsupported=True)
normalized = re.sub(r"\s+", " ", implementation)

# Preserve the existing trust decision: verify the archive itself first and
# enter content fallback only for the explicit no-attestations result.
if "verify_attestation" not in implementation or "NoAttestations" not in implementation:
    fail("archive-first verification with a NoAttestations-only fallback is absent")
archive_outcome_guard = re.search(
    r"archive_outcome\s*=.*?verify.*?if\s*!matches!\s*\(\s*archive_outcome\s*,\s*Err\s*\([^)]*NoAttestations",
    normalized,
)
direct_match_guard = re.search(
    r"match\s+.*?verify\w*\s*\(.*?\).*?\{.*?Err\s*\([^)]*NoAttestations\s*\)\s*=>.*?Err\s*\([^)]*\)\s*=>\s*(?:return\s+)?Err",
    normalized,
)
if not (archive_outcome_guard or direct_match_guard):
    fail("non-NoAttestations archive verification outcomes are not returned before fallback")

# The fallback needs a real archive walk and must distinguish regular files.
if not re.search(r"untar|ZipArchive|Archive::new|entries\s*\(|WalkDir::new", implementation):
    fail("archive contents are not extracted or enumerated")
if not re.search(r"is_file\s*\(\)|is_regular|EntryType::Regular", implementation):
    fail("regular archive members are not identified")
if not re.search(r"for\s+\w+\s+in\s+(?:&?\w+|WalkDir::new)", implementation):
    fail("archive members are not exhaustively iterated")

# Hard links become ordinary files after extraction, so a post-extraction
# filesystem walk cannot enforce the requested rejection policy by itself.
if not re.search(r"is_hard_link|EntryType::Link|hard_link|hardlink", implementation):
    fail("hard-link archive members are not explicitly rejected")

# Extraction/inspection errors are security decisions. Returning the original
# NoAttestations result lets callers downgrade to another verification path and
# is therefore not fail-closed.
if re.search(r"Err\s*\([^)]*\)\s*=>\s*\{[^{}]*return\s+archive_outcome", implementation, re.S):
    fail("archive extraction errors are downgraded to NoAttestations")

# Sampling one member cannot establish coverage of every installed regular
# file. In particular, an unattested first member must not make the verifier
# stop looking before discovering that later members are attested.
if "split_first" in implementation and re.search(
    r"Err\s*\(\s*AttestationError::NoAttestations\s*\)\s*=>\s*\{?\s*return\s+archive_outcome",
    implementation,
    re.S,
):
    fail("a single unattested probe bypasses verification of the remaining files")

# Once content-level verification is selected, every missing or invalid member
# attestation must become a terminal error rather than a successful/fallback
# result.
direct_missing_member_failure = re.search(
    r"Err\s*\(\s*AttestationError::NoAttestations\s*\).*?Err\s*\(",
    normalized,
)
aggregated_missing_member_failure = (
    "ArchiveMemberOutcome::NoAttestation" in implementation
    and re.search(r"ArchiveMemberOutcome::NoAttestation\s*=>\s*\{?\s*failures\.push", normalized)
    and re.search(r"Err\s*\(\s*AttestationError::Verification", normalized)
)
wrapped_missing_member_failure = re.search(
    r"Err\s*\([^)]*NoAttestations\s*\)\s*=>.*?return\s+Err\s*\([^)]*(?:Error|Verification)",
    normalized,
)
if not (direct_missing_member_failure or aggregated_missing_member_failure or wrapped_missing_member_failure):
    fail("missing inner-file attestations are not converted to a terminal failure")

print("semantic alternative archive verifier checks passed")
