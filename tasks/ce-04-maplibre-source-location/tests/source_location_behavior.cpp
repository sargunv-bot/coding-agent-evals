#include "src/mbgl/util/source_location.hpp"

#include <cassert>
#include <cstring>
#include <source_location>
#include <type_traits>

static mbgl::source_location capture(mbgl::source_location location) {
    return location;
}

int main() {
    const auto location = capture(MLN_CURRENT_SOURCE_LOCATION);
    assert(location.line() > 0);
    (void)location.column();
    assert(std::strstr(location.file_name(), "source_location_behavior.cpp") != nullptr);
    assert(std::strstr(location.function_name(), "main") != nullptr);
    constexpr mbgl::source_location empty{};
    static_assert(empty.line() == 0);
    static_assert(empty.column() == 0);
    static_assert(std::is_copy_constructible_v<mbgl::source_location>);
    static_assert(noexcept(location.line()));
    static_assert(noexcept(location.column()));
    static_assert(noexcept(location.file_name()));
    static_assert(noexcept(location.function_name()));
#if defined(__cpp_lib_source_location)
    static_assert(std::is_same_v<mbgl::source_location, std::source_location>);
#endif
}
