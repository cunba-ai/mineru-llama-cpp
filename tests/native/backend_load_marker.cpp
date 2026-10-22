#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdio>
#include <cstdlib>

#ifdef _WIN32
#define BACKEND_EXPORT __declspec(dllexport)
#else
#define BACKEND_EXPORT __attribute__((visibility("default")))
#endif

// Record an attempted optional backend probe without depending on GPU hardware.
extern "C" BACKEND_EXPORT int ggml_backend_score() {
    if (const char * path = std::getenv("MINERU_TEST_BACKEND_MARKER")) {
        if (FILE * file = std::fopen(path, "a")) {
            std::fputs("probed\n", file);
            std::fclose(file);
        }
    }
    return 0;
}

extern "C" BACKEND_EXPORT void * ggml_backend_init() { return nullptr; }

PyMODINIT_FUNC PyInit__backend_load_marker() {
    PyErr_SetString(PyExc_RuntimeError, "Load this fixture through ggml");
    return nullptr;
}
