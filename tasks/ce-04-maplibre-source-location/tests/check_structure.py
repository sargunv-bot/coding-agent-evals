#!/usr/bin/env python3
from pathlib import Path

root = Path('/app')
header = root / 'src/mbgl/util/source_location.hpp'
if not header.is_file():
    raise SystemExit('missing src/mbgl/util/source_location.hpp')
text = header.read_text()
if 'namespace std' in text:
    raise SystemExit('fallback must not add declarations to namespace std')
if 'MLN_CURRENT_SOURCE_LOCATION' not in text:
    raise SystemExit('missing call-site source-location capture abstraction')

call_sites = [
    root / 'src/mbgl/layout/symbol_instance.cpp',
    root / 'src/mbgl/layout/symbol_instance.hpp',
    root / 'src/mbgl/renderer/bucket.hpp',
    root / 'src/mbgl/renderer/buckets/symbol_bucket.cpp',
    root / 'src/mbgl/renderer/buckets/symbol_bucket.hpp',
]
for path in call_sites:
    source = path.read_text()
    if 'std::source_location' in source:
        raise SystemExit(f'{path.relative_to(root)} still directly depends on std::source_location')

bazel = (root / 'bazel/core.bzl').read_text()
if 'src/mbgl/util/source_location.hpp' not in bazel:
    raise SystemExit('Bazel core source manifest omits source_location.hpp')
