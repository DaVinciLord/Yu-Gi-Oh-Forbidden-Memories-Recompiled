#!/usr/bin/env python3
"""Fetch and build the Android game library's dependencies, per ABI.

The Android build (build_game32.py --target android-<abi>) links the same
libraries as the desktop builds, built from the same pinned archives with the
NDK: SDL3 (a shared libSDL3.so that SDL's Java shell loads, and the Java
sources of that shell for the APK), and static libpng and FreeType. zlib is
the NDK's own libz.so, which every Android system has. Fontconfig does not
exist on Android: src/pc/compat/android/fontconfig/fontconfig.h stands in
for the few calls the port makes, with the system fonts.

Output: tmp/pc/android-deps/<abi>/{lib,include}. Needs the NDK
(ANDROID_NDK_ROOT, else the newest under $ANDROID_SDK_ROOT/ndk), cmake and
ninja (notes/pc-build.md, "Android")."""
import glob, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_linux_sysroot   # SDL3's pinned source archive, shared with Linux
import build_win32_deps      # libpng's and FreeType's pinned archives, shared with Windows

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tmp", "pc", "android-deps")
# The Android API level every ABI is built for: 24 (Android 7.0), so that the
# one real 32-bit ARM system image (API 25) can run the armeabi-v7a build.
# What the port needs from later ones has a fallback in
# src/pc/compat/android.h.
API = 24
# ABI -> clang target triple (without the API level).
TRIPLES = {"x86": "i686-linux-android", "armeabi-v7a": "armv7a-linux-androideabi"}
# The ABIs the game builds for, with their own compiler flags: the indirect
# branch thunks (src/pc/guest/branch_thunks.c) and the rest. x86 reuses every
# i386 piece of the desktop port.
READY = {"x86": {"thunks": ["-mretpoline-external-thunk"], "flags": ["-fsigned-char"]}}
# What an ABI still needs before it builds (notes/pc-build.md, "Android").
NOT_READY = {"armeabi-v7a": "not yet: needs the ARM branch thunks (-mharden-sls=blr), the ARM fault handler, "
                            "setjmp and the stack switch in ARM assembly (milestone M2)"}


def ndk():
    """The NDK: ANDROID_NDK_ROOT (or ANDROID_NDK_HOME), else the newest one
    the SDK holds."""
    for name in ("ANDROID_NDK_ROOT", "ANDROID_NDK_HOME"):
        if os.environ.get(name) and os.path.isdir(os.environ[name]):
            return os.environ[name]
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    found = sorted(glob.glob(os.path.join(sdk, "ndk", "*"))) if sdk else []
    if not found:
        sys.exit("no Android NDK: set ANDROID_NDK_ROOT, or ANDROID_SDK_ROOT with an ndk/ folder "
                 "(notes/pc-build.md, \"Android\")")
    return found[-1]


def llvm_bin():
    """The NDK's clang and LLVM tools."""
    return glob.glob(os.path.join(ndk(), "toolchains", "llvm", "prebuilt", "*", "bin"))[0]


def cmake(abi, name, source, *options):
    build = os.path.join(OUT, "build", abi, name)
    prefix = os.path.join(OUT, abi)
    subprocess.run(["cmake", "-S", source, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_TOOLCHAIN_FILE=" + os.path.join(ndk(), "build", "cmake", "android.toolchain.cmake"),
                    f"-DANDROID_ABI={abi}", f"-DANDROID_PLATFORM=android-{API}", "-DANDROID_ARM_MODE=arm",
                    f"-DCMAKE_INSTALL_PREFIX={prefix}", f"-DCMAKE_PREFIX_PATH={prefix}",
                    f"-DCMAKE_FIND_ROOT_PATH={prefix}", "-DCMAKE_POLICY_VERSION_MINIMUM=3.5", *options], check=True)
    subprocess.run(["cmake", "--build", build, "--target", "install"], check=True)


def main(abi):
    if abi not in TRIPLES:
        sys.exit(f"unknown Android ABI {abi}; known: {', '.join(TRIPLES)}")
    stamp = os.path.join(OUT, abi, ".complete")
    if os.path.exists(stamp):
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fetch_tools
    fetch_tools.ensure("cmake")
    fetch_tools.ensure("ninja")
    cmake(abi, "libpng", build_win32_deps.fetch("libpng"), "-DPNG_SHARED=OFF", "-DPNG_STATIC=ON", "-DPNG_TESTS=OFF",
          "-DPNG_TOOLS=OFF", "-DPNG_FRAMEWORK=OFF", "-DPNG_ARM_NEON=off")
    cmake(abi, "freetype", build_win32_deps.fetch("freetype"), "-DBUILD_SHARED_LIBS=OFF", "-DFT_DISABLE_ZLIB=ON",
          "-DFT_DISABLE_BZIP2=ON", "-DFT_DISABLE_PNG=ON", "-DFT_DISABLE_HARFBUZZ=ON", "-DFT_DISABLE_BROTLI=ON")
    build_linux_sysroot.fetch_sdl()
    cmake(abi, "sdl", build_linux_sysroot.SDL_SOURCE, "-DSDL_SHARED=ON", "-DSDL_STATIC=OFF", "-DSDL_TEST_LIBRARY=OFF",
          "-DSDL_TESTS=OFF", "-DSDL_EXAMPLES=OFF")
    # SDL's Java shell (org.libsdl.app), compiled into the APK by
    # build_game32.py: it must be the Java of the same SDL release.
    java = os.path.join(OUT, "java")
    if not os.path.isdir(java):
        shutil.copytree(os.path.join(build_linux_sysroot.SDL_SOURCE, "android-project", "app", "src", "main", "java"),
                        java)
    with open(stamp, "w") as handle:
        handle.write("done\n")
    print(f"android deps ({abi}): {os.path.join(OUT, abi)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "x86")
