# Python 3.11 abi3 与五平台支持范围验证

本轮将安装下限与稳定 ABI 基线统一提升到 Python 3.11，停止 macOS Intel、
Rosetta x86_64 和 universal2 的 wheel 与源码构建支持。现有公开 API 和模型调用行为保持不变。
项目版本号暂未变更，本轮候选不是新的正式发布；历史 0.1.5 产物继续保留原标签和支持范围。

## 发布矩阵

每个平台发布一个 `cp311-abi3` wheel，复用同一产物在普通 GIL 版 CPython 3.11–3.14 安装测试。

| 平台 | 平台标签 | 后端 |
|---|---|---|
| Linux x86_64 | `manylinux_2_28_x86_64` | CPU、Vulkan |
| Linux aarch64 | `manylinux_2_28_aarch64` | CPU、Vulkan |
| Windows AMD64 | `win_amd64` | CPU、Vulkan |
| Windows ARM64 | `win_arm64` | CPU、Vulkan |
| macOS arm64 | `macosx_14_0_arm64` | CPU、Metal |

macOS 14、Linux glibc/CPU 指令集要求以及其他后端策略沿用原规则。
macOS 架构约束检查编译目标，显式 arm64 目标优先于宿主处理器信息。
五平台审计拒绝 Intel/universal2 及压缩标签中混入的这些架构；macOS 专项审计同时检查
WHEEL 元数据和所有 Mach-O 切片。

## 本机验证

本地归档位于 `build/python311-validation/`。原生构建及隔离 Python 环境位于该目录
`runtime-root.txt` 指向的系统临时目录，避免外置盘创建虚拟环境时的文件系统错误。

| 检查 | 结果与证据 |
|---|---|
| 发布、平台与 CMake 策略 | 109 passed；包含完整/子集发布、旧 ABI 拒绝和目标架构优先级 |
| macOS arm64 wheel | 已构建 `mineru_llama_cpp-0.1.5-cp311-abi3-macosx_14_0_arm64.whl`；`candidate-build.log` |
| 稳定 ABI | 严格审计通过，基线 3.11，无非稳定或未来 ABI 符号；`abi3-audit.json` |
| Mach-O 与运行库 | 11 个 Mach-O 均为 arm64，部署版本及动态库依赖审计通过；`macos-audit.json` |
| 同一 wheel 跨 Python 安装 | 3.11、3.12、3.13、3.14 各 128 passed、20 skipped，安装路径及 smoke 见 `python-3.*-contracts.log` 和 `cross-python.json` |
| 不支持的源码目标 | 实际 CMake 配置拒绝 x86_64 与 arm64+x86_64，在 llama.cpp 配置前失败；`configure-rejection.json` |
| 工作流语法 | `actionlint` 通过 |

真实模型回归、基线输出比较、源码包元数据以及五平台 CI 结果将在完成后补充。
仅有构建或模块加载结果不代表目标 GPU 推理和完整文档提取已验证。

## 历史记录

[原六平台验证记录](abi3-backends-validation.md)保留历史 wheel、Python 3.10 和 Intel Mac
测试结果，不将旧结果改写为新支持矩阵的验证证据。
