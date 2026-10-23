# CI 编译缓存与构建目标验证

2026-10-24，本记录覆盖本地候选验证，不作为远端 CI 通过的凭据。

编译 job 通过 `.github/actions/build-cache` 安装 sccache 0.18.0，分别缓存
cibuildwheel 下载与编译对象。编译缓存以 OS、架构和工具链隔离；Xcode 26.6
与 16.4 使用不同命名空间。每个 job 的对象缓存上限为 1 GiB。
Linux 的启动器和对象目录通过 `/host` 映射到宿主，原有 Vulkan 配置和
wheel 修复命令保留；修复成功后在容器内输出统计并关闭缓存服务。

GitHub 的 ref 缓存隔离仍然适用。同一 PR 的后续运行可以复用该 PR 的缓存；
在 `main` 手动运行完整构建可准备默认分支缓存，供后续 PR/tag 恢复。
缓存不保存 CMake 构建目录或已生成的 wheel。

wheel 只请求 `_mineru_llama_cpp` 和 `llama-server` 两个构建目标。
`ggml_add_backend_library()` 已通过 `add_dependencies(ggml ${backend})`
将动态后端加入依赖图，因此 CPU、Metal/Vulkan 模块仍随运行库一起构建和安装。
包分发策略、ABI 审计和 Python 3.11–3.14 安装检查继续执行。

本机环境为 Apple M4、macOS 26.6.2、SDK 27.0、Python 3.14.4、CMake 4.4.4，
编译并行度为 4。下列结果是单次本机检查，不代表远端平台的性能保证。

| 检查 | 结果 |
| --- | --- |
| 工作流、缓存、发布与平台策略回归 | 141 passed，无跳过 |
| actionlint / ShellCheck / Bash 语法 / git diff --check | 通过 |
| 完整目标与精简目标 | Ninja 构建步骤从 356 降至 300 |
| 精简目标，首次使用空 sccache | 84.33 秒 |
| 清理 306 个构建文件后重建 | 5.93 秒，206 次命中、2 次未命中 |
| 完整移开构建目录后重新配置并重建 | 7.47 秒，210 次命中、5 次未命中 |
| wheel 文件清单 | 同为 23 个条目，包含 11 个 Mach-O 文件 |
| 非二进制内容对比 | 除 RECORD 外逐字节一致 |
| cp311-abi3、macOS 14 部署下限及动态库审计 | 通过 |
| 从独立目录安装 wheel 后加载 | 导入路径指向安装目录，CPU、Metal、BLAS 均可加载 |
| 安装包回归 | 117 passed，20 skipped |

全新配置时 sccache 统计中的 4 次预处理错误来自 CMake 对不支持的
`-mfp16-format=ieee`、SVE、MATMUL_INT8、SME 的能力探测；源码编译失败数为 0。
20 项跳过由 Linux 专用检查及缺少测试 GGUF 模型造成；本轮没有执行模型推理。

验证产物与日志位于 `/private/tmp/mineru-ci-optimization.59E7Wy/`：
`inventory-comparison.json`、`macos-audit.json`、`warm-cache-stats.json`、
`fresh-warm-cache-stats.json` 及对应构建日志。构建时因外置 ExFAT 卷写入异常，
将临时构建和缓存移到内置盘完成。原有子模块改动已恢复并逐文件核对。

Linux/Windows 的容器挂载、编译器启动器和真实缓存命中仍需远端 CI 验收。
