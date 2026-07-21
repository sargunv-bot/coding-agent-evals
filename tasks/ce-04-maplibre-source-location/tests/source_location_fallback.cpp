#include <mbgl/util/source_location.hpp>

#include <cassert>
#include <cstring>

#if defined(__cpp_lib_source_location) && __cpp_lib_source_location >= 201907L
#error "the C++17 probe unexpectedly selected the standard-library source_location path"
#endif

int main() {
    const auto location = (CE04_SOURCE_LOCATION_EXPRESSION);
    assert(location.line() > 0);
    (void)location.column();
    assert(std::strstr(location.file_name(), "source_location_macro_probe.cpp") != nullptr);
    assert(std::strlen(location.function_name()) > 0);
}
