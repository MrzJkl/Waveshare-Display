# Create an INTERFACE library for the HUB75 native scan module.
add_library(usermod_hub75_native_scan INTERFACE)

# Add source files for this user C module.
target_sources(usermod_hub75_native_scan INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/hub75_native_scan.c
)

# Add include path for module-local headers (if needed later).
target_include_directories(usermod_hub75_native_scan INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Link this module into MicroPython usermod collection.
target_link_libraries(usermod INTERFACE usermod_hub75_native_scan)
