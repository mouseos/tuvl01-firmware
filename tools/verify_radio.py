"""Verify the bundled, hardware-tested MT5931 radio firmware before linking."""
import hashlib,pathlib

RADIO_SHA='06d43badbb669700c7cf94924c43a40779b428f3ceec8756813b0aaec2b4a68d'

def verify(data):
    if len(data)!=136576 or hashlib.sha256(data).hexdigest()!=RADIO_SHA:
        raise ValueError('Bundled MT5931 firmware size/hash mismatch')

if __name__=='__main__':
    radio=pathlib.Path(__file__).resolve().parents[1]/'firmware/mt5931.bin'
    verify(radio.read_bytes())
    print('Bundled MT5931 firmware verified')
