"""Verify an approved MT5931 image and generate its assembly descriptor."""
import argparse, hashlib, pathlib, zlib

RADIO_SHA='06d43badbb669700c7cf94924c43a40779b428f3ceec8756813b0aaec2b4a68d'
CANDIDATE_SHA='af345785369ee0a53efd85654810ba47463833186201fb3d3e9f9ac8195ca53c'
APPROVED={RADIO_SHA:136576,CANDIDATE_SHA:139776}

def verify(data, expected_sha=RADIO_SHA):
    if expected_sha not in APPROVED or len(data)!=APPROVED[expected_sha] or hashlib.sha256(data).hexdigest()!=expected_sha:
        raise ValueError('MT5931 firmware size/hash mismatch')

def configure(radio, output, expected_sha=RADIO_SHA):
    data=pathlib.Path(radio).read_bytes()
    verify(data,expected_sha)
    path=pathlib.Path(radio).as_posix()
    if any(c in path for c in '\"\n\r'):
        raise ValueError('Unsupported firmware path')
    content=(f'#define RADIO_FILE "{path}"\n'
             f'#define RADIO_LENGTH {len(data)}\n'
             f'#define RADIO_CRC 0x{zlib.crc32(data):08x}\n')
    output=pathlib.Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if not output.exists() or output.read_text()!=content:output.write_text(content)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--radio',default='firmware/mt5931.bin')
    parser.add_argument('--sha256',default=RADIO_SHA)
    parser.add_argument('--config',default='build/radio-config.h')
    args=parser.parse_args()
    configure(args.radio,args.config,args.sha256)
    print('MT5931 firmware size/hash verified')
