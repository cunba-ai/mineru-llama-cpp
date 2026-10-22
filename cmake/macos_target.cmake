# 仅限制 macOS 目标，Linux/Windows 的 x86_64 构建不受影响。
if (APPLE)
    # 显式交叉编译目标优先，未指定时采用 CMake 检测到的目标处理器。
    if (CMAKE_OSX_ARCHITECTURES)
        set(MINERU_MACOS_TARGET_ARCHITECTURES "${CMAKE_OSX_ARCHITECTURES}")
    else()
        set(MINERU_MACOS_TARGET_ARCHITECTURES "${CMAKE_SYSTEM_PROCESSOR}")
    endif()
    if (NOT MINERU_MACOS_TARGET_ARCHITECTURES STREQUAL "arm64")
        message(FATAL_ERROR
            "mineru-llama-cpp supports only macOS arm64 targets; got '${MINERU_MACOS_TARGET_ARCHITECTURES}'. "
            "Intel/Rosetta x86_64 and universal2 builds are not supported.")
    endif()
endif()
