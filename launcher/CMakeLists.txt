# Wild World Recomped launcher: recomp-ui's launcher window, then the game.
#
#   cmake -S launcher -B launcher\build -G Ninja -DCMAKE_BUILD_TYPE=Release
#   cmake --build launcher\build
#   launcher\build\WildWorldRecomped.exe
#
# Built the way recomp-ui's own demo launcher is built (its CMakeLists.txt),
# against the recomp-ui checkout beside this project. Our own code and
# recomp-ui (MIT) only: the runner (GPL) stays a separate program.

cmake_minimum_required(VERSION 3.24)
project(wild_world_recomped_launcher C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(RECOMP_UI_ROOT "C:/acww/recomp-ui" CACHE PATH "The recomp-ui checkout")
set(ACWW_RUNNER "C:/acww/ndsrecomp/runner/build-acww/nds_runner.exe" CACHE FILEPATH
    "The game (ndsrecomp's runner built for Wild World)")
get_filename_component(ACWW_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.." ABSOLUTE)

# recomp_ui.cmake picks its SDL3 backend when this is set.
set(SNESRECOMP_SDL_BACKEND "SDL3")
find_package(SDL3 CONFIG REQUIRED)

add_executable(WildWorldRecomped main.cpp)
target_link_libraries(WildWorldRecomped PRIVATE SDL3::SDL3 opengl32)
target_compile_definitions(WildWorldRecomped PRIVATE
    ACWW_ROOT="${ACWW_ROOT}"
    ACWW_RUNNER="${ACWW_RUNNER}")
if(TARGET SDL3::SDL3-shared)
    add_custom_command(TARGET WildWorldRecomped POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:SDL3::SDL3-shared> $<TARGET_FILE_DIR:WildWorldRecomped>)
endif()

include("${RECOMP_UI_ROOT}/recomp_ui.cmake")
recomp_target_launcher_ui(WildWorldRecomped CONSOLE nds)
