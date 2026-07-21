#include <mbgl/util/source_location.hpp>

#if defined(__cpp_lib_source_location) && __cpp_lib_source_location >= 201907L
#error "the C++17 probe unexpectedly selected the standard-library source_location path"
#endif

int main() {}
