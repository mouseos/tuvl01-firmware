"""Verify MN885521 AA/FF generator data through existing SPI and UART; RAM only."""
import argparse
import datetime
import hashlib
import json
import pathlib
import re

from uart import Transport
from ts_capture import validate_capture


def register(t, bank, reg, value=None):
    t.write(bytes([26, ord('r' if value is None else 'w'), bank, reg,
                   0 if value is None else value]))
    line = t.wait(lambda s: s.startswith('REG bank='), 5)
    end = t.wait(lambda s: s.startswith('REG access end status='), 5)
    match = re.fullmatch(
        r'REG bank=([0-9a-f]{8}) reg=([0-9a-f]{8}) before=([0-9a-f]{8})(?: wrote=[0-9a-f]{8} after=([0-9a-f]{8}))?', line)
    if (end != 'REG access end status=done' or match is None
            or (int(match[1], 16), int(match[2], 16)) != (bank, reg)):
        raise RuntimeError('Register transaction failed')
    if value is not None and (match[4] is None or int(match[4], 16) != value):
        raise RuntimeError('Register write readback mismatch')
    return int(match[3] if value is None else match[4], 16)


def capture(t, output):
    data = bytearray()
    summary = None
    t.write(bytes([23]))
    t.expect('TS capture start')

    def receive(line):
        nonlocal summary
        if line.startswith('TS DATA '):
            if len(data) >= 128 * 188 or not re.fullmatch(r'TS DATA [0-9a-f]{376}', line):
                raise ValueError('Invalid or excessive capture data')
            data.extend(bytes.fromhex(line[8:]))
        if line.startswith('TS capture packets='):
            summary = line
        return line.startswith('TS capture end status=')

    end = t.wait(receive, 20)
    output.write_bytes(data)
    match = re.fullmatch(
        r'TS capture packets=([0-9a-f]{8}) crc=([0-9a-f]{8}) empty=([0-9a-f]{8})'
        r' overrun=([0-9a-f]{8}) underrun=([0-9a-f]{8}) reserved=([0-9a-f]{8})', summary or '')
    if match is None or end.endswith('=failed'):
        raise RuntimeError('Incomplete or failed capture')
    packets, crc, empty, over, under, reserved = [int(s, 16) for s in match.groups()]
    validate_capture(data, packets, crc)
    return data, dict(bytes=len(data), frames=packets, uart_crc_verified=True,
                      empty=empty, overrun=over, underrun=under, reserved=reserved,
                      sha256=hashlib.sha256(data).hexdigest(), outcome=end)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--log', type=pathlib.Path, required=True)
    parser.add_argument('--output-dir', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope='E7 + Main1 08 bit0, normal SPI; partial factory recipe',
                  iq_identified=False, runs=[])
    original = {}
    dirty = False
    with args.log.open('ab') as log:
        t = Transport(args.port, log)
        try:
            t.write(b'i')
            t.expect('UART application')
            keys = [(0x61, 0xe7), (0x61, 8), (0x61, 0xed), (0x61, 0x97),
                    (0x61, 0xf3), (0x62, 0xe8), (0x62, 0xf8)]
            original = {key: register(t, *key) for key in keys}
            report['baseline'] = {f'{b:02X}:{r:02X}': f'{v:02X}' for (b, r), v in original.items()}
            if (original[(0x61, 0xe7)] != 0 or original[(0x61, 8)] != 0
                    or original[(0x61, 0xed)] != 0x16
                    or original[(0x61, 0x97)] & 0x18 != 0x10
                    or original[(0x61, 0xf3)] != 0xe0
                    or original[(0x62, 0xe8)] & 15 != 2
                    or original[(0x62, 0xf8)] & 15 != 1):
                raise RuntimeError('Requires known fullseg/SPI state and frame lock')
            for label, source, control, expected in [('before', 0, 0, None),
                    ('round', 1, 1, None),
                    ('aa', 0x11, 1, 0xaa), ('ff', 0x21, 1, 0xff),
                    ('after', 0, 0, None)]:
                dirty = True  # Include uncertain writes in restoration.
                if register(t, 0x61, 0xe7) != source:
                    register(t, 0x61, 0xe7, source)
                current = register(t, 0x61, 8)
                if current & 1 != control:
                    register(t, 0x61, 8, (current & ~1) | control)
                data, result = capture(t, args.output_dir / f'{label}.bin')
                if register(t, 0x61, 0xe7) != source or register(t, 0x61, 8) & 1 != control:
                    raise RuntimeError('Source/control changed during capture')
                if expected is not None:
                    result['expected_byte'] = f'{expected:02X}'
                    result['pattern_verified'] = len(data) == 128 * 188 and all(x == expected for x in data)
                report['runs'].append(dict(label=label, **result))
                print(f'{label}: {len(data)} bytes, CRC verified', flush=True)
                if expected is not None and not result['pattern_verified']:
                    raise RuntimeError(f'{label} generator pattern mismatch or empty capture')
        except Exception as error:
            report['failure'] = str(error)
        finally:
            failures = []
            if dirty:
                for key, mask in [((0x61, 0xe7), 0xff), ((0x61, 8), 1)]:
                    try:
                        current = register(t, *key)
                        register(t, *key, (current & ~mask) | (original[key] & mask))
                    except Exception as error:
                        failures.append(f'{key[0]:02X}:{key[1]:02X}: {error}')
            try:
                for key in [(0x61, 0xe7), (0x61, 8), (0x62, 0xe8), (0x62, 0xf8)]:
                    if key in original and register(t, *key) != original[key]:
                        raise RuntimeError('Final register restoration mismatch')
                t.write(b'i')
                t.expect('UART application')
            except Exception as error:
                failures.append(str(error))
            report['restoration'] = 'failed' if failures else 'verified'
            report['restore_errors'] = failures
            t.ser.close()
    (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Restoration:', report['restoration'])
    if 'failure' in report or report['restore_errors']:
        raise SystemExit('Diagnostic failed; see report.json and UART log')


if __name__ == '__main__':
    main()
