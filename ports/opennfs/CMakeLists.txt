cmake_minimum_required(VERSION 3.15)
project(opennfs_web C CXX)

# ENGINE: pristine OpenNFS clone (third-party libraries are used from here, unmodified)
# PORT:   patched engine tree written by prepare.py (src/, shaders/, shim/)
# GLM:    glm checkout (copied into LibOpenNFS/lib/glm, where its nested submodule would put it)
set(ENGINE "D:/n64work/opennfs/OpenNFS" CACHE PATH "")
set(PORT "D:/n64work/opennfs/port" CACHE PATH "")
set(LIBONFS "${PORT}/lib/LibOpenNFS")
unset(GLM CACHE)
set(GLM "${LIBONFS}/lib/glm")

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif ()

# __FILE__ strings (asserts, log lines) must not carry local paths or the parser's per-game directory names
set(PATH_MAP "-fmacro-prefix-map=${LIBONFS}/NFS2/=parser/gen2/ -fmacro-prefix-map=${LIBONFS}/NFS3/=parser/gen3/ -fmacro-prefix-map=${LIBONFS}/NFS4/=parser/gen4/ -fmacro-prefix-map=${LIBONFS}/NFS5/=parser/gen5/ -fmacro-prefix-map=${LIBONFS}/=parser/ -fmacro-prefix-map=${PORT}/src/=engine/ -fmacro-prefix-map=${PORT}/=port/ -fmacro-prefix-map=${ENGINE}/=third_party/")
separate_arguments(PATH_MAP_LIST UNIX_COMMAND "${PATH_MAP}")
set(COMMON_FLAGS "-sUSE_FREETYPE=1 -fexceptions")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} ${COMMON_FLAGS}")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${COMMON_FLAGS} -Wno-deprecated-declarations -Wno-nontrivial-memcall")

# ---- Bullet (only the three libraries the engine links) ----
# PREBUILT_BULLET: reuse libbullet.a of another build directory (the sanitizer build does this to save half an hour)
set(PREBUILT_BULLET "" CACHE FILEPATH "")
if (PREBUILT_BULLET)
    add_library(bullet STATIC IMPORTED)
    set_target_properties(bullet PROPERTIES IMPORTED_LOCATION ${PREBUILT_BULLET} INTERFACE_INCLUDE_DIRECTORIES ${ENGINE}/lib/bullet3/src)
else ()
    file(GLOB_RECURSE BULLET_SOURCES
            ${ENGINE}/lib/bullet3/src/LinearMath/*.cpp
            ${ENGINE}/lib/bullet3/src/BulletCollision/*.cpp
            ${ENGINE}/lib/bullet3/src/BulletDynamics/*.cpp)
    add_library(bullet STATIC ${BULLET_SOURCES})
    target_include_directories(bullet PUBLIC ${ENGINE}/lib/bullet3/src)
    target_compile_options(bullet PRIVATE -w)
    if (WEB_ASAN)
        target_compile_options(bullet PRIVATE -fsanitize=address -g1)
    endif ()
endif ()
# WEB_ASAN: AddressSanitizer for the engine and the parsers (cmake -DWEB_ASAN=ON, separate build directory)
option(WEB_ASAN "AddressSanitizer build" OFF)

# ---- LibOpenNFS (asset format parsers) ----
file(GLOB_RECURSE LIBONFS_SOURCES
        ${LIBONFS}/Common/*.cpp
        ${LIBONFS}/Entities/*.cpp
        ${LIBONFS}/NFS2/*.cpp
        ${LIBONFS}/NFS3/*.cpp
        ${LIBONFS}/NFS4/PC/*.cpp
        ${LIBONFS}/Shared/*.cpp
        ${LIBONFS}/lib/CrpLib/*.cpp)
# not part of the upstream build (unfinished audio bank parser)
list(FILTER LIBONFS_SOURCES EXCLUDE REGEX "/BNK/")
add_library(libonfs STATIC ${LIBONFS_SOURCES})
target_include_directories(libonfs PUBLIC ${GLM} ${LIBONFS} ${LIBONFS}/lib ${ENGINE}/include)
target_compile_options(libonfs PRIVATE -w ${PATH_MAP_LIST})
if (WEB_ASAN)
    target_compile_options(libonfs PRIVATE -fsanitize=address -g1)
endif ()

# ---- Dear ImGui ----
set(IMGUI_SOURCES
        ${ENGINE}/include/imgui/imgui.cpp
        ${ENGINE}/include/imgui/imgui_demo.cpp
        ${ENGINE}/include/imgui/imgui_draw.cpp
        ${ENGINE}/include/imgui/imgui_tables.cpp
        ${ENGINE}/include/imgui/imgui_widgets.cpp
        ${ENGINE}/include/imgui/backends/imgui_impl_glfw.cpp
        ${ENGINE}/include/imgui/backends/imgui_impl_opengl3.cpp
        ${ENGINE}/include/ImGuiColorTextEdit/TextEditor.cpp
        ${ENGINE}/include/implot/implot.cpp
        ${ENGINE}/include/implot/implot_items.cpp)

# ---- Engine ----
file(GLOB_RECURSE ENGINE_SOURCES ${PORT}/src/*.cpp)
add_executable(opennfs ${ENGINE_SOURCES} ${IMGUI_SOURCES})
target_compile_definitions(opennfs PRIVATE
        IMGUI_IMPL_OPENGL_ES3
        IMGUI_USER_CONFIG="${PORT}/src/Renderer/imgui_config.h"
        GLM_ENABLE_EXPERIMENTAL)
target_include_directories(opennfs PRIVATE
        ${PORT}/shim
        ${PORT}/src
        ${ENGINE}/include
        ${ENGINE}/include/imgui
        ${ENGINE}/include/implot)
target_compile_options(opennfs PRIVATE ${PATH_MAP_LIST})
if (WEB_ASAN)
    target_compile_options(opennfs PRIVATE -fsanitize=address -g1)
endif ()
# WEB_FILL: fill byte for fresh C++ allocations (development aid for uninitialised reads), e.g. -DWEB_FILL=0xCC
set(WEB_FILL "" CACHE STRING "")
if (NOT WEB_FILL STREQUAL "")
    set_source_files_properties(${PORT}/src/Web/WebPlatform.cpp PROPERTIES COMPILE_DEFINITIONS "WEB_FILL_NEW=${WEB_FILL};${WEB_FILL_MODE}")
endif ()
target_link_libraries(opennfs PRIVATE libonfs bullet)

set(LINK_FLAGS
        -sUSE_GLFW=3
        -sUSE_FREETYPE=1
        -sMIN_WEBGL_VERSION=2
        -sMAX_WEBGL_VERSION=2
        -sFULL_ES3=1
        -sALLOW_MEMORY_GROWTH=1
        -sINITIAL_MEMORY=268435456
        -sSTACK_SIZE=2097152
        -sFORCE_FILESYSTEM=1
        -sEXIT_RUNTIME=0
        -sENVIRONMENT=web
        "-sEXPORTED_RUNTIME_METHODS=['FS','callMain','ccall']"
        "-sEXPORTED_FUNCTIONS=['_main','_malloc','_free']"
        -fexceptions)
# function names help cdp_stack.py; they are left out of release builds (cmake -DDEV_NAMES=OFF)
option(DEV_NAMES "keep wasm function names" ON)
if (DEV_NAMES)
    list(APPEND LINK_FLAGS --profiling-funcs)
endif ()
if (WEB_ASAN)
    list(APPEND LINK_FLAGS -fsanitize=address -sINITIAL_MEMORY=1073741824 -g1)
endif ()
# link-time runtime checks for hunting memory bugs (cmake -DWEB_CHECKS=ON; slow, never for release)
option(WEB_CHECKS "emscripten runtime checks" OFF)
if (WEB_CHECKS)
    list(APPEND LINK_FLAGS -sASSERTIONS=1 -sSAFE_HEAP=1)
endif ()
# trap as soon as the C stack overflows (cmake -DWEB_STACK_CHECK=ON; link-time only)
option(WEB_STACK_CHECK "trap on stack overflow" OFF)
if (WEB_STACK_CHECK)
    list(APPEND LINK_FLAGS -sSTACK_OVERFLOW_CHECK=2)
endif ()
string(REPLACE ";" " " LINK_FLAGS_STR "${LINK_FLAGS}")
set_target_properties(opennfs PROPERTIES LINK_FLAGS "${LINK_FLAGS_STR}" SUFFIX ".js")
