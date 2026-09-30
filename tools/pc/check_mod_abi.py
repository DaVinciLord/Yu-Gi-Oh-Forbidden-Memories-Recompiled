#!/usr/bin/env python3
"""Check that the mods made for earlier releases still work with this build.

A code mod is an object file built against one release's SDK (sdk/include,
sdk/exports.txt) and loaded by later ones (notes/modding.md), so what it was
compiled against has to stay as it was:

  exports    every name a baseline release lent a mod is still lent
  functions  an exported function or variable the SDK declares keeps its type
  records    a structure one of those reaches, by value or by pointer, keeps
             its size, field offsets and field types (growing one is a break
             too: a mod may allocate it, or hand it to the game)
  enums      an enumerator keeps its value; a removed one breaks a mod's
             source, and every later one moves with it

Each header of both SDKs is compiled on its own, as build_mod.py compiles a
mod (i386, -ffreestanding -nostdinc, the SDK's C library), and clang's AST
and record layouts are compared. That part needs no disc and runs in CI after
the release package is built.

With --run it also loads the baseline release's own mods, and its SDK's
examples built by its own build_mod.py, into this build's executable (the
disc is needed), and plays each smoke case that turns mods on
(tests/pc/smoke) with the baseline's copies of those mods and with this
build's: every code mod must load, and the frames must be the same.

The releases checked, and the differences reviewed and accepted, are in
tools/pc/mod_compat.txt. A release is downloaded once into tmp/pc/mod-compat.
Each --run plays in a folder of its own beside it, tmp/pc/mod-compat/run/
TAG-XXXXXXXX, kept when the run found a difference not accepted in
mod_compat.txt (or stopped) and removed otherwise: worktrees
share tmp/ (a junction to the main checkout's), so two checks running at once
in two of them took each other's frames and folders when they shared one."""
import argparse, concurrent.futures, glob, json, os, re, shutil, subprocess, sys, tarfile, tempfile, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPOSITORY = "Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled"   # src/pc/platform/update_check.c
CACHE = os.path.join(ROOT, "tmp/pc/mod-compat")
LIST = os.path.join(ROOT, "tools/pc/mod_compat.txt")
BUILD = os.path.join(ROOT, "tmp/pc/game32")
FLAGS = ["--target=i386-pc-linux-gnu", "-std=gnu11", "-ffreestanding", "-nostdinc", "-fsyntax-only", "-w",
         "-DMEMORIES_PC", "-DMEMORIES_MOD", "-D_LANGUAGE_C", "-DLANGUAGE_C"]
# The psyq headers expect the SDK's order and find one another with <angled>
# includes; a header that fails alone is tried again so (check_layouts.py).
PRELUDE = ["psyq/libgte.h", "psyq/libgpu.h", "psyq/libgs.h"]
UNNAMED = re.compile(r"\((?:unnamed|anonymous)(?: struct| union| enum)? at ([^)]*?):(\d+):(\d+)\)")
IDENTIFIER = re.compile(r"\b(?:(struct|union|enum)\s+)?([A-Za-z_]\w*)")


def clang():
    for candidate in (os.environ.get("MEMORIES_ABI_CLANG"), "clang", os.path.join(ROOT, "tmp/pc/llvm-mingw/bin/clang")):
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    sys.exit("check_mod_abi: clang is needed (MEMORIES_ABI_CLANG names another)")


# --- one SDK's surface ------------------------------------------------------

def compile_header(compiler, include, header, extra):
    """The JSON AST and the record layout dump of one header, or None."""
    resource = subprocess.run([compiler, "-print-resource-dir"], capture_output=True, text=True).stdout.strip()
    base = [compiler, *FLAGS, "-isystem", os.path.join(resource, "include"), "-isystem", os.path.join(include, "libc"),
            "-I", include, "-isystem", os.path.join(include, "psyq")]
    for prelude in ([], PRELUDE):
        includes = [a for name in prelude for a in ("-include", os.path.join(include, name))] + ["-include", header]
        ast = subprocess.run([*base, *includes, *extra, "-Xclang", "-ast-dump=json", "-x", "c", os.devnull],
                             capture_output=True, text=True)
        if ast.returncode:
            continue
        layout = subprocess.run([*base, *includes, *extra, "-Xclang", "-fdump-record-layouts-complete",
                                 "-x", "c", os.devnull], capture_output=True, text=True)
        return json.loads(ast.stdout), layout.stdout
    return None


def place(path, include):
    """`path` from the SDK's include directory. A compiler header on another
    Windows drive has no relative path: it is spelled whole, the same for
    every SDK, since they all use one compiler."""
    try:
        return os.path.relpath(path, include)
    except ValueError:
        return path.replace("\\", "/")


def spot(text, include):
    """An unnamed type's place, spelled the same whichever SDK it is in."""
    return UNNAMED.sub(lambda m: f"(unnamed at {place(m.group(1), include)}:{m.group(2)})", text)


def unnamed_places(tree, include):
    """{node id: "(unnamed at header:line)"} for every unnamed record. The
    JSON leaves out a location's file and line when they are the previous
    location's, so they are carried along in document order."""
    places, where = {}, {"file": None, "line": None}
    def location(value):
        if isinstance(value, dict):
            if "offset" in value:
                where["file"] = value.get("file", where["file"])
                where["line"] = value.get("line", where["line"])
            for key in ("spellingLoc", "expansionLoc", "begin", "end"):
                if key in value:
                    location(value[key])
    def walk(node):
        location(node.get("loc"))
        if node.get("kind") == "RecordDecl" and not node.get("name") and where["file"]:
            places[node["id"]] = f"(unnamed at {place(where['file'], include)}:{where['line']})"
        location(node.get("range"))
        for child in node.get("inner", []):
            walk(child)
    walk(tree)
    return places


def owned_record(node):
    """The id of the record a typedef declares in place (typedef struct {...} X):
    an ElaboratedType's ownedTagDecl, or (clang 22) a RecordType isTagOwned."""
    for child in node.get("inner", []):
        if "ownedTagDecl" in child:
            return child["ownedTagDecl"]["id"]
        if child.get("isTagOwned") and "decl" in child:
            return child["decl"]["id"]
        found = owned_record(child)
        if found:
            return found
    return None


def read_ast(tree, include, surface):
    places = unnamed_places(tree, include)
    for node in tree.get("inner", []):
        if node.get("kind") == "TypedefDecl" and owned_record(node) in places:
            surface["unnamed"].setdefault(places[owned_record(node)], node["name"])
    for node in tree.get("inner", []):
        if node.get("isImplicit"):
            continue
        kind, name = node["kind"], node.get("name")
        if kind in ("FunctionDecl", "VarDecl") and name:
            if kind == "VarDecl" and node.get("storageClass") == "static":
                continue
            surface["decls"].setdefault(name, (kind, spot(node["type"]["qualType"], include)))
        elif kind == "TypedefDecl" and name:
            surface["typedefs"].setdefault(name, spot(node["type"].get("qualType", ""), include))
        elif kind == "EnumDecl":
            value = -1
            for constant in node.get("inner", []):
                if constant.get("kind") != "EnumConstantDecl":
                    continue
                evaluated = find_value(constant)
                value = evaluated if evaluated is not None else value + 1
                surface["enums"].setdefault(constant["name"], value)


def find_value(node):
    for child in node.get("inner", []):
        if "value" in child and child.get("kind") == "ConstantExpr":
            return int(child["value"])
        found = find_value(child)
        if found is not None:
            return found
    return None


def read_layouts(dump, include, surface):
    """Each layout starts `0 | struct Name`, its fields and theirs indented
    under it, and ends `| [sizeof=..., align=...]`."""
    record, lines = None, []
    def done():
        if record:
            surface["records"].setdefault(record, "\n".join(lines))
    for line in dump.splitlines():
        if line.startswith("*** Dumping AST Record Layout"):
            done()
            record, lines = None, []
        elif "|" in line:
            if record is None:
                record = spot(line.split("|", 1)[1].strip(), include)
            lines.append(spot(re.sub(r"\s+", " ", line.strip()), include))
    done()


def sdk_surface(sdk, compiler):
    """{decls, typedefs, enums, records} of every header an SDK has, and the
    headers that do not compile alone."""
    include = os.path.join(sdk, "include")
    headers = sorted(path for path in glob.glob(os.path.join(include, "**", "*.h"), recursive=True)
                     if not os.path.relpath(path, include).startswith("libc" + os.sep))
    surface = {"decls": {}, "typedefs": {}, "enums": {}, "records": {}, "unnamed": {}, "skipped": []}
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
        results = pool.map(lambda h: (h, compile_header(compiler, include, h, [])), headers)
        for header, result in results:
            if result is None:
                surface["skipped"].append(os.path.relpath(header, include))
                continue
            read_ast(result[0], include, surface)
            read_layouts(result[1], include, surface)
    # An unnamed record goes by its typedef's name, else by none: its line
    # moves whenever the header above it changes.
    def named(text):
        return re.sub(r"(?:(?:struct|union) )?(\(unnamed at [^)]*\))",
                      lambda m: surface["unnamed"].get(m.group(1), "(unnamed)"), text)
    surface["records"] = {named(key): named(text) for key, text in surface["records"].items()}
    surface["decls"] = {key: (kind, named(text)) for key, (kind, text) in surface["decls"].items()}
    surface["typedefs"] = {key: named(text) for key, text in surface["typedefs"].items()}
    return surface


# --- comparing two ----------------------------------------------------------

def canonical(text, typedefs, depth=0):
    """A type with the typedefs of scalars and pointers spelled out, so s32
    and int compare equal; a record's or enum's typedef stays its name."""
    def expand(match):
        keyword, name = match.groups()
        if keyword or name not in typedefs or depth > 8:
            return match.group(0)
        target = typedefs[name]
        if re.match(r"(struct|union|enum)\b", target):
            return name
        return "(" + canonical(target, typedefs, depth + 1) + ")" if " " in target else canonical(target, typedefs, depth + 1)
    return re.sub(r"\s+", " ", IDENTIFIER.sub(expand, text)).replace("( ", "(").replace(" )", ")")


def record_key(name, surface):
    """What a type name is called in the record layouts, if it is a record."""
    target = surface["typedefs"].get(name, name)
    for candidate in (target, "struct " + name, "union " + name, name):
        if candidate in surface["records"]:
            return candidate
    return None


def reachable(names, surface):
    """The records the given exported declarations reach, however deep."""
    seen, pending = set(), []
    def visit(text):
        for keyword, name in IDENTIFIER.findall(text):
            key = record_key(f"{keyword} {name}" if keyword else name, surface) or record_key(name, surface)
            if key and key not in seen:
                seen.add(key)
                pending.append(key)
    for name in names:
        visit(surface["decls"][name][1])
    while pending:
        visit(surface["records"][pending.pop()])
    return seen


def compare(old, new, exports_old, exports_new):
    """Every difference, as (kind, name, what)."""
    found = [("header", header, "no longer compiles on its own, as it did") for header in new["skipped"]
             if header not in old["skipped"]]
    for name in sorted(exports_old - exports_new):
        found.append(("export", name, "no longer exported"))
    checked = sorted(n for n in exports_old & exports_new if n in old["decls"])
    for name in checked:
        kind = "function" if old["decls"][name][0] == "FunctionDecl" else "variable"
        if name not in new["decls"]:
            found.append((kind, name, "no longer declared in the SDK's headers"))
            continue
        before = canonical(old["decls"][name][1], old["typedefs"])
        after = canonical(new["decls"][name][1], new["typedefs"])
        if before != after:
            found.append((kind, name, f"was {before}, now {after}"))
    for record in sorted(reachable(checked, old)):
        # Named by its tag alone: one word, as mod_compat.txt names it.
        shown = record.split(" ", 1)[1] if record.startswith(("struct ", "union ")) else record
        if record not in new["records"]:
            found.append(("record", shown, "is gone"))
        elif old["records"][record] != new["records"][record]:
            before, after = old["records"][record].splitlines(), new["records"][record].splitlines()
            first = next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), min(len(before), len(after)))
            was = before[first] if first < len(before) else "(nothing)"
            now = after[first] if first < len(after) else "(nothing)"
            found.append(("record", shown, f"layout changed: was `{was}`, now `{now}`"))
    for name, value in sorted(old["enums"].items()):
        if name not in new["enums"]:
            found.append(("enum", name, f"was {value}, now removed"))
        elif new["enums"][name] != value and not (name.endswith("_COUNT") and new["enums"][name] > value):
            # A count past the last enumerator grows as enumerators are added.
            found.append(("enum", name, f"was {value}, now {new['enums'][name]}"))
    return found


# --- releases ---------------------------------------------------------------

def read_list():
    """The baseline releases, and {(release, kind, name): reason} accepted."""
    baselines, accepted = [], {}
    with open(LIST, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            words = line.split(None, 4)
            if words[0] == "baseline" and len(words) == 2:
                baselines.append(words[1])
            elif words[0] == "accept" and len(words) == 5:
                accepted[tuple(words[1:4])] = words[4]
            else:
                sys.exit(f"{LIST}:{number}: expected `baseline TAG` or `accept TAG KIND NAME reason`")
    return baselines, accepted


def fetch(tag, system):
    """A release's package for `system`, unpacked: its sdk/, mods/ and executable."""
    folder = os.path.join(CACHE, tag, system)
    unpacked = os.path.join(folder, f"yfm-redecomp-{tag}")
    if os.path.isdir(unpacked):
        return unpacked
    os.makedirs(folder, exist_ok=True)
    name = f"yfm-redecomp-{tag}-{system}." + ("zip" if system == "windows" else "tar.gz")
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    print(f"check_mod_abi: downloading {url}", flush=True)
    # Downloaded and unpacked in a folder of this run's, then moved in whole:
    # a check in another worktree may be fetching the same release.
    staging = tempfile.mkdtemp(prefix="fetch-", dir=folder)
    try:
        archive = os.path.join(staging, name)
        with urllib.request.urlopen(url, timeout=300) as response, open(archive, "wb") as handle:
            shutil.copyfileobj(response, handle)
        if system == "windows":
            with zipfile.ZipFile(archive) as package:
                package.extractall(staging)
        else:
            with tarfile.open(archive) as package:
                package.extractall(staging, filter="data")
        if not os.path.isdir(os.path.join(staging, f"yfm-redecomp-{tag}")):
            sys.exit(f"check_mod_abi: {name} has no yfm-redecomp-{tag} folder")
        try:
            os.rename(os.path.join(staging, f"yfm-redecomp-{tag}"), unpacked)
        except OSError:
            if not os.path.isdir(unpacked):  # not another run's copy that got there first
                raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return unpacked


# --- running the baseline's mods --------------------------------------------

def game_environment(settings, user, mods, extra=()):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("MEMORIES_") or key == "MEMORIES_DISC"}
    environment.update(MEMORIES_HEADLESS="1", MEMORIES_NO_UPDATE_CHECK="1", MEMORIES_NO_AUDIO="1",
                       MEMORIES_NO_GAMEPAD="1", MEMORIES_SPEED="-1", MEMORIES_SHOW_HUD="0", MEMORIES_WATCHDOG="0",
                       MEMORIES_SETTINGS=settings, MEMORIES_USER_DIR=user, MEMORIES_MODS_DIR=mods, **dict(extra))
    return environment


def launch(executable):
    if executable.endswith(".exe") and sys.platform != "win32":
        return ["wine", executable], {"WINEPREFIX": os.path.join(ROOT, "tmp/pc/wine-prefix"),
                                      "WINEDLLOVERRIDES": "mscoree,mshtml=", "WINEDEBUG": "-all"}
    return [executable], {}


def manifest(directory):
    with open(os.path.join(directory, "mod.json"), encoding="utf-8-sig") as handle:
        return json.load(handle)


def run_mods(tag, release, executable, build):
    """Every mod the baseline shipped, all on, in this build: ([(kind, name, what)],
    the run's folder). main() removes the folder unless a finding in it was
    not accepted in mod_compat.txt."""
    os.makedirs(os.path.join(CACHE, "run"), exist_ok=True)
    work = tempfile.mkdtemp(prefix=f"{tag}-", dir=os.path.join(CACHE, "run"))
    mods, user = os.path.join(work, "mods"), os.path.join(work, "user")
    shutil.copytree(os.path.join(release, "mods"), mods)
    os.makedirs(user)
    # The SDK's examples stand for a mod someone else made with that release:
    # the code ones are built by its own build_mod.py, against its headers.
    # A copy of its SDK is run, as that script keeps its objects in
    # tmp/pc/mod-objects beside the SDK, where another run would be writing.
    sdk = os.path.join(work, "sdk")
    shutil.copytree(os.path.join(release, "sdk"), sdk, ignore=shutil.ignore_patterns("examples"))
    for example in sorted(glob.glob(os.path.join(release, "sdk", "examples", "mods", "*"))):
        target = os.path.join(mods, "example-" + os.path.basename(example))
        shutil.copytree(example, target)
        if glob.glob(os.path.join(target, "*.c")):
            subprocess.run([sys.executable, os.path.join(sdk, "tools", "build_mod.py"), "--game", release,
                            target], check=True, capture_output=True)
    ids = {}
    for directory in sorted(glob.glob(os.path.join(mods, "*", "mod.json"))):
        data = manifest(os.path.dirname(directory))
        ids[data["id"]] = data.get("library")
    settings = os.path.join(work, "settings.txt")
    with open(settings, "w") as handle:
        handle.writelines(f"mod.{mod}=1\n" for mod in ids)
    command, extra = launch(executable)
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=300,
                            env={**game_environment(settings, user, mods, dict(MEMORIES_TRACE="mods",
                                 MEMORIES_DUMP_FRAME="600", MEMORIES_DUMP_PATH=os.path.join(work, "frame.ppm"))),
                                 **extra})
    output = result.stdout + result.stderr
    found = []
    if result.returncode:
        found.append(("run", "mods", f"the game exited {result.returncode} with {tag}'s mods on"))
    for mod, library in ids.items():
        for line in re.findall(rf"memories-pc: mod {re.escape(mod)}: (?!warning)(.*)", output):
            found.append(("run", mod, line))
        if library and not re.search(rf"mods\] {re.escape(mod)}: loaded ", output):
            found.append(("run", mod, "its code was not loaded"))
    print(f"check_mod_abi: {tag}: {len(ids)} mods run in {executable}")
    for case_path in sorted(glob.glob(os.path.join(ROOT, "tests/pc/smoke/*.json"))):
        with open(case_path, encoding="utf-8") as handle:
            case = json.load(handle)
        wanted = [key[4:] for key, value in case.get("settings", {}).items() if key.startswith("mod.") and value]
        if not wanted or not all(os.path.isdir(os.path.join(release, "mods", m)) and
                                 os.path.isdir(os.path.join(build, "mods", m)) for m in wanted):
            continue
        frames = []
        for side, source in (("baseline", os.path.join(release, "mods")), ("current", os.path.join(build, "mods"))):
            folder = os.path.join(work, f"{case['name']}-{side}")
            os.makedirs(os.path.join(folder, "user"))
            for mod in wanted:
                shutil.copytree(os.path.join(source, mod), os.path.join(folder, "mods", mod))
            with open(os.path.join(folder, "settings.txt"), "w") as handle:
                handle.writelines(f"{key}={value}\n" for key, value in case["settings"].items())
            frame = os.path.join(folder, "frame.ppm")
            subprocess.run(command, cwd=ROOT, capture_output=True, timeout=300, env={**game_environment(
                os.path.join(folder, "settings.txt"), os.path.join(folder, "user"), os.path.join(folder, "mods"),
                dict(MEMORIES_INPUT=str(case["input"]), MEMORIES_DUMP_FRAME=str(case["frame"]),
                     MEMORIES_DUMP_PATH=frame)), **extra})
            frames.append(open(frame, "rb").read() if os.path.exists(frame) else None)
        if frames[0] is None or frames[0] != frames[1]:
            found.append(("frame", case["name"], f"{tag}'s {', '.join(wanted)} draw another frame than this "
                          f"build's (see {work}/{case['name']}-*/frame.ppm)"))
        else:
            print(f"check_mod_abi: {tag}: {case['name']} is the same frame with {tag}'s {', '.join(wanted)}")
    return found, work


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", default=BUILD, help="the game build whose sdk/ (and mods/) to check")
    parser.add_argument("--baseline", action="append", help="a release tag, or an unpacked release folder "
                        "(default: every `baseline` in tools/pc/mod_compat.txt)")
    parser.add_argument("--run", action="store_true", help="also run the baseline's mods in this build (needs the disc)")
    parser.add_argument("--executable", help="the executable --run uses (default: the build's; a .exe runs in Wine)")
    options = parser.parse_args()
    baselines, accepted = read_list()
    compiler = clang()
    current_sdk = os.path.join(options.build, "sdk")
    if not os.path.isfile(os.path.join(current_sdk, "exports.txt")):
        sys.exit(f"check_mod_abi: {current_sdk} has no exports.txt; build the game first (tools/pc/build_game32.py)")
    with open(os.path.join(current_sdk, "exports.txt")) as handle:
        exports_new = set(handle.read().split())
    current = sdk_surface(current_sdk, compiler)
    # The Windows SDK lends a few names the Linux one does not, and the
    # other way round: a build is held to its own system's package.
    system = "windows" if os.path.exists(os.path.join(options.build, "memories-pc.exe")) else "linux"
    failed = False
    for baseline in options.baseline or baselines:
        release = baseline if os.path.isdir(baseline) else fetch(baseline, system)
        tag = os.path.basename(os.path.normpath(release)).replace("yfm-redecomp-", "") if os.path.isdir(baseline) else baseline
        with open(os.path.join(release, "sdk", "exports.txt")) as handle:
            exports_old = set(handle.read().split())
        old = sdk_surface(os.path.join(release, "sdk"), compiler)
        found = compare(old, current, exports_old, exports_new)
        work = None
        if options.run:
            executable = options.executable or os.path.join(options.build, "memories-pc" + (".exe" if system == "windows" else ""))
            ran, work = run_mods(tag, release, os.path.abspath(executable), options.build)
            found += ran
        used, keep = set(), False
        for kind, name, what in found:
            key = (tag, kind, name)
            if key in accepted:
                used.add(key)
                print(f"  accepted: {kind} {name}: {what} ({accepted[key]})")
            else:
                failed = True
                keep = keep or kind in ("run", "frame")
                print(f"check_mod_abi: {tag}: {kind} {name}: {what}", file=sys.stderr)
        # The run's folder is kept for a difference still to be looked at;
        # an accepted one would leave a folder behind on every passing run.
        if work and not keep:
            shutil.rmtree(work, ignore_errors=True)
        for key in sorted(k for k in accepted if k[0] == tag and k not in used and (options.run or k[1] not in ("run", "frame"))):
            print(f"check_mod_abi: {tag}: `accept {' '.join(key)}` in mod_compat.txt no longer matches anything; "
                  "remove it", file=sys.stderr)
            failed = True
        compared = len([n for n in exports_old & exports_new if n in old["decls"]])
        print(f"check_mod_abi: {tag}: {len(exports_old)} exports, {compared} declarations, "
              f"{len(reachable([n for n in exports_old & exports_new if n in old['decls']], old))} records and "
              f"{len(old['enums'])} enumerators compared; {len(old['skipped'])} headers do not compile alone")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
