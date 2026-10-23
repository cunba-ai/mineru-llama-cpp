"""配置 CI 编译缓存，让 manylinux 容器直接读写宿主持久化目录。"""

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shlex
import tomllib


def cache_environment(runner_os: str, temporary: str, sccache: str, cibw: dict) -> dict[str, str]:
    """按平台生成缓存环境；Linux 显式映射 /host，Windows 使用 CMake 可读路径。"""
    path_type = PureWindowsPath if runner_os == "Windows" else PurePosixPath
    root = path_type(temporary) / "mineru-build-cache"
    executable = path_type(sccache)
    if runner_os == "Windows" and executable.suffix.lower() != ".exe":
        executable = executable.with_suffix(".exe")
    environment = {
        "CIBW_CACHE_PATH": (root / "cibuildwheel").as_posix(),
        "SCCACHE_DIR": (root / "sccache").as_posix(),
        "SCCACHE_CACHE_SIZE": "1G",
        "SCCACHE_IDLE_TIMEOUT": "0",
        "CMAKE_C_COMPILER_LAUNCHER": executable.as_posix(),
        "CMAKE_CXX_COMPILER_LAUNCHER": executable.as_posix(),
    }
    if runner_os == "Linux":
        # 保留项目原有 Vulkan/CMake 设置，仅叠加 CI 的缓存配置。
        container = dict(cibw["linux"]["environment"])
        container.update({key: value for key, value in environment.items() if key != "CIBW_CACHE_PATH"})
        for key in ("SCCACHE_DIR", "CMAKE_C_COMPILER_LAUNCHER", "CMAKE_CXX_COMPILER_LAUNCHER"):
            container[key] = "/host" + container[key]
        environment["CIBW_ENVIRONMENT_LINUX"] = " ".join(
            f"{key}={shlex.quote(value)}" for key, value in container.items()
        )
        # repair 位于真实编译之后；在容器退出前打印统计并等待缓存写入完成。
        environment["CIBW_REPAIR_WHEEL_COMMAND_LINUX"] = (
            cibw["linux"]["repair-wheel-command"] + " && "
            + shlex.quote(container["CMAKE_CXX_COMPILER_LAUNCHER"]) + " --stop-server"
        )
    return environment


def main() -> None:
    """把路径写入 Actions 环境文件，供后续缓存恢复与 cibuildwheel 构建使用。"""
    project = Path(__file__).resolve().parents[1]
    with (project / "pyproject.toml").open("rb") as source:
        cibw = tomllib.load(source)["tool"]["cibuildwheel"]
    environment = cache_environment(os.environ["RUNNER_OS"], os.environ["RUNNER_TEMP"],
                                    os.environ["SCCACHE_PATH"], cibw)
    for name in ("CIBW_CACHE_PATH", "SCCACHE_DIR"):
        Path(environment[name]).mkdir(parents=True, exist_ok=True)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as destination:
        for name, value in environment.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"Unexpected newline in {name}")
            destination.write(f"{name}={value}\n")


if __name__ == "__main__":
    main()
