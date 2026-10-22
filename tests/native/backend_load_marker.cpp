#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdio>
#include <cstdlib>

#ifdef _WIN32
#define BACKEND_EXPORT __declspec(dllexport)
#else
#define BACKEND_EXPORT __attribute__((visibility("default")))
#endif

// 记录可选后端探测行为，无需实际 GPU 硬件。
extern "C" BACKEND_EXPORT int ggml_backend_score() {
    if (const char * path = std::getenv("MINERU_TEST_BACKEND_MARKER")) {
        if (FILE * file = std::fopen(path, "a")) {
            std::fputs("probed\n", file);
            std::fclose(file);
        }
    }
    return 0;
}

// 标记模块不提供真实后端，初始化始终返回空指针。
extern "C" BACKEND_EXPORT void * ggml_backend_init() { return nullptr; }

// 拒绝直接导入，确保测试通过 ggml 的加载入口调用探针。
PyMODINIT_FUNC PyInit__backend_load_marker() {
    PyErr_SetString(PyExc_RuntimeError, "Load this fixture through ggml");
    return nullptr;
}
