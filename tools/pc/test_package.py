#!/usr/bin/env python3
"""Check release archives without a ROM: layout, modes, no user data."""
import argparse
import struct
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def check_exe(image):
    """The shipped .exe: stripped (tools/pc/package.py strip) and with a
    resource section (version information), since virus scanners flag data
    after the last section and programs that say nothing about themselves.
    Its PDB is named without the builder's path: Bitdefender flagged the CI
    builds, whose path was the GitHub runner's D:/a/..."""
    header = struct.unpack_from("<I", image, 0x3C)[0]
    sections, _, symbols, symbol_count, optional = struct.unpack_from("<HIIIH", image, header + 6)
    table = header + 24 + optional
    names, end = set(), 0
    for index in range(sections):
        at = table + 40 * index
        names.add(image[at:at + 8].rstrip(b"\0"))
        size, offset = struct.unpack_from("<II", image, at + 16)
        end = max(end, offset + size)
    assert symbols == 0 and symbol_count == 0, "memories-pc.exe keeps its COFF symbol table"
    assert len(image) == end, f"memories-pc.exe has {len(image) - end} bytes after its last section"
    assert b".rsrc" in names, "memories-pc.exe has no resources (version information)"
    marker = image.find(b"RSDS")
    assert marker >= 0, "memories-pc.exe has no CodeView record"
    pdb = image[marker + 24:image.index(b"\0", marker + 24)]
    assert pdb == b"memories-pc.pdb", f"memories-pc.exe names its PDB {pdb!r}, not by bare name"
    # What v0.1.4-preview.1 gained and 11 engines' models held against it
    # (notes/pc-release.md): DEP-policy imports and the executable-guest-RAM
    # test path, which a release leaves out (MEMORIES_TEST_HOOKS).
    for name in (b"SetProcessDEPPolicy", b"GetProcessDEPPolicy", b"GetSystemDEPPolicy", b"MEMORIES_TEST_EXEC_GUEST"):
        assert name not in image, f"memories-pc.exe contains {name.decode()}"
    # The PE checksum package.py fills in after the strip: ImageHlp's sum
    # of the file's 16-bit words (its own field as 0), folded, plus the length.
    field = header + 24 + 64
    stored = struct.unpack_from("<I", image, field)[0]
    padded = image[:field] + bytes(4) + image[field + 4:] + bytes(len(image) % 2)
    total = sum(struct.unpack(f"<{len(padded) // 2}H", padded))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    assert stored == total + len(image), f"memories-pc.exe's PE checksum is {stored:#x}, not {total + len(image):#x}"


def check(path):
    windows = path.suffix == ".zip"
    if windows:
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            check_exe(archive.read(next(name for name in names if name.endswith("/memories-pc.exe"))))
    else:
        with tarfile.open(path) as archive:
            members = archive.getmembers()
            names = [item.name for item in members if item.isfile()]
            assert all(item.isfile() or item.isdir() for item in members), "unexpected links or special files"
            executable = [item for item in members if item.name.endswith("/memories-pc")]
            assert len(executable) == 1 and executable[0].mode & 0o111, "Linux executable must be executable"
    roots = {PurePosixPath(name).parts[0] for name in names}
    assert len(roots) == 1, "archive needs one top-level folder"
    assert all(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts for name in names)
    contents = {str(PurePosixPath(name).relative_to(next(iter(roots)))) for name in names}
    required = {"README.txt", "LICENSE", "buildid", "commit", "game/README.txt",
                "memories-pc.exe" if windows else "memories-pc"}
    if windows:
        required |= {"SDL3.dll", "memories-pc.pdb"}
    assert required <= contents, f"missing files: {required - contents}"
    for directory in ("mods/", "sdk/", "symbols/"):
        assert any(name.startswith(directory) for name in contents), f"missing {directory}"
    languages = {f"languages/{name}.txt" for name in ("en-eu", "fr", "de", "it", "es")}
    assert {name for name in contents if name.startswith("languages/")} == languages, "languages/ needs the five packs"
    assert {name for name in contents if name.startswith("game/")} == {"game/README.txt"}
    assert not any(name.startswith(("saves/", "reports/", "tmp/", "mods/assets-hd/")) or
                   name in {"disc-path.txt", "settings.ini", "controls.ini"} or
                   PurePosixPath(name).suffix.lower() in {".bin", ".cue", ".iso", ".chd", ".mcr"}
                   for name in contents), "archive contains personal or disc data"
    print(f"{path.name}: layout passed ({len(contents)} files)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, required=True)
    args = parser.parse_args()
    archives = sorted(args.archives.glob("*.zip")) + sorted(args.archives.glob("*.tar.gz"))
    assert archives, "no release archives found"
    for path in archives:
        check(path)


if __name__ == "__main__":
    main()
