# Copies every DLL the launcher needs from MSYS2's bin folder next to it, so
# it starts from a shortcut without MSYS2 on PATH. CMakeLists.txt runs it
# after each build:
#
#   cmake -DEXE=<the .exe> -DDLL_DIR=<MSYS2 bin> -DOBJDUMP=<objdump> -P copy_dlls.cmake
#
# Windows' own DLLs aren't in DLL_DIR, so they stay where they are.

if(POLICY CMP0207)
    cmake_policy(SET CMP0207 NEW)   # C:\WINDOWS\system32/x.dll -> C:/WINDOWS/system32/x.dll
endif()

get_filename_component(dest "${EXE}" DIRECTORY)
set(CMAKE_GET_RUNTIME_DEPENDENCIES_PLATFORM "windows+pe")
set(CMAKE_GET_RUNTIME_DEPENDENCIES_TOOL "objdump")
set(CMAKE_GET_RUNTIME_DEPENDENCIES_COMMAND "${OBJDUMP}")

file(GET_RUNTIME_DEPENDENCIES
    EXECUTABLES "${EXE}"
    DIRECTORIES "${DLL_DIR}"
    PRE_EXCLUDE_REGEXES "^api-ms-" "^ext-ms-"
    RESOLVED_DEPENDENCIES_VAR found
    UNRESOLVED_DEPENDENCIES_VAR not_found         # none so far; listed, not fatal
    CONFLICTING_DEPENDENCIES_PREFIX twice)        # found beside the .exe and in DLL_DIR

foreach(dll IN LISTS found)
    string(FIND "${dll}" "${DLL_DIR}/" at)
    if(NOT at EQUAL 0)
        continue()   # Windows' own (system32), or already beside the .exe
    endif()
    get_filename_component(name "${dll}" NAME)
    if(NOT EXISTS "${dest}/${name}")
        message(STATUS "copying ${name}")
    endif()
    file(COPY_FILE "${dll}" "${dest}/${name}" ONLY_IF_DIFFERENT)
endforeach()
