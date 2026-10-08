"""Build pinned BSD RSN sources for freestanding SH-2A big endian."""
import argparse,hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
VENDOR=ROOT/'third_party/wpa_supplicant'
PORT=ROOT/'rtos/wpa/port'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inputs():
    m=json.loads((VENDOR/'manifest.json').read_text())
    paths=[VENDOR/name for name in m['files']]
    paths += list(PORT.glob('*.c'))+list(PORT.glob('*.h'))
    paths += list((ROOT/'third_party/nanoprintf').iterdir())
    paths += [VENDOR/'manifest.json',ROOT/'src/wifi_wpa_console.c']
    return m,paths
def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',action='store_true');p.add_argument('--cc')
    a=p.parse_args();m,paths=inputs()
    if a.inputs:
        print(' '.join(path.relative_to(ROOT).as_posix() for path in paths));return
    if not a.cc:p.error('--cc is required')
    for name,entry in m['files'].items():
        if sha(VENDOR/name)!=entry['sha256']:raise ValueError('Pinned WPA source differs: '+name)
    nano=ROOT/'third_party/nanoprintf';nm=json.loads((nano/'manifest.json').read_text())
    for name,entry in nm['files'].items():
        if sha(nano/name)!=entry['sha256']:raise ValueError('Pinned nanoprintf source differs')
    common=['-m2a-nofpu','-mb','-Os','-g','-ffreestanding','-fno-builtin',
        '-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-fstack-usage',
        '-Wall','-Wextra','-Wno-unused-parameter','-Wno-unused-but-set-variable',
        '-Werror=implicit-function-declaration','-DOS_NO_C_LIB_DEFINES',
        '-DCONFIG_NO_STDOUT_DEBUG','-DCONFIG_NO_RC4','-DCONFIG_NO_TKIP',
        '-DCONFIG_NO_EAPOL','-DCONFIG_CRYPTO_INTERNAL',
        '-include','rtos/wpa/port/includes.h','-Irtos/wpa/port',
        '-Ithird_party/wpa_supplicant/src','-Ithird_party/wpa_supplicant/src/utils',
        '-Ithird_party/nanoprintf','-Iinclude']
    sources=[VENDOR/'src'/n for n in m['sources']]+sorted(PORT.glob('*.c'))
    sources += [ROOT/'src/wifi_wpa_console.c']
    build=ROOT/'build/wpa';build.mkdir(parents=True,exist_ok=True);objects=[]
    for source in sources:
        relative=source.relative_to(ROOT).as_posix()
        obj=build/(relative.replace('/','_')+'.o')
        flags=common+(['-Werror'] if source.is_relative_to(PORT) or source.parent==ROOT/'src' else [])
        subprocess.run([a.cc,*flags,'-c',relative,'-o',str(obj)],cwd=ROOT,check=True)
        objects.append(obj)
    subprocess.run(['sh-elf-ld','-r',*[str(p) for p in objects],'-o',str(build/'rsn-core.o')],check=True)
    print('WPA pinned BSD sources and independent port compiled for SH-2A BE')
if __name__=='__main__':main()
