# Updates

A release build asks GitHub for the project's releases when it starts and,
when a newer one is out, says so in a notice over the picture:

- **Update now** downloads the release's archive for this system, unpacks it
  and installs it over the program's folder. The running game carries on; the
  new version runs from the next start (**Quit now** / **Later**).
- **Release page** opens the release on GitHub.
- **Skip this version** is remembered: that version is not offered again at
  start (a newer one still is).
- **Later** (Esc) asks again next start.

Update now is only offered where it can work: an unpacked release folder
(the executable, `buildid` and `LICENSE` beside each other) that can be
written to, and a release that has an archive for this system. Otherwise the
notice explains why and offers the release page. Nothing blocks the game: the
request and the download run on a thread of their own, and the main thread
only looks at the answer once a frame. Offline, the check at start fails
silently.

## Settings

**Help** on the menu bar. All three are in `settings.txt` and, as every
setting, have an environment override.

| Menu | Key | Default | Environment |
|---|---|---|---|
| Check for updates at start | `check_for_updates` | 1 | `MEMORIES_CHECK_FOR_UPDATES` |
| Install updates automatically | `auto_update` | 0 | `MEMORIES_AUTO_UPDATE` |
| Include pre-releases | `update_prereleases` | 0 | `MEMORIES_UPDATE_PRERELEASES` |

**Check for updates now** always answers, "You're up to date" included, and
ignores a skipped version. **Releases page** opens the list. The last row
shows this build's version, or "Development build".

With **Install updates automatically** a newer release found at start is
downloaded and installed without asking; the notice then says it is
installed. A pre-release is only offered when **Include pre-releases** is on,
or when the running version is itself a pre-release (someone on
`v0.2.0-preview.1` hears of `-preview.2`, `-rc.1` and `v0.2.0`).

## Which version a build is

`tools/pc/build_game32.py` writes `version.c` (`Memories_Version`) beside the
executable's objects on every link: `MEMORIES_VERSION` when it is set, else
the `v*` tag the checkout is exactly at (`git describe --tags --exact-match`).
`tools/pc/package.py` sets `MEMORIES_VERSION` to its `--version`, which the
release workflow takes from the tag. Anything that is not `vX.Y.Z` or
`vX.Y.Z-PRE` (`dev-<sha>` from CI on master, the date-and-commit label of a
local package, an untagged checkout) is a development build: it never checks
at start, and Check for updates now points at the releases page.

Versions compare as [semantic versions](https://semver.org/#spec-item-11):
`v0.2.0-preview.2 < v0.2.0-preview.10 < v0.2.0-rc.1 < v0.2.0`. A tag with a
hyphen is a pre-release whatever GitHub's flag says; drafts never count.

## Installing

The archive goes to `updates/` in the user folder, is checked against the
size GitHub lists and its SHA-256 (the `digest` GitHub gives each asset),
and is unpacked to `updates/stage` by the game itself (zlib; a zip's CRC-32s
and gzip's trailer are checked, and every name must stay inside the folder:
no absolute paths, `..`, links or devices). Then, over the program folder:

1. Every file of the release is copied beside its target as
   `<name>.update-new`. A failure here removes the copies; nothing changed.
2. Each target is renamed to `<name>.update-old` and the new file renamed in.
   A failure puts back what was renamed.
3. The old files are removed. What cannot be yet (the running `.exe` and
   `SDL3.dll` on Windows, which can be renamed but not deleted) is listed in
   `updates/cleanup.txt` and removed at the next start.

The release's `game/` folder is never copied (the player's disc image lives
there), and nothing the release does not contain is removed: a player's own
files in the program folder, a texture pack in its `mods/`, older symbol
tables. The archive and the staging folder are removed afterwards, whether
the install worked or not.

## Networking

No TLS library is linked in. Windows uses WinHTTP (`-lwinhttp`); Linux runs
`curl` (present on practically every distribution; without it the check
fails silently) with `posix_spawn`, reading the body from a pipe, with the
signal mask cleared for the child. The check has 20 seconds; a download 30
minutes (curl's whole-transfer limit; WinHTTP's per wait).

## Tests and scripted runs

The check at start is skipped when any of these hold, so tests and CI never
touch the network:

- `MEMORIES_NO_UPDATE_CHECK` is set to anything but `0` (`tools/pc/smoke.py`
  sets it);
- `MEMORIES_HEADLESS` is set;
- the input is scripted (`MEMORIES_INPUT`, `MEMORIES_SDL_SCRIPT`) and
  `MEMORIES_UPDATE_URL` is not set;
- the build is a development build.

For testing the notice end to end:

- `MEMORIES_UPDATE_URL` names another release list (the same JSON as
  `https://api.github.com/repos/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/releases`),
  for example one a local `python3 -m http.server` serves, with asset URLs
  pointing at archives beside it;
- `MEMORIES_UPDATE_CURRENT` pretends the running version is another one;
- `MEMORIES_USER_DIR` keeps the downloads, `skip.txt` and settings away from
  the player's own.

Keys drive the notice from `MEMORIES_SDL_SCRIPT`: Left/Right move the focus
(it starts on the last button), Return presses it, Escape presses the last.

`tests/pc/update_test.c` (CTest `pc_update`) covers the version order,
choosing a release from a GitHub answer, SHA-256, both archive kinds
(including long pax names, damaged, cut-off and escaping archives) and the
install step. The code is `src/pc/platform/update.c` (no window, no network),
`update_net.c` and `update_runtime.c`; the notice is `Menu_ShowNotice`
(`menu.h`).

## Limits

- The new version runs from the next start; the game does not restart
  itself: its restart (and the crash monitor's) would start the old,
  renamed executable again.
- A file a release drops stays in the folder (a removed bundled mod would
  still be listed). Extract into a fresh folder to get rid of them.
- A Windows folder under Program Files cannot be written to, so the notice
  offers the release page there. The executable has no manifest, so Windows
  would quietly redirect its writes there to the VirtualStore; the updater
  asks the process token (`TokenVirtualizationEnabled`) and does not try.
- Builds made from source (`play.sh`, `play.bat`) are development builds
  unless the checkout is exactly at a release tag; update those with git.
