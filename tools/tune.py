"""Send an explicit tuner profile to RAM firmware; never writes SPI NOR.

UHF RF/ADC constants remain experimental inputs, not certified defaults.
"""
import argparse,json,pathlib,struct,time,zlib
from uart import Transport

def encode(profile):
    mode={'vlf-control':0,'uhf-partial-experimental':1,'uhf-native-candidate':2}[profile['mode']]
    rf=profile['rf_khz']
    if not isinstance(rf,int) or not ((90000<=rf<=108000) if mode==0 else (470000<=rf<=770000)):
        raise ValueError('Frequency outside selected receive band')
    p=bytearray(b'TUN1'+struct.pack('>I',rf))
    for field in ('fad','nco'):
        value=profile[field]
        if not isinstance(value,int) or not 0<=value<=0xffffff:raise ValueError(field)
        p.extend(value.to_bytes(3,'big'))
    p.extend(bytes([profile['sysset'],profile['p_m']]))
    pk=profile['p_k']
    if not isinstance(pk,int) or not 0<=pk<1<<20:raise ValueError('p_k')
    p.extend(pk.to_bytes(3,'big'))
    for field in ('tncop1','tncop2','tncop3','tncop4','tncop6','tncop7','adclksel'):
        p.extend(bytes([profile[field]]))
    dtv=profile['dtvset']
    if (dtv!=0x16 if mode==2 else dtv&0xc0!=(0x40 if mode else 0xc0)):
        raise ValueError('dtvset mode mismatch')
    p.extend(bytes([dtv,mode]))
    if not profile['p_m']:raise ValueError('p_m must be nonzero')
    return bytes(p)+struct.pack('>I',zlib.crc32(p))

def send_profile(transport,data):
    if len(data)!=32:raise ValueError('Profile must be 32 bytes')
    # No UART flow control: let the polling receiver drain between bytes.
    # 32 * 10ms is below the target's 3-second transport deadline.
    for byte in data:
        transport.write(bytes([byte]))
        time.sleep(.01)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=pathlib.Path,required=True)
    parser.add_argument('--port',required=True)
    parser.add_argument('--log',type=pathlib.Path,required=True)
    args=parser.parse_args()
    data=encode(json.loads(args.profile.read_text(encoding='utf-8-sig')))
    args.log.parent.mkdir(parents=True,exist_ok=True)
    with args.log.open('ab') as log:
        t=Transport(args.port,log)
        try:
            t.write(b'i');t.expect('UART application')
            t.write(b'w');t.expect('TUNE profile ready bytes=32');send_profile(t,data)
            result=t.wait(lambda s:s.startswith('TUNE end status='),15)
            print(result)
            t.write(b'i');t.expect('UART application')
            print('UART application remains active after tuning')
            if not result.endswith('=sequence-complete'):raise RuntimeError(result)
        finally:t.ser.close()

if __name__=='__main__':main()
