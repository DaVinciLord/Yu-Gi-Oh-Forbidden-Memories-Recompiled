#!/usr/bin/env python3
"""Experimental full macOS arm64 translated build; no i386 artifacts reused.

The driver generates copies/IR under tmp, compiles every resident and configured
module unit, and links native SDK/platform services. Missing game functions use
existing fatal Memories_Unimplemented diagnostics, never success placeholders.

O2 code generation and audited native SoftGpu boundaries are enabled by default.
The guest frontend remains O0 before translation; --no-optimize restores the
fully instrumented O0 diagnostic build, and --instrument-softgpu retains O2
while restoring per-access raster instrumentation for comparisons.
"""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from llvm_guest import translate, TranslationError, normalize, inspect, process, toolchain
from direct_overlay_bridges import ENTRIES as DIRECT_OVERLAY_ENTRIES, validate_declaration, emit_bridge
SOFT_GPU = 'src/pc/render/soft_gpu.c'
from native_call_marshalling import emit_native_calls
from build_config import MODULES, MODULE_CONFIG, GATED_MODULES, native_sources, game_sources

ROOT = Path(__file__).resolve().parents[2]
SECTION = re.compile(r'__attribute__\s*\(\(\s*section\s*\(\s*"[^"\n]+"\s*\)\s*\)\)')
SYMBOL = r'[A-Za-z_][\w.$]*'
EXCLUDE = {'src/pc/guest/resolve.c', 'src/pc/guest/image.c', 'src/pc/guest/branch_thunks.c', 'src/pc/guest/state.c',
           'src/pc/platform/x11.c', 'src/pc/platform/audio_alsa.c', 'src/pc/platform/gamepad_evdev.c'}
ORDINARY = {'src/pc/memory.c', 'src/pc/guest/state_translated.c'}
HOST_LIBC = {'printf','sprintf','strcmp','strcpy','bzero','qsort','memcpy','memset','memmove',
             'strlen','strcat','strncmp','strncpy','memcmp','snprintf','vsnprintf',
             'strchr','strrchr','strnlen','strcspn','strspn','strstr','memchr'}
CHECKED_LIBC = {'__memcpy_chk','__memmove_chk','__memset_chk','__strcpy_chk','__strncpy_chk',
                '__strcat_chk','__strncat_chk','__sprintf_chk','__snprintf_chk',
                '__vsprintf_chk','__vsnprintf_chk','__strlcpy_chk','__strlcat_chk'}


def maps():
    result, active = {}, None
    for line in (ROOT / 'config/pc/guest_addresses.txt').read_text().splitlines():
        if line.startswith('['): active = line[1:-1];result[active] = {}
        elif active and len(line.split()) == 2:
            name, address = line.split();result[active][name] = int(address,16)
    return result

def definitions(ir):
    return set(inspect(ir)['definitions'])

def replace_names(ir, renames):
    return normalize(ir, renames)

def drop_functions(ir, names):
    return normalize(ir, drop_definitions=names)

def optimize_translated_ir(text):
    return process('optimize', text)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=ROOT/'tmp/arm64-build')
    parser.add_argument('--jobs',type=int,default=8)
    parser.add_argument('--compile-only',action='store_true')
    parser.add_argument('--instrument-softgpu', action='store_true', help='Keep full SoftGpu instrumentation for optimized A/B comparisons')
    parser.add_argument('--optimize', action=argparse.BooleanOptionalAction, default=True, help='Enable O2 translated IR/native helpers and audited SoftGpu boundaries (default); frontend remains O0')
    args = parser.parse_args()
    llvm = toolchain()
    cc = str(llvm/'bin/clang')
    from macos_deps import ensure, sdk_path
    dependencies = ensure(jobs=args.jobs)
    sdk = str(sdk_path())
    build=args.build.resolve();generated=ROOT
    for d in ['raw','ir','obj','logs']: (build/d).mkdir(parents=True,exist_ok=True)
    modules=MODULES;module_config=MODULE_CONFIG;address_tables=maps()
    groups=game_sources()
    natives=native_sources('arm64')
    required={'src/pc/guest/translated_image_backend.c','src/pc/guest/state_translated.c','src/pc/guest/translated_runtime.c'}
    if required-set(natives):raise SystemExit('Native backend files missing: '+str(required-set(natives)))
    ordinary={s for s in natives if s in ORDINARY or '/translated_' in s}
    if args.optimize and not args.instrument_softgpu: ordinary.add(SOFT_GPU)
    # Local independent runtime helpers must never resolve their own accesses.
    flags=['-isysroot',sdk,'-std=gnu11','-fms-extensions','-O0','-fno-strict-aliasing','-fwrapv','-fcommon','-fno-stack-protector',
           '-DMEMORIES_PC','-DMEMORIES_TRANSLATED','-D_LANGUAGE_C','-DLANGUAGE_C','-D_DARWIN_C_SOURCE',
           '-Isrc','-I'+str(dependencies/'include'),'-I'+str(dependencies/'include/freetype2'),'-w',
           '-Wno-incompatible-pointer-types','-Wno-int-conversion','-Wno-implicit-function-declaration']
    game_extra=['-include','src/pc/compat/pgxp_game.h']
    if not args.optimize or args.instrument_softgpu:
        flags.append('-DMEMORIES_INSTRUMENT_SOFTGPU')
    jobs=[(s,g) for g,sources in groups.items() for s in sources]+[(s,'native') for s in natives]
    newest=max(p.stat().st_mtime for p in (generated/'src').rglob('*.h'))
    def path_for(kind,source,suffix):return build/kind/(source.replace('/','_')+suffix)
    def run_logged(command,log,cwd=generated):
        result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
        log.write_text(result.stdout+result.stderr)
        return result.returncode
    def emit(job):
        source,group=job;raw=path_for('raw',source,'.ll');obj=path_for('obj',source,'.o')
        extra=game_extra if group!='native' else []
        emit_flags = [('-O2' if args.optimize and source in ordinary and flag == '-O0' else flag) for flag in flags]
        command=[cc,*emit_flags,*extra, '-c' if source in ordinary else '-S',
                 *([] if source in ordinary else ['-emit-llvm']),source,'-o',str(obj if source in ordinary else raw)]
        stamp=path_for('raw',source,'.flags');fingerprint=json.dumps(command)
        target=obj if source in ordinary else raw
        if target.exists() and stamp.exists() and stamp.read_text()==fingerprint and target.stat().st_mtime>=max(newest,(generated/source).stat().st_mtime):return source,group,0
        status=run_logged(command,path_for('logs',source,'.emit.log'))
        if not status:stamp.write_text(fingerprint)
        return source,group,status
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool: emitted=list(pool.map(emit,jobs))
    failures=[s for s,g,status in emitted if status]
    if failures:
        print('IR failures:',len(failures));print('\n'.join(failures));return 1
    print(f'Emitted {len(jobs)} units ({len(ordinary)} ordinary runtime helpers)',flush=True)
    raw_text={s:replace_names(path_for('raw',s,'.ll').read_text(),{}) for s,g in jobs if s not in ordinary}
    host_renames=dict(line.split() for line in (ROOT/'config/pc/host_symbol_renames.txt').read_text().splitlines() if line.strip())
    for g,sources in groups.items():
        for s in sources:raw_text[s]=replace_names(raw_text[s],host_renames)
    native_defs=set().union(*(definitions(raw_text[s]) for s in natives if s not in ordinary))
    for s in ordinary:
        result=subprocess.run(['nm','-g',str(path_for('obj',s,'.o'))],capture_output=True,text=True)
        native_defs|={line.split()[-1][1:] for line in result.stdout.splitlines() if len(line.split())==3 and line.split()[1]!='U'}
    group_defs={g:set().union(*(definitions(raw_text[s])|set(inspect(raw_text[s])['globals']) for s in sources)) for g,sources in groups.items()}
    renames={}
    for name,pattern,identifier,bank in modules:
        if not bank:renames[name]={};continue
        others=set().union(*(symbols for g,symbols in group_defs.items() if g!=name))
        clashes=group_defs[name]&others
        if name in GATED_MODULES:clashes|=group_defs[name]
        renames[name]={symbol:name+'__'+symbol for symbol in clashes}
        for s in groups[name]:raw_text[s]=replace_names(raw_text[s],renames[name])
    pin_maps={}
    for group in groups:
        pins=dict(address_tables['SLUS_014.11']);pins.update(address_tables.get('main_menu',{}))
        if group!='resident':pins.update({renames.get(group,{}).get(k,k):v for k,v in address_tables.get(group,{}).items()})
        pin_maps[group]=pins
    pin_maps['native']={**address_tables['SLUS_014.11'],**address_tables.get('main_menu',{})}
    for table in address_tables.values():
        for symbol,address in table.items():pin_maps['native'].setdefault(symbol,address)
    for s,g in jobs:
        if s not in ordinary and g!='native':raw_text[s]=drop_functions(raw_text[s],native_defs)
    linked_defs=native_defs|set().union(*(definitions(raw_text[s]) for g,ss in groups.items() for s in ss))
    rows=list(csv.DictReader((ROOT/'config/slus_01411/functions.csv').open()))
    for row in rows:row['name']=host_renames.get(row['name'],row['name'])
    for name,_,identifier,bank in modules:
        for row in csv.DictReader((ROOT/f'config/slus_01411/overlays/{module_config.get(name,name)}_functions.csv').open()):
            row['name']=host_renames.get(row['name'],row['name'])
            row['name']=renames.get(name,{}).get(row['name'],row['name']);row['bank']=bank;row['identifier']=identifier if bank else 0
            if name not in GATED_MODULES:rows.append(row)
    by_address={int(row['address'],16):row['name'] for row in rows if not row.get('bank')}
    aliases={}
    for s,g in jobs:
        if s in ordinary:continue
        declarations=set(inspect(raw_text[s])['declarations'])
        for symbol in declarations-linked_defs:
            if g == 'native' and symbol in host_renames:continue
            address=pin_maps[g].get(symbol)
            if address is None and re.fullmatch(r'func_[89A-Fa-f0-9]{8}',symbol):address=int(symbol[5:],16)
            target=by_address.get(address)
            if target and target!=symbol and target in linked_defs:aliases[symbol]=target
        raw_text[s]=replace_names(raw_text[s],aliases)
    checked_seen = set().union(*(set(inspect(text)['declarations']) & CHECKED_LIBC for text in raw_text.values()))
    missing_checked = sorted(name for name in checked_seen if 'GuestRuntime_' + name not in native_defs)
    if missing_checked:
        raise SystemExit('Fortified native pointer bridges required: ' + ', '.join(missing_checked))
    libc_renames = {name:'GuestRuntime_'+name for name in HOST_LIBC | {'malloc','calloc','realloc','free'} | checked_seen}

    for source in raw_text:
        raw_text[source] = replace_names(raw_text[source],libc_renames)
    registrations = {}
    def adapt(job):
        source,group=job
        if source in ordinary:return source,0
        ir=path_for('ir',source,'.ll');obj=path_for('obj',source,'.o')
        try:
            routine = 'GuestRuntime_RegisterUnit_' + hashlib.sha256(source.encode()).hexdigest()[:16]
            registrations[source] = routine
            text=translate(raw_text[source],pin_maps[group],routine, game_unit=group != 'native')
            if args.optimize: text=optimize_translated_ir(text)
        except TranslationError as error:path_for('logs',source,'.transform.log').write_text(str(error));return source,1
        if not ir.exists() or ir.read_text()!=text:ir.write_text(text)
        if obj.exists() and obj.stat().st_mtime>=max(ir.stat().st_mtime,Path(__file__).stat().st_mtime,(ROOT/'tools/pc/translate_guest_ir.py').stat().st_mtime):return source,0
        return source,run_logged([cc,'-isysroot',sdk,'-O2' if args.optimize else '-O0','-fno-strict-aliasing','-c',str(ir),'-o',str(obj)],path_for('logs',source,'.object.log'))
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:adapted=list(pool.map(adapt,jobs))
    failures=[s for s,status in adapted if status]
    (build/'summary.json').write_text(json.dumps({'units':len(jobs),'failures':failures,'groups':{g:len(v) for g,v in groups.items()},'ordinary':sorted(ordinary),'aliases':aliases,'renames':renames},indent=2)+'\n')
    if failures:print('Transform/object failures:',len(failures));print('\n'.join(failures));return 1
    print(f'Compiled {len(jobs)} ARM64 objects',flush=True)
    if args.compile_only:return 0
    all_declarations=set().union(*(set(inspect(text)['declarations']) for text in raw_text.values()))
    known_game={row['name'] for row in rows}
    stub_names = known_game | set(host_renames.values()) | {name for name in all_declarations if re.fullmatch(r'func_[89A-Fa-f0-9]{8}',name)}
    # Legacy direct name for the shared-bank name-entry entry point. Its
    # native implementation belongs to the active password/name-entry module,
    # so never register the bridge itself as a resident function.
    direct_overlay_bridges = {name: details[0] for name, details in DIRECT_OVERLAY_ENTRIES.items()}
    direct_overlay_bridges = {name: address for name, address in direct_overlay_bridges.items()
                              if name in all_declarations and name not in linked_defs}
    # The LLVM verifier and the typed bridge declarations validate these imports.
    stubs=sorted((all_declarations-linked_defs-HOST_LIBC-set(host_renames)-set(direct_overlay_bridges))&stub_names)
    if set(stubs)&set(host_renames):raise SystemExit('Refusing to override native libc with guest stubs')
    bridges=[(0x8013A004,'Memories_ModelPrimaryControlA'),(0x8013B004,'Memories_ModelVariantControlA'),
             (0x801462B0,'Memories_DuelEffectControl'),(0x8017A004,'Memories_ModelPrimaryControlB'),(0x8017B004,'Memories_ModelVariantControlB')]
    mapped=[(int(r['address'],16),r['name'],r.get('bank',0),r.get('identifier',0)) for r in rows if r['name'] in linked_defs|set(stubs)]
    mapped += [(a,n,0,0) for a,n in bridges if n in linked_defs]
    # The typed effect bridge includes the request header, which already
    # declares these functions. Do not redeclare them with erased signatures.
    typed_declarations = ({'DuelEffect_AllocateRequest', 'DuelEffect_CreateRequest',
                           'DuelEffect_FindFreeRequest', 'DuelEffect_UpdateRequests',
                           'Memories_DuelEffectControl'}
                          if 'func_801462B0' in direct_overlay_bridges else set())
    declarations=''.join(f'extern void {name}(void);\n' for name in sorted({r[1] for r in mapped}-set(stubs)-typed_declarations))
    tables='#include "pc/guest/image.h"\n#include "pc/mods/exports.h"\n#include "pc/guest/translated_runtime.h"\n#include <stdint.h>\n'
    tables += ''.join(emit_bridge(name) for name in direct_overlay_bridges)
    tables+=''.join(f'extern void {name}(void);\n' for name in registrations.values())
    tables+='void GuestRuntime_RegisterAllGlobals(void) {\n'+''.join(f'  {name}();\n' for name in registrations.values())+'}\n'
    tables+='const unsigned Memories_GameFingerprint = 0x'+hashlib.sha256(''.join(raw_text.values()).encode()).hexdigest()[:8]+'u;\n'
    tables+='const char Memories_Version[] = "experimental-macos-arm64";\n'
    tables+=''.join(f'void {n}(void) {{ Memories_Unimplemented("{n}"); }}\n' for n in stubs)+declarations
    tables+='const MemoriesGuestFunction Memories_FunctionMap[] = {\n'+''.join(f'{{0x{a:08x}u, {n}, 0x{int(b):08x}u, 0x{int(i):x}u}},\n' for a,n,b,i in sorted(mapped))+'};\n'
    tables+=f'const unsigned Memories_FunctionMapCount = {len(mapped)};\n'
    tables += emit_native_calls(mapped, raw_text.values(), stubs)
    shared=[(n,i,b) for n,_,i,b in modules if b and n not in GATED_MODULES]
    tables+='const MemoriesModule Memories_Modules[] = {\n'+''.join(f'{{"{n}",0x{b:08x}u,0x{i:x}u,0,0,0,0}},\n' for n,i,b in shared)+'};\n'
    tables+=f'const unsigned Memories_ModuleCount = {len(shared)};\n'
    # ELF i386 code mods cannot bind native ARM64 code. Empty exports accurately
    # report no supported code-mod ABI; asset mod support remains native.
    tables+='const MemoriesModExport Memories_ModExports[] = {{0,0}};\nconst unsigned Memories_ModExportCount = 0;\n'
    generated_tables=build/'tables.c';generated_tables.write_text(tables);tables_obj=build/'tables.o'
    status=run_logged([cc,*flags,'-c',str(generated_tables),'-o',str(tables_obj)],build/'logs/tables.log')
    if status:raise SystemExit('Table compilation failed: '+str(build/'logs/tables.log'))
    command=[cc,'-isysroot',sdk,*[str(path_for('obj',s,'.o')) for s,g in jobs],str(tables_obj),
             *[str(dependencies/'lib'/name) for name in ['libfreetype.a','libpng16.a','libz.a','libSDL3.a']],
             '-liconv','-framework','Cocoa','-framework','IOKit',
             '-framework','CoreVideo','-framework','CoreAudio','-framework','AudioToolbox','-framework','Metal',
             '-framework','QuartzCore','-framework','GameController','-framework','UniformTypeIdentifiers',
             '-framework','CoreMedia','-framework','AVFoundation','-framework','OpenGL','-framework','Foundation',
             '-framework','CoreText','-framework','ForceFeedback','-framework','Carbon','-framework','CoreHaptics',
             '-o',str(build/'memories-arm64')]
    (build/'link-command.json').write_text(json.dumps(command,indent=2)+'\n')
    status=run_logged(command,build/'logs/link.log')
    print('Link '+('failed: '+str(build/'logs/link.log') if status else 'succeeded: '+str(build/'memories-arm64')),flush=True)
    return status

if __name__=='__main__':raise SystemExit(main())
