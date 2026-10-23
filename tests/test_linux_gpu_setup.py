"""执行真实 SDK 准备脚本，验证热缓存不联网、残缺缓存进入重建分支。"""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def sdk_setup(tmp_path):
    """在临时项目中提供最小 SDK，并用拒绝联网的命令替身隔离系统安装。"""
    script = tmp_path / "tools/setup_linux_gpu.sh"
    script.parent.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1] / "tools/setup_linux_gpu.sh", script)
    prefix = tmp_path / ".gpu-tools"
    files = {
        "bin/glslc": "#!/bin/sh\nprintf 'shaderc 2026.1\\n'\n",
        "include/vulkan/vulkan_core.h": "#define VK_HEADER_VERSION 350\n",
        "include/spirv/unified1/spirv.hpp": "// 测试所需的 SPIRV 头文件占位。\n",
        "share/cmake/SPIRV-Headers/SPIRV-HeadersConfig.cmake": "# 测试所需的 CMake 包配置。\n",
        "lib/libvulkan.so": "test loader",
    }
    for name, contents in files.items():
        path = prefix / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    (prefix / "bin/glslc").chmod(0o755)
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "yum-call"
    replacements = {
        "yum": '#!/bin/sh\nprintf "%s\\n" "$*" > "$SDK_TEST_CALLS"\nexit 73\n',
        "python": '#!/bin/sh\nif [ "$1" = "-m" ] && [ "$2" = "pip" ]; then exit 91; fi\n'
                  f'exec {shlex.quote(sys.executable)} "$@"\n',
    }
    for name, contents in replacements.items():
        command = commands / name
        command.write_text(contents, encoding="utf-8")
        command.chmod(0o755)
    environment = os.environ.copy()
    environment.update(PATH=str(commands) + os.pathsep + environment["PATH"], SDK_TEST_CALLS=str(calls),
                       PIP_NO_INDEX="1", PIP_CONFIG_FILE=os.devnull)
    return script, prefix, calls, environment


@pytest.mark.parametrize("libdir", ["lib", "lib64"])
def test_valid_sdk_cache_skips_dependency_installation(sdk_setup, libdir):
    """两种 Linux 库目录下的完整缓存均直接成功，不执行 yum 或 pip。"""
    script, prefix, calls, environment = sdk_setup
    if libdir == "lib64":
        (prefix / "lib").rename(prefix / "lib64")
    result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Using cached Vulkan tools" in result.stdout
    assert not calls.exists()
    assert (prefix / libdir / "libvulkan.so").is_file()


@pytest.mark.parametrize("damage", [
    "absent", "old_headers", "old_compiler", "broken_compiler", "missing_compiler",
    "missing_loader", "broken_loader_link", "missing_spirv", "missing_cmake_config",
])
def test_unusable_sdk_cache_enters_cold_setup(sdk_setup, damage):
    """旧版本或缺失组件不能误命中缓存，重建前清理残留并保留安装失败状态。"""
    script, prefix, calls, environment = sdk_setup
    if damage == "absent":
        shutil.rmtree(prefix)
    elif damage == "old_headers":
        (prefix / "include/vulkan/vulkan_core.h").write_text("#define VK_HEADER_VERSION 349\n")
    elif damage == "old_compiler":
        (prefix / "bin/glslc").write_text("#!/bin/sh\nprintf 'shaderc 2025.1\\n'\n")
    elif damage == "broken_compiler":
        (prefix / "bin/glslc").write_text("#!/bin/sh\nexit 1\n")
    else:
        missing = {
            "missing_compiler": "bin/glslc",
            "missing_loader": "lib/libvulkan.so",
            "broken_loader_link": "lib/libvulkan.so",
            "missing_spirv": "include/spirv/unified1/spirv.hpp",
            "missing_cmake_config": "share/cmake/SPIRV-Headers/SPIRV-HeadersConfig.cmake",
        }[damage]
        (prefix / missing).unlink()
        if damage == "broken_loader_link":
            (prefix / missing).symlink_to("libvulkan.so.1.missing")
    result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 73, result.stdout + result.stderr
    assert calls.read_text().startswith("install -y ")
    assert "Using cached Vulkan tools" not in result.stdout
    assert not prefix.exists()
