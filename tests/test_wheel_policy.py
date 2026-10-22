"""验证五平台分发矩阵、稳定 ABI、Windows 架构以及 Linux 系统 ABI 下限。"""

import importlib
import struct
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def wheel_tools(monkeypatch):
    """导入生产审计工具，使用临时 wheel 而不运行跨平台构建。"""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    return importlib.import_module("verify_wheels"), importlib.import_module("repair_linux_wheel")


def make_wheel(directory, platform, backends, extra=None):
    """构造最小标签及 PE 头，专门验证分发规则而非原生代码执行。"""
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0xAA64 if platform == "win_arm64" else 0x8664)
    windows = platform.startswith("win_")
    module_suffix = ".dll" if windows else ".so"
    module_prefix = "" if windows else "lib"
    extension_suffix = ".pyd" if windows else ".abi3.so"
    contents = {f"mineru_llama_cpp/_mineru_llama_cpp{extension_suffix}": bytes(data)}
    contents.update({f"mineru_llama_cpp/bin/{module_prefix}ggml-{backend}{module_suffix}": bytes(data) for backend in backends})
    contents.update(extra or {})
    wheel = directory / f"mineru_llama_cpp-0.1.2-cp311-abi3-{platform}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    return wheel


def test_five_platform_matrix(wheel_tools, tmp_path):
    """五平台保持完整，Linux/Windows 仅要求 CPU 和 Vulkan。"""
    verifier, _ = wheel_tools
    wheels = [make_wheel(tmp_path, platform, backends) for platform, backends in verifier.PLATFORMS.items()]
    assert len(verifier.verify(wheels)) == 5
    assert verifier.PLATFORMS["manylinux_2_28_x86_64"] == {"cpu", "vulkan"}
    assert verifier.PLATFORMS["win_amd64"] == {"cpu", "vulkan"}


def test_wheel_set_requires_all_platforms(wheel_tools, tmp_path):
    """自动发布仍拒绝缺少平台的集合，手动发布可以校验明确选择的子集。"""
    verifier, _ = wheel_tools
    platform = "macosx_14_0_arm64"
    wheel = make_wheel(tmp_path, platform, verifier.PLATFORMS[platform])
    with pytest.raises(ValueError, match="Expected five wheels"):
        verifier.verify([wheel])
    assert len(verifier.verify([wheel], require_all=False)) == 1


def test_wheel_requires_stable_abi_tag(wheel_tools, tmp_path):
    """普通 CPython 扩展标签仍不能混入 cp311-abi3 发布集合。"""
    verifier, _ = wheel_tools
    platform = "macosx_14_0_arm64"
    wheel = make_wheel(tmp_path, platform, verifier.PLATFORMS[platform])
    wheel = wheel.rename(wheel.with_name(wheel.name.replace("cp311-abi3", "cp312-cp312")))
    with pytest.raises(ValueError, match="Unexpected package or ABI tag"):
        verifier.verify([wheel], require_all=False)


@pytest.mark.parametrize("tag", ["cp310-abi3", "cp312-abi3", "cp311-cp311"])
def test_wheel_requires_python311_abi_floor(wheel_tools, tmp_path, tag):
    """发布集合仅接受统一的 cp311-abi3 标签，不能混入旧基线或逐版本扩展。"""
    verifier, _ = wheel_tools
    platform = "macosx_14_0_arm64"
    wheel = make_wheel(tmp_path, platform, verifier.PLATFORMS[platform])
    wheel = wheel.rename(wheel.with_name(wheel.name.replace("cp311-abi3", tag)))
    with pytest.raises(ValueError, match="Unexpected package or ABI tag"):
        verifier.verify([wheel], require_all=False)


@pytest.mark.parametrize("platform", [
    "macosx_14_0_x86_64", "macosx_14_0_universal2",
    "macosx_14_0_arm64.macosx_14_0_x86_64",
    "macosx_14_0_arm64.macosx_14_0_universal2",
])
@pytest.mark.parametrize("require_all", [False, True])
def test_macos_intel_and_universal_wheels_are_rejected(wheel_tools, tmp_path, platform, require_all):
    """完整集合和手动子集均拒绝 Intel 标签，包括伪装成 arm64 的压缩标签。"""
    verifier, _ = wheel_tools
    wheel = make_wheel(tmp_path, platform, {"cpu", "metal"})
    with pytest.raises(ValueError, match="Unsupported platform"):
        verifier.verify([wheel], require_all=require_all)


@pytest.mark.parametrize("platform", ["macosx_14_0_x86_64", "macosx_14_0_universal2"])
def test_macos_audit_rejects_unsupported_wheel_before_unpacking(wheel_tools, tmp_path, monkeypatch, platform):
    """macOS 专项审计在调用系统工具前即拒绝已移除的平台。"""
    auditor = importlib.import_module("verify_macos_wheel")
    wheel = tmp_path / f"mineru_llama_cpp-0.1.5-cp311-abi3-{platform}.whl"
    monkeypatch.setattr(sys, "argv", ["verify_macos_wheel.py", str(wheel)])
    with pytest.raises(AssertionError, match="expected macosx_14_0_arm64 wheel"):
        auditor.main()


@pytest.mark.parametrize("platform", ["macosx_14_0_x86_64", "macosx_14_0_universal2"])
def test_macos_audit_rejects_hidden_metadata_architecture(wheel_tools, tmp_path, monkeypatch, platform):
    """arm64 文件名不能掩盖 WHEEL 元数据额外宣称的 Intel 或通用架构。"""
    auditor = importlib.import_module("verify_macos_wheel")
    metadata = f"Wheel-Version: 1.0\nTag: cp311-abi3-macosx_14_0_arm64\nTag: cp311-abi3-{platform}\n"
    wheel = make_wheel(tmp_path, "macosx_14_0_arm64", {"cpu", "metal"},
                       {"mineru_llama_cpp-0.1.2.dist-info/WHEEL": metadata})
    monkeypatch.setattr(sys, "argv", ["verify_macos_wheel.py", str(wheel)])
    with pytest.raises(AssertionError, match=platform):
        auditor.main()


@pytest.mark.parametrize("architectures", ["x86_64", "arm64 x86_64"])
def test_macos_audit_rejects_non_arm64_binary(wheel_tools, tmp_path, monkeypatch, architectures):
    """即使 wheel 标签合法，Mach-O 中混入 Intel 切片也不能通过原生审计。"""
    auditor = importlib.import_module("verify_macos_wheel")
    monkeypatch.setattr(auditor.subprocess, "check_output", lambda *args, **kwargs: architectures)
    with pytest.raises(AssertionError, match="unexpected architectures"):
        auditor.inspect_binary(tmp_path / "libggml-cpu.so", "arm64")


def test_wheel_requires_configured_backend_modules(wheel_tools, tmp_path):
    """平台对应的必需模块仍需完整，例如 Linux 不能漏掉配置中的 Vulkan 模块。"""
    verifier, _ = wheel_tools
    wheel = make_wheel(tmp_path, "manylinux_2_28_aarch64", {"cpu"})
    with pytest.raises(ValueError, match="Missing vulkan MODULE"):
        verifier.verify([wheel], require_all=False)


def test_wheel_rejects_wrong_windows_architecture(wheel_tools, tmp_path):
    """ARM64 wheel 中的 AMD64 原生产物仍必须被架构检查拒绝。"""
    verifier, _ = wheel_tools
    platform = "win_arm64"
    wheel = make_wheel(tmp_path, platform, verifier.PLATFORMS[platform])
    with zipfile.ZipFile(wheel) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    extension = "mineru_llama_cpp/_mineru_llama_cpp.pyd"
    data = bytearray(contents[extension])
    struct.pack_into("<H", data, 68, 0x8664)
    contents[extension] = bytes(data)
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError, match="Wrong PE architecture"):
        verifier.verify([wheel], require_all=False)


def test_vulkan_dependencies_and_cpu_abi_remain_supported(wheel_tools):
    """Vulkan loader 仍为外部依赖，CPU 的 manylinux ABI 下限保持原规则。"""
    _, repair = wheel_tools
    repair.validate_report(
        {"libggml-vulkan.so": {"needed": ["libvulkan.so.1"], "versions": ["GLIBC_2.28", "GLIBCXX_3.4.24", "CXXABI_1.3.11"]}}
    )
    assert repair.GPU_RUNTIME_PREFIXES == ("libvulkan.so",)
    with pytest.raises(RuntimeError, match="ABI floor"):
        repair.validate_report({"libllama.so.0": {"needed": [], "versions": ["GLIBC_2.29"]}})


@pytest.mark.parametrize("symbol", ["__once_proxy", "_ZSt11__once_call", "_ZSt15__once_callable", "__cxa_throw"])
def test_private_cpp_runtime_exports_are_rejected(wheel_tools, symbol):
    """验证 wheel 审计会拒绝暴露私有 C++ 运行库状态的产物。"""
    _, repair = wheel_tools
    with pytest.raises(RuntimeError, match="private C\\+\\+ runtime symbols"):
        repair.validate_report({"libllama.so.0": {"needed": [], "versions": [], "runtime_exports": [symbol]}})
