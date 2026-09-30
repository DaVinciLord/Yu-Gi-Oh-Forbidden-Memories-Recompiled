# PC release packaging

The release is an unpack-and-run folder. Windows uses a GUI executable
(no console window); Linux uses the SDL executable, built against the
existing Debian 11 i386 sysroot. Both remain 32-bit builds.

```text
yfm-redecomp-<version>/
  memories-pc.exe + SDL3.dll    # Windows ZIP
  memories-pc.pdb              # Windows symbols (debuggers, profilers)
  memories-pc                  # Linux tar.gz, executable permission retained
  README.txt
  LICENSE
  buildid
  commit
  game/README.txt              # optional auto-detected ROM location
  mods/                       # bundled mods, from tracked project files
  sdk/                        # headers, tools, examples, modding notes
  symbols/                    # this build's crash/save-state symbol tables
```

GitHub shows each release asset's SHA-256 itself, so there are no
`.sha256` files beside the archives. No ROM, extracted game data, user
settings, saves, reports or personal HD packs belong in the archive. Release
builds omit the optional executable icon extracted from a local disc.

The Windows executable is what virus scanners' heuristics judge, so the
release keeps it plain: `package.py` strips the symbol table and debug
sections (`memories-pc.pdb` has them) and fills in the PE checksum the linker
leaves 0; the build gives it version information, names its PDB without the
builder's path, and leaves test-only paths out (`MEMORIES_TEST_HOOKS`,
[PC build](pc-build.md)); the game does not call `SetProcessDEPPolicy`.
v0.1.4-preview.1 was flagged by 11 engines with generic machine-learning
labels (a false positive): Bitdefender's engines over the GitHub runner's PDB
path, the rest with no reason given, in the release that had gained the
DEP-policy imports. `test_package.py` checks all of these on every release.

## Launch experience

If a remembered or auto-detected disc is available, launch goes straight
into the game. Otherwise a normal information dialog welcomes the player,
explains the USA SLUS-01411 raw `.bin` requirement, and offers **Choose ROM...**
and **Quit**. Choose ROM opens the system file picker. Cancel exits with
status zero. Invalid/unreadable selections show an error and allow another
attempt. Failure to save the location is also reported.

Only the path is saved, as UTF-8 in `disc-path.txt` in the existing user
folder. The ROM is never copied or modified. A moved/missing selection brings
setup back on the next launch. The existing `game/` discovery and explicit
`MEMORIES_DISC` override still work. Headless launches and a broken explicit
override fail without opening a picker. The developer X11 backend retains
folder/environment-based discovery; shipped builds explicitly use SDL.

SDL's asynchronous picker is awaited while pumping events, with the crash
monitor paused for user interaction. Linux uses the desktop portal or Zenity;
a failed picker explains the `game/` folder fallback. See the
[SDL dialog contract](https://wiki.libsdl.org/SDL3/SDL_ShowOpenFileDialog).

## GitHub build flow

`.github/workflows/pc-release.yml` builds on pull requests, pushes to `master`,
`v*` tags and manual dispatch. Native Ubuntu and Windows runners use the
existing dependency/toolchain fetchers and cache only dependencies. Linux
selects GCC 14 because the game source build uses C `-fpermissive`.

Every build uploads a Windows ZIP or Linux tar.gz as an Actions
artifact, retained for 14 days. On a version tag, both jobs must succeed before
the final job creates a **draft** GitHub release and attaches both packages.
Reruns can update a draft but refuse to replace an already published release.

Two kinds of tag:

- `v0.2.0-preview.1` (any hyphen, also `-rc.1`, `-beta.2`): a **preview**.
  The draft is marked as a pre-release, so GitHub labels it and "Latest
  release" keeps pointing at the last real one.
- `v0.2.0`: a **release**, a normal draft.

To make one: `git tag v0.2.0-preview.1 origin/master && git push origin
v0.2.0-preview.1`, wait for the workflow, test the attached archives, then
edit the draft on the Releases page and press Publish. Nothing is public
until then. A bad draft can be deleted along with its tag
(`gh release delete v0.2.0-preview.1 --cleanup-tag`).
The normal PC foundation workflow continues running the full adapter tests
on both platforms; it also includes the new ROM setup tests.

Public runners do not receive a disc or need a ROM secret. They compile the
full game and check archive structure; they skip ROM-dependent gameplay smoke
tests explicitly. Run those locally before publishing a draft. Workflow events
follow [GitHub's trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

### Mods made for earlier releases

A mod made for one release has to keep working in the later ones.
`tools/pc/mod_compat.txt` lists the releases that promise covers, and
`tools/pc/check_mod_abi.py` enforces it:

- In CI, on every pull request (Linux job, no disc), it compares the SDK
  just built with each listed release's SDK. Every name that release lent
  a code mod must still be exported. Every exported function and variable
  its headers declare must keep its type. Every structure they reach must
  keep its layout, and every enumerator its value.
- Locally, `smoke.py` (and so `package.py`) runs it with `--run`. This
  loads each listed release's own mods, and its SDK's examples built with
  its own `build_mod.py`, into the new build. Every code mod must load.
  Each smoke case that turns mods on must draw the same frame with the old
  release's copies of those mods as with this build's. Each run plays in a
  folder of its own, `tmp/pc/mod-compat/run/<tag>-XXXXXXXX`, kept when it
  found a difference not accepted in `mod_compat.txt`: worktrees share `tmp/`, and two checks at once used to
  take each other's frames.

A difference that fails the check is fixed, not waved through. Keep the old
number, argument list or layout, and add beside it. Only a difference
that provably breaks no mod goes in `mod_compat.txt` as `accept`, with the
reason. After publishing a release, add `baseline <tag>` for it to
`mod_compat.txt`.

## Local commands

```sh
# Build the CTests used by the Linux smoke runner first:
cmake -S . -B tmp/pc/cmake-test -DCMAKE_BUILD_TYPE=Release
cmake --build tmp/pc/cmake-test --parallel

# Build, smoke-test with your own disc, then package both platforms:
python tools/pc/package.py --version v0.1.0

# Compile/package without a disc (the CI path):
python tools/pc/package.py linux --skip-smoke --version dev-preview
python tools/pc/package.py windows --skip-smoke --version dev-preview

# Inspect the artifacts without a disc:
python tools/pc/test_package.py --archives dist
```

`--no-build` packages existing outputs; use it only after explicitly building
with `--release`, since it cannot change a previously built executable.
Windows builds use `tmp/pc/win32` during packaging on both host platforms.

Before publishing: play-test the packaged builds on Linux and real Windows,
including first-run selection, invalid selection, cancellation, moving the
ROM, restart with the remembered path, sound, controller input, and an in-game
save/load. Wine checks help but do not replace native Windows validation.
Upgrade by extracting into a fresh folder. A build packaged with a `vX.Y.Z`
version checks the releases at start (Help menu turns it off) and tells the player
a newer one is out; it never installs it itself ([updates](updates.md)). `--version` is the
version the build compares with (`MEMORIES_VERSION`); CI passes the tag, so
tag builds check and `dev-*` builds do not. User settings and memory-card
saves persist; cross-build save-state compatibility is not guaranteed.

## VirusTotal

Generic machine-learning and heuristic engines keep flagging the Windows
`memories-pc.exe` (v0.1.4-preview.1: 11 of 71). `tools/pc/vt_check.py`
measures that without uploading by hand on the website: it looks each file
up by SHA-256 (API v3), uploads the ones VirusTotal has not seen, waits for
the analysis and prints detections/total, the label of every engine that
flagged the file, an engine × file matrix when there are several files, and
each file's page (`https://www.virustotal.com/gui/file/<sha256>`). The
count is the engines that said "malicious", out of those that gave any
verdict, as the website counts; "suspicious" verdicts are listed apart.

**Key.** Sign up at virustotal.com (a free community account); the key is
under the profile menu, *API key*. Keep it out of the repository: the script
reads `VT_API_KEY`, else `~/.config/yfm/vt_api_key` (on Windows
`%USERPROFILE%\.config\yfm\vt_api_key`; make it readable only by you). It
never prints the key, only where it came from.

**Terms and limits.** The free public API is for non-commercial use only
(this project qualifies; a commercial product or service needs VirusTotal's
premium API). It allows 4 requests a minute, 500 a day and 15.5 thousand a
month. The script spaces its requests 15 s apart (`--rate`), backs off on
HTTP 429, and stops at `--daily` requests (500) in one run. A lookup is one
request; an upload is one or two more, then one per 15 s until the analysis
is done, usually a few minutes.

**Uploads are public.** Every uploaded file is shared with the antivirus
vendors and downloadable by VirusTotal's premium users. Upload only builds
that are, or will be, public anyway: release candidates of our own
executable. Never anything with game data (a disc image, extracted files,
HD packs), nor builds nobody will ship. `--lookup-only` never uploads.

**Bisecting locally.** Build the variants exactly like the release (as
`package.py windows` does: `build_game32.py --target windows --backend sdl
--release --build tmp/pc/<name>` with `MEMORIES_VERSION` set, then that
commit's `package.strip()` on a copy, since the shipped exe is stripped; a
build dir of its own, because worktrees share `tmp/`). Then:

```sh
python tools/pc/vt_check.py --lookup-only old-release.exe      # already public: no upload
python tools/pc/vt_check.py --label master --label no-dep a.exe b.exe --json vt.json
python tools/pc/vt_check.py --reanalyze --label v0.1.4 v0.1.4.exe   # rescan with today's engines
```

The same engine names down one column tell which change moved which
engine. Engines' verdicts drift over days (a rescan can flag a file that
was clean when it shipped), so compare variants scanned the same day.
`--max N` exits 1 when a file has more than N detections; 2 means the
check itself failed (no key, network, quota, `--timeout`).

**In CI.** The release workflow's *VirusTotal* step (Windows job) runs the
script on the shipped `memories-pc.exe` and `fm-editor.exe`, taken from
the archives, and writes the table, the matrix and the links into the job
summary. It warns above `VT_MAX_DETECTIONS` (2) and never fails the build;
when VirusTotal is down or slow it warns too, after at most 10 minutes an
analysis (`--timeout 600`) and 30 for the step. McAfeeD's reputation verdict (`ti!<hash>`) marks every file VirusTotal has
just met, so 0 would warn on every release. It runs only on version tags and
manual runs (*Run workflow*), so only those builds are uploaded; never on
pull requests nor on pushes to `master`, and it is skipped when the
repository has no `VT_API_KEY` secret (forks). A repository admin adds the secret with
`gh secret set VT_API_KEY` (it prompts for the value, so it stays out of
the shell history); removing it turns the step off.
