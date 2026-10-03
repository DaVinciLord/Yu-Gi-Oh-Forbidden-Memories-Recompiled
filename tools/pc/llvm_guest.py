"""Versioned LLVM guest compiler; Python orchestrates, LLVM owns IR semantics."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'tmp/pc/guest-compiler'
CONFIG = Path(__file__).with_name('macos_toolchain.json')

class TranslationError(ValueError):
    pass

def toolchain():
    config = json.loads(CONFIG.read_text())
    folder = ROOT / 'tmp/pc/llvm-macos' / ('LLVM-' + config['version'] + '-macOS-ARM64')
    if not (folder/'bin/llvm-config').is_file():
        from fetch_tools import download, unpack
        unpack(download(config['url'], config['sha256']), str(folder.parent))
    version = subprocess.check_output([str(folder/'bin/llvm-config'), '--version'], text=True).strip()
    if version != config['version']:
        raise RuntimeError(f'Expected LLVM {config["version"]}, found {version}')
    return folder

def compiler():
    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT/'memories-guest-ir'
    source = ROOT/'tools/pc/llvm/guest_ir.cpp'
    if binary.is_file() and binary.stat().st_mtime >= max(source.stat().st_mtime, CONFIG.stat().st_mtime, Path(__file__).stat().st_mtime):
        return binary
    llvm = toolchain()
    flags = shlex.split(subprocess.check_output([str(llvm/'bin/llvm-config'), '--cxxflags',
        '--ldflags', '--libs', 'core', 'irreader', 'passes', 'support', '--system-libs'], text=True))
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    subprocess.run([str(llvm/'bin/clang++'), '-isysroot', sdk, '-nostdlib++', str(source), *flags,
                    str(llvm/'lib/libc++.a'), str(llvm/'lib/libc++abi.a'),
                    '-Wl,-rpath,@loader_path/../llvm-macos/' + llvm.name + '/lib',
                    '-O2', '-o', str(binary)], check=True)
    return binary

def process(operation, text, **options):
    binary = compiler()
    digest = hashlib.sha256((operation + text + json.dumps(options, sort_keys=True)).encode()).hexdigest()
    cache = OUT/'cache'; cache.mkdir(exist_ok=True)
    cached = cache/(digest + ('.json' if operation == 'inspect' else '.ll'))
    if cached.is_file() and cached.stat().st_mtime >= binary.stat().st_mtime:
        result = cached.read_text()
    else:
        with tempfile.TemporaryDirectory(dir=OUT) as temporary:
            folder = Path(temporary)
            source = folder/'input.ll'; source.write_text(text)
            config = folder/'options.json'; config.write_text(json.dumps(options))
            output = folder/'output'
            result = subprocess.run([str(binary), operation, str(source), str(output), str(config)],
                                    capture_output=True, text=True)
            if result.returncode:
                raise TranslationError(result.stderr.strip())
            result = output.read_text()
            cached.write_text(result)
    return json.loads(result) if operation == 'inspect' else result

def translate(text, pinned=None, registration=None, *, game_unit=False):
    return process('translate', text, pins=pinned or {}, game_unit=game_unit, **({'registration': registration} if registration else {}))

def normalize(text, renames=None, drop_definitions=()):
    return process('normalize', text, renames=renames or {}, drop_definitions=list(drop_definitions))

def inspect(text):
    return process('inspect', text)
