"""Verify exact HTV31 2.44 ARM32 register-read and ioctl motifs.

No firmware execution, full disassembly, or IQ acquisition claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

SOURCE_SHA = "59a758d0b61ded96690c32bcee42d144b5250e6edc278c02d2d7ffd1bdc66067"
CALLS = [(13328, 9892), (13374, 9892), (13606, 9892), (13672, 9892), (14010, 9892), (14314, 9892), (14846, 9892), (15120, 9892), (15194, 9892), (15364, 9892), (15638, 9892), (15704, 9892), (15780, 9928), (16034, 9892), (16388, 9892), (16800, 9892), (17360, 9892), (17812, 9892), (18184, 9892), (18460, 9892), (18930, 9892), (19022, 9892), (19212, 9892), (19470, 9892), (19598, 9892), (19742, 9892), (19920, 9892), (19982, 9892), (20102, 9892), (23718, 9892), (23968, 9892), (24160, 9892), (24274, 9892), (25762, 9892), (25854, 9892), (25976, 9892), (26078, 9892), (28064, 9892), (28176, 9892), (28410, 9892), (28698, 9892), (29118, 9892), (29488, 9892), (30044, 9892), (30380, 9892), (30540, 9892), (32954, 9892), (34282, 9892), (34594, 9892), (34916, 9892), (35416, 9892), (35824, 9892), (36626, 9892), (37184, 9892), (37246, 9892), (37320, 9892), (38202, 9892), (38710, 9892)]

def analyze(raw):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError("Requires exact HTV31 2.44 ARM32 libtuner552.so")
    if raw[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", raw, 18)[0] != 40:
        raise ValueError("Not ARM32 little-endian ELF")
    phoff = struct.unpack_from("<I", raw, 28)[0]
    phsize, phnum = struct.unpack_from("<HH", raw, 42)
    segments = []
    for n in range(phnum):
        typ, off, va, _, size, _, _, _ = struct.unpack_from("<8I", raw, phoff + n * phsize)
        if typ == 1:
            segments.append((off, va, size))
    def offset(va, width=4):
        for off, start, size in segments:
            if start <= va and va + width <= start + size:
                return off + va - start
        raise ValueError("VA not supplied")
    def blob(va, size):
        off = offset(va, size)
        return raw[off:off + size]
    def word(va):
        return struct.unpack("<I", blob(va, 4))[0]
    def blx(va):
        a, b = struct.unpack("<HH", blob(va, 4))
        if a & 0xf800 != 0xf000 or b & 0xd001 != 0xc000:
            raise ValueError("Expected immediate Thumb BLX")
        s = a >> 10 & 1
        i1 = 1 ^ (b >> 13 & 1) ^ s
        i2 = 1 ^ (b >> 11 & 1) ^ s
        imm = s << 24 | i1 << 23 | i2 << 22 | (a & 1023) << 12 | (b & 2046) << 1
        if s:
            imm -= 1 << 25
        return (((va + 4) & ~3) + imm) & 0xffffffff
    for site, target in CALLS:
        if blx(site) != target:
            raise ValueError("Read API call target changed")
    if blob(0x9570, 4) != bytes.fromhex("00207047"):
        raise ValueError("Shared zero-return stub changed")
    # i2crd: device6C, startF2, count20; destination is stack u16 array.
    for va, value in ((0x3d9a, 0x21f2), (0x3d9c, 0x2314), (0x3d9e, 0x206c), (0x3dda, 0x2c14)):
        if struct.unpack("<H", blob(va, 2))[0] != value:
            raise ValueError("i2crd fixed argument changed")
    if blx(0x862a) != 0x2650:
        raise ValueError("Descriptor ioctl call changed")
    # TBB bytes are data, not instructions; destination=table start +2*byte.
    table = blob(0x7b16, 10)
    expected = [0x7b20, 0x7b3e, 0x7b3e, 0x7b2e, 0x7b3e, 0x7b3e, 0x7b3a, 0x7b3e, 0x7b32, 0x7b36]
    destinations = [0x7b16 + 2 * v for v in table]
    if destinations != expected or blob(0x7b0e, 2) != bytes.fromhex("0929"):
        raise ValueError("ioctl switch changed")
    ioctl_numbers = [word(va) for va in (0x7b48, 0x7b4c, 0x7b50, 0x7b54, 0x7b58)]
    if ioctl_numbers != [0x400c6401, 0x800c6402, 0x400c6405, 0x400c6406, 0x800c6403]:
        raise ValueError("ioctl literal changed")
    if word(0x6330) != 0x47800000 or blob(0x605e, 4) != bytes.fromhex("dfedb43a") or blob(0x6106, 4) != bytes.fromhex("dfed8a8a"):
        raise ValueError("CN float literal references changed")
    return {
        "source_sha256": SOURCE_SHA,
        "verified_read_api_calls": len(CALLS),
        "scope": "Fixed BLX targets and motifs only; original linear Thumb candidates need function-level inspection. No complete indirect-call or dataflow proof.",
        "i2crd": {"device": "6C", "start": "F2", "register_count": 20},
        "shared_zero_return_stub_VA": "9570",
        "ioctl_case_destinations": [f"{v:08X}" for v in destinations],
        "CN_6330_literal_float": 65536.0,
        "IQ_verified": False,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze(args.library.read_bytes()), indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")

if __name__ == "__main__":
    main()
