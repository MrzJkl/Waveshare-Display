# User C module "hub75_native_scan": autonomous HUB75 scan engine (PIO + DMA).
# Pass this file to the MicroPython rp2 build via -DUSER_C_MODULES=<path>.
add_library(usermod_hub75_native_scan INTERFACE)

target_sources(usermod_hub75_native_scan INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/hub75_stream.c
    ${CMAKE_CURRENT_LIST_DIR}/hub75_pio.c
    ${CMAKE_CURRENT_LIST_DIR}/hub75_dma.c
    ${CMAKE_CURRENT_LIST_DIR}/hub75_driver.c
    ${CMAKE_CURRENT_LIST_DIR}/mod_hub75_native_scan.c
)

target_include_directories(usermod_hub75_native_scan INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_hub75_native_scan)
