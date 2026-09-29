#!/usr/bin/env python3
"""Package the Android build (libmain.so, the loader, and libgame.so, the
game) as an installable APK.

Called by build_game32.py --target android-<abi> after the link; it can also
be run on its own: package_android.py <build dir> <abi>. Uses only the JDK
(javac) and the Android SDK's own tools, no Gradle: SDL's Java shell
(org.libsdl.app, from the same SDL release as libSDL3.so; build_android_deps.py)
is compiled against the SDK's android.jar and dexed with d8, aapt2 links the
manifest, the native libraries go in lib/<abi>/, and the APK is aligned
(zipalign) and signed (apksigner) with a debug key kept under tmp/, never in
the repository. The activity is SDL's own SDLActivity: it loads libSDL3.so
and libmain.so and calls SDL_main (src/pc/platform/android_loader.c), which
loads libgame.so at its link address. The build's id, commit and symbol
table go in assets/build/, and the shipped mods and language packs under
assets/build/files/ with their list in build/files.txt
(src/pc/platform/android.c unpacks them).

Output: <build>/memories-<abi>.apk. notes/pc-build.md, "Android"."""
import glob, os, shutil, subprocess, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_android_deps

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACKAGE = "org.yfmredecomp.game"
LABEL = "YFM Re-Decomp"
KEYSTORE = os.path.join(ROOT, "tmp", "pc", "android-deps", "debug.keystore")
TARGET_SDK = 35

MANIFEST = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{PACKAGE}" android:versionCode="1" android:versionName="m1">
    <uses-feature android:glEsVersion="0x00020000" />
    <uses-feature android:name="android.hardware.touchscreen" android:required="false" />
    <uses-feature android:name="android.hardware.gamepad" android:required="false" />
    <application android:label="{LABEL}" android:hasCode="true" android:allowBackup="false"
        android:extractNativeLibs="true" android:hardwareAccelerated="true"
        android:theme="@android:style/Theme.NoTitleBar.Fullscreen">
        <activity android:name="org.libsdl.app.SDLActivity" android:exported="true"
            android:configChanges="layoutDirection|locale|orientation|uiMode|screenLayout|screenSize|smallestScreenSize|keyboard|keyboardHidden|navigation"
            android:screenOrientation="sensorLandscape" android:launchMode="singleInstance"
            android:preferMinimalPostProcessing="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""


def sdk():
    path = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not path or not os.path.isdir(path):
        sys.exit("ANDROID_SDK_ROOT is not set (notes/pc-build.md, \"Android\")")
    return path


def newest(pattern):
    found = sorted(glob.glob(pattern), key=lambda path: [int(part) if part.isdigit() else part
                                                         for part in os.path.basename(path).replace("-", ".").split(".")])
    if not found:
        sys.exit(f"not found: {pattern}")
    return found[-1]


def tool(build_tools, name):
    """A build-tools program: name.exe or name.bat on Windows, name elsewhere."""
    for suffix in ((".exe", ".bat") if sys.platform == "win32" else ("",)):
        if os.path.exists(os.path.join(build_tools, name + suffix)):
            return os.path.join(build_tools, name + suffix)
    sys.exit(f"{name} is not in {build_tools}")


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        sys.exit(f"{' '.join(command[:4])} ...\n{result.stdout}\n{result.stderr}")
    return result.stdout


def program_files(build, folders):
    """The files under <build>/<folder> for each of `folders`, as assets
    under build/files/, and build/files.txt listing them (one relative path
    a line): an app cannot list its own assets, and android.c unpacks each
    one listed into the program directory."""
    assets, names = {}, []
    for folder in folders:
        for path in sorted(glob.glob(os.path.join(build, folder, "**", "*"), recursive=True)):
            if os.path.isfile(path):
                relative = os.path.relpath(path, build).replace(os.sep, "/")
                assets[f"build/files/{relative}"] = path
                names.append(relative)
    index = os.path.join(build, "files.txt")
    with open(index, "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(name + "\n" for name in names)
    assets["build/files.txt"] = index
    return assets


def package(build, abi, library, game, assets):
    build_tools = newest(os.path.join(sdk(), "build-tools", "*"))
    android_jar = os.path.join(newest(os.path.join(sdk(), "platforms", "android-*")), "android.jar")
    work = os.path.join(build, "apk")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "classes"))
    os.makedirs(os.path.join(work, "dex"))
    # SDL's Java shell, from the SDL release libSDL3.so was built from.
    sources = sorted(glob.glob(os.path.join(build_android_deps.OUT, "java", "**", "*.java"), recursive=True))
    javac = shutil.which("javac") or sys.exit("javac is not on PATH (a JDK, 17 or later)")
    run([javac, "--release", "11", "-nowarn", "-encoding", "UTF-8", "-classpath", android_jar,
         "-d", os.path.join(work, "classes"), *sources])
    classes = sorted(glob.glob(os.path.join(work, "classes", "**", "*.class"), recursive=True))
    run([tool(build_tools, "d8"), "--release", "--min-api", str(build_android_deps.API), "--lib", android_jar,
         "--output", os.path.join(work, "dex"), *classes])
    with open(os.path.join(work, "AndroidManifest.xml"), "w", encoding="utf-8") as handle:
        handle.write(MANIFEST)
    unaligned = os.path.join(work, "unaligned.apk")
    run([tool(build_tools, "aapt2"), "link", "-o", unaligned, "-I", android_jar, "--manifest",
         os.path.join(work, "AndroidManifest.xml"), "--min-sdk-version", str(build_android_deps.API),
         "--target-sdk-version", str(TARGET_SDK)])
    deps_lib = os.path.join(build_android_deps.OUT, abi, "lib")
    with zipfile.ZipFile(unaligned, "a", zipfile.ZIP_DEFLATED) as apk:
        apk.write(os.path.join(work, "dex", "classes.dex"), "classes.dex")
        apk.write(library, f"lib/{abi}/libmain.so")
        apk.write(game, f"lib/{abi}/libgame.so")
        for name, path in sorted(assets.items()):
            apk.write(path, f"assets/{name}")
        apk.write(os.path.join(deps_lib, "libSDL3.so"), f"lib/{abi}/libSDL3.so")
    aligned = os.path.join(work, "aligned.apk")
    run([tool(build_tools, "zipalign"), "-p", "-f", "4", unaligned, aligned])
    if not os.path.exists(KEYSTORE):
        home = os.environ.get("JAVA_HOME")
        keytool = (shutil.which("keytool") or (home and shutil.which("keytool", path=os.path.join(home, "bin"))) or
                   sys.exit("keytool is not on PATH or in $JAVA_HOME/bin (a JDK)"))
        run([keytool, "-genkeypair", "-keystore", KEYSTORE, "-alias", "androiddebugkey", "-storepass", "android",
             "-keypass", "android", "-dname", "CN=Android Debug,O=Android,C=US", "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10000"])
    apk_path = os.path.join(build, f"memories-{abi}.apk")
    run([tool(build_tools, "apksigner"), "sign", "--ks", KEYSTORE, "--ks-pass", "pass:android", "--key-pass",
         "pass:android", "--out", apk_path, aligned])
    print(f"{apk_path}: {PACKAGE}, lib/{abi}/libmain.so + libgame.so + libSDL3.so, {len(assets)} assets")
    return apk_path


if __name__ == "__main__":
    build = sys.argv[1]
    with open(os.path.join(build, "buildid")) as handle:
        build_id = handle.read().strip()
    assets = {"build/buildid": os.path.join(build, "buildid"), "build/commit": os.path.join(build, "commit"),
              f"build/symbols/{build_id}.txt": os.path.join(build, "symbols", f"{build_id}.txt")}
    assets.update(program_files(build, ("mods", "languages")))
    package(build, sys.argv[2], os.path.join(build, "libmain.so"), os.path.join(build, "libgame.so"), assets)
