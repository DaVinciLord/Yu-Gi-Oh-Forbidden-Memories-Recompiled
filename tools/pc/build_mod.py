#!/usr/bin/env python3
"""Build a code mod: every .c in its directory, merged into one <library>.o.

The object runs on both the Linux and the Windows game, which load it with
their own loader (src/pc/mods/object_loader.c), so a mod is built once, on
either system, with the same result. That only holds because the flags below
close every gap between the two 32-bit ABIs (notes/portable-mods-plan.md):

  -fno-pic -fno-common            plain relocations only; no GOT, no COMMON
  -fno-stack-protector            the canary lives in Linux thread storage
  -march=i686 -mno-sse            x87 floating point, no SSE alignment needs
  -mstackrealign                  every function aligns its own stack to 16:
                                  Windows only promises 4 on the way in, and
                                  the Linux game (SSE2) needs 16 on the way
                                  out, or it faults on the first movaps
  -fstack-clash-protection        touches each stack page on the way down,
                                  as Windows' guard page requires
  -ffreestanding -nostdinc        no system C library: the SDK's headers
                                  (src/pc/mods/sdk) declare what the game lends
  -mretpoline-external-thunk      (clang; GCC: -mindirect-branch=thunk-extern
                                  -mindirect-branch-register) indirect calls go
                                  through the game's __x86_indirect_thunk_*,
                                  so a call through a guest function pointer
                                  works without DEP, as in the game's own code

The compiler is clang (on Windows, llvm-mingw's, targeting i386 Linux ELF),
else gcc -m32. MEMORIES_MOD_CC names another. The game's headers come from
src/ (in this repository) or from the sdk/include the game ships beside it,
where this script is sdk/tools/build_mod.py.

The names the mod leaves undefined are checked against what the game
provides: in the repository, each game build (--game, default both); beside
a game, the list its SDK was shipped with. A mod that would load on one
system and not the other fails here rather than in the game.

Objects are kept in tmp/pc/mod-build/<mod>-<key>, where the key is a digest
of everything that goes into the object: the compiler and linker (their
files), the flags, this script, and each source as the preprocessor sees
it, so with every header it includes (inputs_key). tmp is shared by every
checkout of the repository (the worktrees link it), and an object is reused
only where its inputs are the same, never because it is newer. A memo in
tmp/pc/mod-build/.memo finds the key again without the preprocessor while
none of the files it read has changed."""
import argparse, concurrent.futures, filecmp, functools, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
import build_process

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# In the repository, or the copy in the sdk/ directory beside a game
# (sdk/tools/build_mod.py, with the headers in sdk/include).
SHIPPED = not os.path.isdir(os.path.join(ROOT, "src/pc/mods/sdk"))
SDK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLVM_MINGW = os.path.join(ROOT, "tmp/pc/llvm-mingw/bin")
CACHE = os.path.join(ROOT, "tmp", "pc", "mod-build")
GAME_BUILDS = [SDK] if SHIPPED else [os.path.join(ROOT, "tmp/pc/game32"), os.path.join(ROOT, "tmp/pc/win32")]
FLAGS = ["-std=gnu11", "-O2", "-g", "-fno-pic", "-fno-pie", "-fno-common", "-fno-stack-protector",
         "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fstack-clash-protection",
         "-march=i686", "-mno-sse", "-mno-mmx", "-ffreestanding", "-nostdinc",
         "-DMEMORIES_PC", "-DMEMORIES_MOD", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Wall",
         "-Wno-unused-function", "-Wno-missing-braces"]
CLANG_FLAGS = ["--target=i386-pc-linux-gnu", "-mstackrealign", "-mretpoline-external-thunk"]
GCC_FLAGS = ["-m32", "-mstackrealign", "-mincoming-stack-boundary=2", "-mindirect-branch=thunk-extern",
             "-mindirect-branch-register"]


def tool(name):
    """A program from PATH, or from the llvm-mingw this repository fetches."""
    found = shutil.which(name)
    if not found and os.path.exists(os.path.join(LLVM_MINGW, name + (".exe" if os.name == "nt" else ""))):
        found = os.path.join(LLVM_MINGW, name)
    return found


def compiler():
    """(command, flags, linker command) for building an i386 ELF object."""
    path, clang, linker = programs()
    return [path], (CLANG_FLAGS if clang else GCC_FLAGS) + ["-isystem", builtin_headers(path, clang)], list(linker)


def programs():
    """(compiler, whether it is clang, linker command), found without
    starting either: the cache keys need only their files."""
    return find_programs(os.environ.get("MEMORIES_MOD_CC"))


@functools.lru_cache(maxsize=None)
def find_programs(named):
    candidates = [named] if named else [os.path.join(LLVM_MINGW, "clang"), "clang", "gcc"]
    for candidate in candidates:
        path = candidate if os.path.isabs(candidate) and os.path.exists(candidate) else tool(candidate)
        if not path:
            continue
        if "clang" in os.path.basename(path):
            # The lld that came with this clang. Windows needs the .exe
            # spelled out: "ld.lld" already has an extension, so it adds none.
            beside = os.path.join(os.path.dirname(path), "ld.lld")
            linker = next((p for p in (beside + ".exe", beside) if os.path.exists(p)), None) or tool("ld.lld")
            if not linker:
                continue  # clang without lld cannot merge the objects; try the next compiler
            return path, True, (linker, "-r")
        return path, False, (tool("ld") or "ld", "-m", "elf_i386", "-r")
    sys.exit("build_mod: no compiler found; install clang or gcc (with 32-bit support), or set MEMORIES_MOD_CC")


@functools.lru_cache(maxsize=None)
def builtin_headers(path, clang):
    """The compiler's own headers (stddef.h, stdarg.h and the like)."""
    if clang:
        resource = subprocess.run([path, "-print-resource-dir"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        return os.path.join(resource, "include")
    return subprocess.run([path, "-m32", "-print-file-name=include"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def headers():
    """The SDK's C library, then the game's headers."""
    if SHIPPED:
        return ["-isystem", os.path.join(SDK, "include", "libc"), "-I", os.path.join(SDK, "include")]
    return ["-isystem", os.path.join(ROOT, "src/pc/mods/sdk"), "-I", os.path.join(ROOT, "src")]


def run(command):
    result = build_process.run(command)
    if result.returncode:
        sys.exit(f"build_mod: {' '.join(command[:3])} ... failed\n{result.stdout}{result.stderr}")
    return result.stdout


def provided(build):
    """The names a game build lends mods: its export table and the C
    library list, or None if that build is not there. A game build in the
    repository has its generated table; an SDK beside a game has the list
    it was shipped with (exports.txt)."""
    table, shipped = os.path.join(build, "mod_exports.c"), os.path.join(build, "exports.txt")
    if os.path.exists(table):
        with open(table) as handle:
            names = set(re.findall(r'^    \{"([^"]+)"', handle.read(), re.M))
        return names | libc_names()
    if os.path.exists(shipped):
        with open(shipped) as handle:
            return set(handle.read().split())
    return None


def libc_names():
    """The C library list in src/pc/mods/mod_libc.c."""
    with open(os.path.join(ROOT, "src/pc/mods/mod_libc.c")) as handle:
        # F(name), or AS(name, function) for one the host implements itself.
        return set(re.findall(r"\b(?:F\(|AS\()(\w+)\b", handle.read()))


def library_name(directory):
    """The object's file name, relative to the mod's directory, by the game's
    own rule (read_manifest in src/pc/mods/mods.c): "library" as written
    when it has a '.' anywhere in it, else with ".o" added. The game loads
    no code for a mod without "library", so neither is one built."""
    manifest = os.path.join(directory, "mod.json")
    if not os.path.exists(manifest):
        sys.exit(f"{directory}: no mod.json (notes/modding.md)")
    # utf-8-sig: a manifest saved with a byte order mark, as the game allows.
    with open(manifest, encoding="utf-8-sig") as handle:
        name = json.load(handle).get("library")
    if not name:
        sys.exit(f'{manifest}: the mod has C sources but no "library": the game would load none of its code. '
                 f'Add "library": "{os.path.basename(os.path.normpath(directory))}"')
    return name if "." in name else name + ".o"


def identity(program):
    """A compiler or linker as the keys know it: its file's name, size and
    time, as ccache's compiler_check=mtime does, so no process starts. The
    same file through another worktree's junction is the same file."""
    found = program if os.path.dirname(program) else shutil.which(program)
    for candidate in (found, found + ".exe") if found else ():
        if os.path.isfile(candidate):
            real = os.path.realpath(candidate)
            stat = os.stat(real)
            return f"{os.path.basename(real)} {stat.st_size} {stat.st_mtime_ns}"
    sys.exit(f"build_mod: {program} not found")


def portable(text):
    """`text` with this checkout's root spelled the same in every checkout."""
    for root in sorted({ROOT, ROOT.replace("\\", "/"), ROOT.replace("/", "\\")}, key=len, reverse=True):
        text = text.replace(root, "<root>")
    return text


def file_digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def settings_digest(directory, extra_flags):
    """What both of an object's digests start from: this script, the
    compiler and linker, the flags and the library name."""
    path, clang, linker = programs()
    flags = FLAGS + (CLANG_FLAGS if clang else GCC_FLAGS) + headers() + list(extra_flags)
    digest = hashlib.sha256()
    with open(os.path.abspath(__file__), "rb") as handle:
        script = hashlib.sha256(handle.read().replace(b"\r\n", b"\n")).hexdigest()   # either checkout's line ends
    for label, text in (("script", script), ("compiler", identity(path)),
                        ("linker", identity(linker[0])), ("flags", portable("\n".join(flags))),
                        ("library", library_name(directory))):
        digest.update(f"{label}\0{text}\0".encode("utf-8", "surrogateescape"))
    return digest


# A line marker in preprocessed C: # <line> "<file>" <flags>. The key keeps
# the line, which the debug information records, and drops the file, which
# names the checkout; the file goes in the memo's list instead.
LINE_MARKER = re.compile(r'^(#(?: line)? \d+) "((?:[^"\\]|\\.)*)"', re.M)


def inputs_key(directory, sources, extra_flags=()):
    """The key an object is kept under in tmp/pc/mod-build: settings_digest
    and each source after the preprocessor, which takes in every header it
    includes from wherever it is. Returns (key, the files the preprocessor
    read, when it started). No time goes into the key: another checkout
    sharing tmp gets the same object only when it has the same inputs."""
    cc, cc_flags, _ = compiler()
    flags = FLAGS + cc_flags + headers() + list(extra_flags)
    digest = settings_digest(directory, extra_flags)
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(len(sources)) as pool:
        preprocessed = list(pool.map(lambda source: run(cc + flags + ["-E", source]), sources))
    read = set()
    for source, text in zip(sources, preprocessed):
        for match in LINE_MARKER.finditer(text):
            # Not <built-in> or <command line>, nor the working directory
            # GCC names with -g ("/path//").
            path = os.path.normpath(os.path.abspath(re.sub(r"\\(.)", r"\1", match.group(2))))
            if not match.group(2).startswith("<") and os.path.isfile(path):
                read.add(path)
        digest.update(os.path.basename(source).encode() + b"\0")
        digest.update(LINE_MARKER.sub(r"\1", text).encode("utf-8", "surrogateescape") + b"\0")
    return digest.hexdigest(), read, started


# The memo: the key inputs_key gave, remembered with the content of every
# file the preprocessor read, so that a build with none of them changed
# finds the key again without starting the preprocessor (as ccache's direct
# mode). It is only a way to the key, never to an object: a memo that does
# not hold sends the build to inputs_key.
MEMOS = os.path.join(CACHE, ".memo")


def memo_folder(directory, sources, extra_flags):
    """Where the memos for these sources are: named by settings_digest, the
    sources and the names of the headers that could be included, so that a
    new header that would be found first (and was never read) also misses."""
    digest = settings_digest(directory, extra_flags)
    for source in sources:
        digest.update(os.path.basename(source).encode() + b"\0" + file_digest(source).encode() + b"\0")
    include = os.path.join(SDK, "include") if SHIPPED else os.path.join(ROOT, "src")
    names = glob.glob(os.path.join(include, "**", "*.h"), recursive=True)
    names += glob.glob(os.path.join(directory, "**", "*.h"), recursive=True)
    listing = "\n".join(sorted(portable(os.path.abspath(name)) for name in names))
    digest.update(listing.encode("utf-8", "surrogateescape"))
    return os.path.join(MEMOS, f"{os.path.basename(os.path.abspath(directory))}-{digest.hexdigest()[:24]}")


def recall(folder):
    """The key of a memo in `folder` whose files are all as they were."""
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(path, encoding="utf-8") as handle:
                memo = json.load(handle)
            if all(file_digest(name.replace("<root>", ROOT)) == digest for name, digest in memo["files"].items()):
                return memo["key"]
        except (OSError, ValueError, KeyError, AttributeError):
            continue   # a file gone, or a memo from another version of this script
    return None


def remember(folder, key, read, started):
    files = {}
    for path in sorted(read):
        if os.path.getmtime(path) >= started:
            return   # changed while the preprocessor ran: the key may not be of what is there now
        files[portable(path)] = file_digest(path)
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"key": key, "files": files}, stream, indent=0)
        os.replace(temporary, os.path.join(folder, key[:16] + ".json"))
    except OSError:
        # Windows will not replace a file another build is reading (recall),
        # and that file is this same memo. A memo is only a shortcut.
        try:
            os.remove(temporary)
        except OSError:
            pass


def compile_object(sources, output, objects_dir, extra_flags=()):
    """Compile `sources` with the mod flags (then `extra_flags`, which the
    loader's tests use to make broken objects) and merge them into `output`."""
    cc, cc_flags, linker = compiler()
    objects = []
    os.makedirs(objects_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    for source in sources:
        obj = os.path.join(objects_dir, os.path.basename(source) + ".o")
        run(cc + FLAGS + cc_flags + headers() + [*extra_flags, "-c", source, "-o", obj])
        objects.append(obj)
    run(linker + ["-o", output] + objects)
    return output


def build(directory, out_dir=None, objects_dir=None, extra_flags=(), games=GAME_BUILDS, quiet=False):
    """Build the mod in `directory`; returns the path of its .o, or None when
    it has no C (a data-only mod). The object is built once per inputs_key,
    into tmp/pc/mod-build/<mod>-<key>, and copied to `out_dir` (default: the
    mod's directory) when what is there differs. It is checked against the
    game builds every time, reused or not: what a game lends comes from the
    game's own sources, which the key does not cover."""
    sources = sorted(glob.glob(os.path.join(directory, "*.c")))
    if not sources:
        return None
    name = library_name(directory)
    output = os.path.join(out_dir or directory, name)
    extra_flags = ["-I", directory, *extra_flags]
    memo = memo_folder(directory, sources, extra_flags)
    key = recall(memo)
    if key is None:
        key, read, started = inputs_key(directory, sources, extra_flags)
        remember(memo, key, read, started)
    entry = os.path.join(CACHE, f"{os.path.basename(os.path.abspath(directory))}-{key[:16]}")
    cached = os.path.join(entry, name)
    try:
        if os.path.exists(cached):
            try:
                with open(cached + ".undefined") as handle:
                    undefined = set(handle.read().split())
            except OSError:
                undefined = None
            check(cached, games, undefined)
            state = "up to date"
        else:
            publish(entry, name, sources, objects_dir, extra_flags, games)
            state = f"{len(sources)} source{'s' if len(sources) != 1 else ''}"
    except SystemExit:
        if os.path.exists(output):
            os.remove(output)   # not left there to pass for this mod's object
        raise
    if not os.path.exists(output) or not filecmp.cmp(cached, output, shallow=False):
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)   # "library": "sub/rules"
        shutil.copyfile(cached, output)
    if not quiet:
        print(f"{output}: {state} ({os.path.relpath(entry, ROOT)})")
    return output


def publish(entry, name, sources, objects_dir, extra_flags, games):
    """Build the object in a folder of its own beside `entry`, check it, and
    rename the folder to `entry`: a folder there is always a whole object
    that passed, with the names it leaves undefined beside it
    (<library>.undefined). When another checkout gets there first with the
    same key, its object is the same and this one is dropped."""
    os.makedirs(CACHE, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=f".{os.path.basename(entry)}-", dir=CACHE)
    try:
        staged = os.path.join(stage, "object")
        output = compile_object(sources, os.path.join(staged, name), objects_dir or os.path.join(stage, "parts"),
                                extra_flags)
        undefined = undefined_names(output)
        check(output, games, undefined)
        with open(output + ".undefined", "w") as handle:
            handle.writelines(symbol + "\n" for symbol in sorted(undefined))
        for attempt in range(40):
            try:
                os.rename(staged, entry)
                return
            except OSError:
                if os.path.exists(os.path.join(entry, name)):
                    return
                if os.path.isdir(entry):
                    shutil.rmtree(entry, ignore_errors=True)   # emptied by hand: not an object
                if attempt == 39:
                    raise
                time.sleep(0.25)   # a virus scanner still holding the new file (Windows)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def undefined_names(output):
    """The names the object leaves for the game to lend."""
    reader = tool("llvm-readelf") or tool("readelf")
    undefined = set()
    for line in run([reader, "-sW", output]).splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[6] == "UND" and parts[4] != "WEAK":
            undefined.add(parts[7])
    return undefined


def check(output, games, undefined=None):
    """What the object leaves undefined must be there on every game build."""
    if undefined is None:
        undefined = undefined_names(output)
    for bad, why in (("_GLOBAL_OFFSET_TABLE_", "it is position-independent"),
                     ("__stack_chk_fail", "it uses the stack protector"),
                     ("__stack_chk_fail_local", "it uses the stack protector")):
        if bad in undefined:
            sys.exit(f"build_mod: {output}: {why}; build it with the flags in this script")
    for build in games:
        names = provided(build)
        if names is None:
            continue
        missing = sorted(undefined - names)
        if missing:
            try:
                build = os.path.relpath(build, ROOT)
            except ValueError:
                pass   # on another drive (Windows)
            sys.exit(f"build_mod: {output} needs names the game at {build} "
                     f"does not provide: {' '.join(missing)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", help="the mod's directory (its mod.json and .c files)")
    parser.add_argument("--out", help="where the .o goes (default: the mod's directory)")
    parser.add_argument("--game", action="append",
                        help="a game build directory to check the mod's names against (repeatable; "
                             "default: tmp/pc/game32 and tmp/pc/win32 when they exist)")
    options = parser.parse_args()
    output = build(options.directory, options.out, games=options.game or GAME_BUILDS)
    if not output:
        print(f"{options.directory}: no C sources; a data-only mod needs no build")


if __name__ == "__main__":
    main()
