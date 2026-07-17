#include <mbgl/util/source_location.hpp>
#include "/tmp/ce04/current_macro.hpp"

#include <cassert>
#include <cstring>
#include <source_location>
#include <type_traits>

template <typename Location>
static Location capture(Location location) {
    return location;
}

int main() {
    const auto location = capture(CAE_CURRENT_SOURCE_LOCATION);
    using source_location = std::remove_cv_t<decltype(location)>;
    assert(location.line() > 0);
    (void)location.column();
    assert(std::strstr(location.file_name(), "source_location_behavior.cpp") != nullptr);
    assert(std::strstr(location.function_name(), "main") != nullptr);
    constexpr source_location empty{};
    static_assert(empty.line() == 0);
    static_assert(empty.column() == 0);
    static_assert(std::is_copy_constructible_v<source_location>);
    static_assert(noexcept(location.line()));
    static_assert(noexcept(location.column()));
    static_assert(noexcept(location.file_name()));
    static_assert(noexcept(location.function_name()));
#if defined(__cpp_lib_source_location)
    static_assert(std::is_same_v<source_location, std::source_location>);
#endif
}
