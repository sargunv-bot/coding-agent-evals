#!/usr/bin/env bash
set -euo pipefail
command -v rg >/dev/null
command -v cmake >/dev/null
command -v ninja >/dev/null
cd /app

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if [[ -f src/mbgl/util/source_location.hpp ]]; then
    cat >"$tmp/source_location.cpp" <<'CPP'
#include <mbgl/util/source_location.hpp>
int main() {
    constexpr auto here = MLN_CURRENT_SOURCE_LOCATION;
    return here.line() == 0;
}
CPP
    include_flags=(-Isrc)
else
    cat >"$tmp/source_location.cpp" <<'CPP'
int main() { return 0; }
CPP
    include_flags=()
fi
for compiler in g++ clang++; do
    for standard in c++17 c++20; do
        "$compiler" -std="$standard" -Wall -Wextra -Werror "${include_flags[@]}" \
            "$tmp/source_location.cpp" -o "$tmp/${compiler}-${standard}"
        "$tmp/${compiler}-${standard}"
    done
done

cmake --preset linux-opengl -DMLN_WITH_CLANG_TIDY=OFF -DMLN_WITH_COVERAGE=OFF
cmake --build build-linux-opengl --target mbgl-core --parallel 2
