"""Audited SoftGpu native-memory boundary; generated source copies only."""
import re

SOFT_GPU = 'src/pc/render/soft_gpu.c'
# Inputs may be encoded guest addresses or native host buffers. Once resolved,
# all raster state and allocations remain native for the whole pixel loop.
BORDERS = {
    'SoftGpu_StateWords': 'words = GuestRuntime_ResolveData(words, 6 * sizeof(*words));',
    'SoftGpu_SetRecorder': 'if (wanted) wanted = GuestRuntime_ResolveData((void *)wanted, sizeof(*wanted));',
    'SoftGpu_Load': 'if (w > 0 && h > 0) pixels = GuestRuntime_ResolveData((void *)pixels, (size_t)w * (size_t)h * sizeof(*pixels));',
    'SoftGpu_Store': 'if (w > 0 && h > 0) pixels = GuestRuntime_ResolveData(pixels, (size_t)w * (size_t)h * sizeof(*pixels));',
    'SoftGpu_SetPrecise': 'if (count) vertices = GuestRuntime_ResolveData((void *)vertices, count * sizeof(*vertices));',
    'SoftGpu_Gp0': 'if (count) words = GuestRuntime_ResolveData((void *)words, count * sizeof(*words));',
    'SoftGpu_WideFrameView': 'pixels = GuestRuntime_ResolveData(pixels, sizeof(*pixels)); out_x = GuestRuntime_ResolveData(out_x, sizeof(*out_x)); out_w = GuestRuntime_ResolveData(out_w, sizeof(*out_w));',
    'SoftGpu_WideFrame': 'pixels = GuestRuntime_ResolveData(pixels, sizeof(*pixels)); out_x = GuestRuntime_ResolveData(out_x, sizeof(*out_x)); out_w = GuestRuntime_ResolveData(out_w, sizeof(*out_w));',
    'SoftGpu_StateData': 'size = GuestRuntime_ResolveData(size, sizeof(*size));',
}

def adapt_soft_gpu(text):
    for name, statement in BORDERS.items():
        pattern = r'(^[^\n]*\b' + name + r'\([^;\n]*\)\n\{)'
        text, count = re.subn(pattern, lambda m: m[0] + '\n    ' + statement, text, flags=re.M)
        if count != 1: raise ValueError('SoftGpu boundary signature changed: ' + name)
    return '#include "pc/guest/translated_runtime.h"\n' + text
