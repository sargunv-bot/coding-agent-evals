#include <mbgl/layout/symbol_instance.hpp>

#include <cassert>
#include <cstring>

template <typename Location>
static Location capture(Location location) {
    return location;
}

int main() {
    const auto location = capture(SYM_GUARD_LOC);
    assert(location.line() > 0);
    (void)location.column();
    assert(std::strstr(location.file_name(), "source_location_behavior.cpp") != nullptr);
    assert(std::strstr(location.function_name(), "main") != nullptr);
}
