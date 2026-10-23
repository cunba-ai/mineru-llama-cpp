"""验证编译缓存跨容器挂载、Windows 路径及各平台工具链隔离。"""

import importlib
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

import pytest
import yaml

from test_publish_workflows import load_workflow


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cache_tools(monkeypatch):
    """导入生产配置工具，并使用当前项目的 cibuildwheel 设置。"""
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    with (ROOT / "pyproject.toml").open("rb") as source:
        cibw = tomllib.load(source)["tool"]["cibuildwheel"]
    return importlib.import_module("setup_ci_cache"), cibw


def test_linux_cache_maps_host_paths_and_preserves_build_policy(cache_tools):
    """容器缓存和启动器映射至宿主，Vulkan 配置及原有 wheel 修复命令继续执行。"""
    tool, cibw = cache_tools
    environment = tool.cache_environment("Linux", "/home/runner/temp dir", "/opt/tool cache/sccache", cibw)
    container = dict(item.split("=", 1) for item in shlex.split(environment["CIBW_ENVIRONMENT_LINUX"]))
    assert container["SCCACHE_DIR"] == "/host/home/runner/temp dir/mineru-build-cache/sccache"
    assert container["CMAKE_C_COMPILER_LAUNCHER"] == "/host/opt/tool cache/sccache"
    assert container["CMAKE_CXX_COMPILER_LAUNCHER"] == container["CMAKE_C_COMPILER_LAUNCHER"]
    assert environment["SCCACHE_DIR"] == "/home/runner/temp dir/mineru-build-cache/sccache"
    assert all(container[key] == value for key, value in cibw["linux"]["environment"].items())
    repair = environment["CIBW_REPAIR_WHEEL_COMMAND_LINUX"]
    assert repair.startswith(cibw["linux"]["repair-wheel-command"] + " && ")
    assert shlex.split(repair.split(" && ")[-1]) == ["/host/opt/tool cache/sccache", "--stop-server"]


@pytest.mark.parametrize("runner_os,temporary,executable,expected", [
    ("macOS", "/Users/runner/temp", "/Users/runner/tools/sccache", "/Users/runner/tools/sccache"),
    ("Windows", r"D:\a\_temp", r"C:\hosted tools\sccache", "C:/hosted tools/sccache.exe"),
    ("Windows", r"D:\a\_temp", r"C:\hosted tools\sccache.exe", "C:/hosted tools/sccache.exe"),
])
def test_native_cache_uses_platform_paths(cache_tools, runner_os, temporary, executable, expected):
    """原生构建不添加 Linux 挂载前缀，Windows 启动器保留 exe 后缀及带空格路径。"""
    tool, cibw = cache_tools
    environment = tool.cache_environment(runner_os, temporary, executable, cibw)
    assert environment["CMAKE_C_COMPILER_LAUNCHER"] == expected
    assert environment["CMAKE_CXX_COMPILER_LAUNCHER"] == expected
    assert "\\" not in environment["SCCACHE_DIR"]
    assert "CIBW_ENVIRONMENT_LINUX" not in environment
    assert "CIBW_REPAIR_WHEEL_COMMAND_LINUX" not in environment


def test_cache_cli_writes_actions_environment(tmp_path):
    """真实入口追加环境文件并创建两个独立缓存目录，不修改源码构建设置。"""
    destination = tmp_path / "github-env"
    destination.write_text("EXISTING=value\n")
    environment = os.environ.copy()
    environment.update(RUNNER_OS="macOS", RUNNER_TEMP=str(tmp_path / "temp dir"),
                       SCCACHE_PATH=str(tmp_path / "sccache"), GITHUB_ENV=str(destination))
    subprocess.run([sys.executable, str(ROOT / "tools/setup_ci_cache.py")], env=environment, check=True)
    values = dict(line.split("=", 1) for line in destination.read_text().splitlines())
    assert values["EXISTING"] == "value"
    assert values["SCCACHE_DIR"] != values["CIBW_CACHE_PATH"]
    assert Path(values["SCCACHE_DIR"]).is_dir()
    assert Path(values["CIBW_CACHE_PATH"]).is_dir()


def test_workflow_keeps_toolchain_caches_separate():
    """所有编译 job 启用缓存，两个 Xcode 与 Windows 编译器使用不同命名空间。"""
    jobs = load_workflow("build-wheels.yml")["jobs"]
    expected = {
        "build_linux_x86_64": "manylinux228", "build_linux_aarch64": "manylinux228",
        "build_macos": "xcode-26.6", "check_macos_older_sdk": "xcode-16.4",
        "build_windows": "msvc-2022", "build_windows_arm64": "clang-cl-arm64",
    }
    for job, toolchain in expected.items():
        step = next(step for step in jobs[job]["steps"] if step.get("uses") == "./.github/actions/build-cache")
        assert step["with"]["toolchain"] == toolchain
    action = yaml.safe_load((ROOT / ".github/actions/build-cache/action.yml").read_text())
    caches = [step["with"] for step in action["runs"]["steps"] if step.get("uses") == "actions/cache@v4"]
    assert {cache["path"] for cache in caches} == {"${{ env.CIBW_CACHE_PATH }}", "${{ env.SCCACHE_DIR }}"}
    compiler = next(cache for cache in caches if "SCCACHE_DIR" in cache["path"])
    for part in ("runner.os", "runner.arch", "inputs.toolchain"):
        assert part in compiler["key"] and part in compiler["restore-keys"]
