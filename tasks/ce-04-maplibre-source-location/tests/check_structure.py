#!/usr/bin/env python3
import re
from pathlib import Path

root = Path("/app")
relative_headers = [
    Path("src/mbgl/util/source_location.hpp"),
    Path("include/mbgl/util/source_location.hpp"),
]
relative_header = next((path for path in relative_headers if (root / path).is_file()), None)
if relative_header is None:
    raise SystemExit("missing mbgl/util/source_location.hpp")
text = (root / relative_header).read_text()
if re.search(r"namespace\s+std\s*{", text):
    raise SystemExit("fallback must not add declarations to namespace std")

symbol_header = root / "src/mbgl/layout/symbol_instance.hpp"
symbol_text = symbol_header.read_text()
def capture_macro(source: str):
    return next(
        (
            (name, body)
            for name, body in re.findall(
                r"^\s*#\s*define\s+([A-Z][A-Z0-9_]*)\s+([^\\\n]+)",
                source,
                re.MULTILINE,
            )
            if "source_location" in body and ("current" in body or "__FILE__" in body)
        ),
        None,
    )


header_capture = capture_macro(text)
capture = header_capture or capture_macro(symbol_text)
if capture is None:
    raise SystemExit("missing call-site source-location capture abstraction")
capture_name, capture_expression = capture
capture_value = capture_name if header_capture else capture_expression
(Path("/tmp/ce04") / "current_macro.hpp").write_text(
    f"#define CAE_CURRENT_SOURCE_LOCATION {capture_value}\n"
)

call_sites = [
    root / 'src/mbgl/layout/symbol_instance.cpp',
    root / 'src/mbgl/layout/symbol_instance.hpp',
    root / 'src/mbgl/renderer/bucket.hpp',
    root / 'src/mbgl/renderer/buckets/symbol_bucket.cpp',
    root / 'src/mbgl/renderer/buckets/symbol_bucket.hpp',
]
for path in call_sites:
    source = path.read_text()
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
    if "std::source_location" in code:
        raise SystemExit(f'{path.relative_to(root)} still directly depends on std::source_location')

relative = relative_header.as_posix()
bazel = (root / "bazel/core.bzl").read_text()
cmake = (root / "CMakeLists.txt").read_text()
if relative not in bazel and relative not in cmake:
    raise SystemExit("core build manifests omit source_location.hpp")
