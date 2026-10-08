"""Volatile credential provisioning only; does not connect WPA2 or persist SPI."""
import argparse,getpass,re,time
from wpa_packet import make_packet,wipe_packet
TERMINAL={b'WPA provisioning accepted; association=unimplemented',b'WPA provisioning rejected',
    b'WPA provisioning input-timeout',b'WPA provisioning target-timeout',b'WPA provisioning target-refused'}
WAITING=b'WPA waiting-for-resync version=1'
KNOWN=TERMINAL|{WAITING,b'UART application',b'WPA protocol=1 provisioning-only',
    b'WPA target bytes=7 version=1',b'WPA credentials bytes=148 version=1',
    b'WPA UART resynchronized',b'WPA volatile session closed',
    b'WPA provisioning refused-active',b'WPA provisioning clock-failed',
    b'WPA association refused',b'WPA association failed',
    b'WPA association ready; protection=unimplemented',
    b'WPA command refused-active',b'WPA AIS cleanup unresolved',
    b'WPA key cleanup unresolved',b'WPA cleanup refused-unresolved'}
def write_all(ser,p):
    offset=0
    while offset<len(p):
        written=ser.write(memoryview(p)[offset:])
        if not written:raise RuntimeError('UART write made no progress')
        offset+=written
    ser.flush()
def wait(ser,wanted,timeout=5):
    end=time.monotonic()+timeout;pending=bytearray()
    while time.monotonic()<end:
        data=ser.readline()
        if not data:continue
        pending.extend(data)
        if len(pending)>512:raise RuntimeError('Unrecognized UART response')
        if not pending.endswith(b'\n'):continue
        line=bytes(pending).strip();pending.clear()
        if re.fullmatch(rb'RTOS tick=[0-9a-f]{8}',line):continue
        if line.startswith(b'WIFI '):continue # Radio diagnostics are not protocol ACKs; never echo their contents.
        if line not in KNOWN:raise RuntimeError('Unrecognized UART response')
        if line in {b'WPA AIS cleanup unresolved',b'WPA key cleanup unresolved',b'WPA cleanup refused-unresolved'}:
            raise RuntimeError('Radio cleanup remains unresolved')
        if line in wanted:return line
        if line in TERMINAL or line.endswith((b'refused-active',b'clock-failed')):
            raise RuntimeError('Provisioning rejected by firmware')
    raise TimeoutError('Expected WPA UART protocol response not received')
def identify(ser):
    write_all(ser,b'i');wait(ser,{b'UART application'});wait(ser,{b'WPA protocol=1 provisioning-only'},1)
def resynchronize(ser):
    write_all(ser,b'\0');status=wait(ser,{WAITING}|TERMINAL,4)
    if status!=WAITING:write_all(ser,b'\0');wait(ser,{WAITING},1)
    write_all(ser,b'TUVL-WPA-RESYNC\n');wait(ser,{b'WPA UART resynchronized'},1)
def close_session(ser):
    identify(ser);write_all(ser,b'\x03');wait(ser,{b'WPA volatile session closed'})

def join_trial(ser):
    identify(ser);write_all(ser,b'\x04')
    try:
        status=wait(ser,{b'WPA association refused',b'WPA association failed',
            b'WPA association ready; protection=unimplemented'},25)
        if status!=b'WPA association ready; protection=unimplemented':
            raise RuntimeError('AIS association trial failed or was refused')
        return 'AIS association reported ready; WPA2/protection/IP are unverified; trial closed'
    finally:close_session(ser)
def provision(ser,ssid,ap,channel,passphrase):
    packet=make_packet(ssid,ap,channel,passphrase);entered=False;accepted=False
    try:
        identify(ser);write_all(ser,b'\x02');wait(ser,{b'WPA target bytes=7 version=1'});entered=True
        write_all(ser,bytes([channel])+ap);wait(ser,{b'WPA credentials bytes=148 version=1'})
        write_all(ser,packet);status=wait(ser,TERMINAL);accepted=status.startswith(b'WPA provisioning accepted;')
        if not accepted:raise RuntimeError('Credentials rejected by firmware')
    finally:
        wipe_packet(packet)
        if entered:
            resynchronize(ser)
            if not accepted:close_session(ser)
    return 'Volatile credentials accepted; association is not implemented'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
    group=p.add_mutually_exclusive_group();group.add_argument('--close',action='store_true');group.add_argument('--resync',action='store_true');group.add_argument('--join-trial',action='store_true')
    p.add_argument('--ssid');p.add_argument('--bssid');p.add_argument('--channel',type=int)
    a=p.parse_args()
    if not(a.close or a.resync or a.join_trial) and any(v is None for v in (a.ssid,a.bssid,a.channel)):
        p.error('--ssid, --bssid and --channel are required')
    import serial
    ser=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2);ser.dtr=False;ser.rts=False;ser.port=a.port
    try:
        if a.close or a.resync or a.join_trial:
            ser.open()
            if a.join_trial:print(join_trial(ser))
            elif a.close:close_session(ser);print('Volatile session closed')
            else:resynchronize(ser);print('UART protocol resynchronized')
        else:
            try:ap=bytes.fromhex(a.bssid.replace(':',''))
            except ValueError:p.error('Invalid BSSID format')
            password=getpass.getpass('AP passphrase: ').encode('ascii')
            ser.open();print(provision(ser,a.ssid.encode('utf-8'),ap,a.channel,password))
    except (ValueError,RuntimeError,TimeoutError,serial.SerialException):
        p.exit(1,'WPA provisioning did not complete; credentials are not logged.\n')
    finally:ser.close()
if __name__=='__main__':main()
