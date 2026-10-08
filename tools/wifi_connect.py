"""Bounded Windows open-AP test, with restoration of the existing Wi-Fi profile.

No credentials are read/exported. A unique manual-connect profile is created
for TUVL01 only and removed in finally. Requires English netsh status output.
"""
import argparse,json,os,pathlib,re,socket,subprocess,tempfile,time,uuid
from xml.sax.saxutils import escape

def netsh(*args):
    result=subprocess.run(['netsh','wlan',*args],capture_output=True,timeout=10)
    text=result.stdout.decode('utf8',errors='replace')
    if result.returncode:raise RuntimeError('netsh failed: '+text.strip())
    return text

def status(interface):
    text=netsh('show','interfaces')
    chunks=re.split(r'(?m)^\s*Name\s*:',text)[1:]
    for chunk in chunks:
        if chunk.splitlines()[0].strip()!=interface:continue
        fields={}
        for key in ('State','SSID','AP BSSID','Profile'):
            match=re.search(r'(?m)^\s*'+re.escape(key)+r'\s*:\s*(.*?)\s*$',chunk)
            if match:fields[key]=match[1]
        if 'State' not in fields:raise RuntimeError('Cannot parse English netsh state')
        return fields
    raise RuntimeError('Interface not found; test requires English netsh output')

def wait_connected(interface,profile,seconds,ssid=None):
    end=time.monotonic()+seconds
    last={}
    while time.monotonic()<end:
        last=status(interface)
        if (last.get('State')=='connected' and last.get('Profile')==profile
                and (ssid is None or last.get('SSID')==ssid)):
            return True,last
        time.sleep(.5)
    return False,last

def restore_connection(interface,profile,ssid):
    # The previous AP can briefly disappear from the scan cache after disconnect.
    errors=[];last={}
    for attempt in range(3):
        try:
            netsh('connect','name='+profile,'interface='+interface)
        except RuntimeError as e:
            errors.append(str(e))
            netsh('show','networks','interface='+interface)
            if attempt<2:time.sleep(2)
            continue
        connected,last=wait_connected(interface,profile,25,ssid)
        if connected:return True,last,errors
    return False,last,errors

def burst_test(udp,server,count,window,size):
    """Finite echo load; unique payloads, no retransmission or hidden losses."""
    nonce=os.urandom(8);payloads=[];pending={};seen=set();duplicates=0;sent=0
    started=time.monotonic();deadline=started+25
    udp.settimeout(.1)
    while (sent<count or pending) and time.monotonic()<deadline:
        while sent<count and len(pending)<window:
            payload=b'TVL1'+nonce+sent.to_bytes(4,'big')+os.urandom(size-16)
            payloads.append(payload);udp.sendto(payload,(server,4201))
            pending[sent]=time.monotonic();sent+=1
        try:
            received,source=udp.recvfrom(2048)
        except socket.timeout:
            received=None
        if received is not None:
            if source!=(server,4201) or len(received)!=size or received[:12]!=b'TVL1'+nonce:
                raise RuntimeError('Unexpected burst packet/source')
            sequence=int.from_bytes(received[12:16],'big')
            if sequence>=sent or received!=payloads[sequence]:
                raise RuntimeError('Burst sequence/payload mismatch')
            if sequence in seen:duplicates+=1
            seen.add(sequence);pending.pop(sequence,None)
        now=time.monotonic()
        for sequence,stamp in list(pending.items()):
            if now-stamp>=2:del pending[sequence]
    elapsed=time.monotonic()-started
    return {'requested':count,'sent':sent,'received':len(seen),'lost':sent-len(seen),
            'duplicates':duplicates,'payload_bytes':size,'window':window,
            'elapsed_s':round(elapsed,3),'echo_payload_mbps':round(len(seen)*size*8/elapsed/1e6,4)}

def data_test(interface,result,burst,window,mtu,payload_size):
    """Check a DHCP lease and actual payload roundtrips, without static IP edits."""
    server='192.168.74.1';client='192.168.74.2'
    env=os.environ.copy();env['TUVL01_TEST_INTERFACE']=interface
    command=('Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias '
             '$env:TUVL01_TEST_INTERFACE -ErrorAction Stop | '
             "Where-Object { $_.AddressState -eq 'Preferred' } | "
             'Select-Object -ExpandProperty IPAddress | ConvertTo-Json -Compress')
    deadline=time.monotonic()+18
    while True:
        proc=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],
                            env=env,capture_output=True,timeout=8)
        if proc.returncode:
            # A newly connected interface can temporarily have no IPv4 entry.
            # Keep the existing lease deadline rather than fail the first query.
            if time.monotonic()>=deadline:
                raise RuntimeError('Cannot read test interface IPv4 addresses before lease deadline')
            time.sleep(.5)
            continue
        addresses=json.loads(proc.stdout.decode('utf8').strip() or '[]')
        if isinstance(addresses,str):addresses=[addresses]
        if client in addresses:break
        if time.monotonic()>=deadline:raise RuntimeError('DHCP lease was not observed')
        time.sleep(.5)
    result['data']={'lease':client,'preferred':True,'server':server,'udp_echo_lengths':[],
                    'udp_echo_ms':[],'icmp_timeout_ms':3000}
    ping=subprocess.run(['ping','-n','2','-w','3000','-S',client,server],capture_output=True,timeout=10)
    result['data']['icmp_returncode']=ping.returncode
    result['data']['icmp_replies']=ping.stdout.upper().count(b'TTL=')
    result['data']['icmp_output']=ping.stdout.decode('utf8',errors='replace')
    lengths=[1,31,188,376,454]
    if mtu:lengths.extend([1316,1472])
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.bind((client,0));udp.settimeout(3)
        for n in lengths:
            payload=os.urandom(n);start=time.monotonic();udp.sendto(payload,(server,4201))
            received,source=udp.recvfrom(2048)
            if source!=(server,4201) or received!=payload:
                raise RuntimeError('UDP source/payload mismatch')
            result['data']['udp_echo_lengths'].append(n)
            result['data']['udp_echo_ms'].append(round((time.monotonic()-start)*1000,1))
        if burst:result['data']['burst']=burst_test(udp,server,burst,window,payload_size)
    if ping.returncode or result['data']['icmp_replies']!=2:
        raise RuntimeError('UDP succeeded but two ICMP echo replies were not observed')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface',required=True)
    p.add_argument('--restore-profile',required=True)
    p.add_argument('--seconds',type=float,default=12)
    p.add_argument('--data',action='store_true',help='Verify DHCP, ping and UDP echo before restoration')
    p.add_argument('--burst',type=int,default=0,help='Finite echo datagrams after --data (0..512)')
    p.add_argument('--window',type=int,default=4,help='Burst packets in flight (1..8)')
    p.add_argument('--mtu',action='store_true',help='Include 1316/1472B UDP echoes')
    p.add_argument('--payload-size',type=int,choices=[188,376,1316,1472],default=376)
    p.add_argument('--ts-output',type=pathlib.Path,help='Receive actual tuner TS after DHCP validation')
    p.add_argument('--ts-log',type=pathlib.Path)
    p.add_argument('--ts-seconds',type=float,default=30)
    p.add_argument('--ts-forward-port',type=int,help='Forward actual TS to localhost UDP for a player')
    p.add_argument('--uart-port',default='COM3')
    a=p.parse_args()
    if a.ts_forward_port is not None and (not a.ts_output or not 1024<=a.ts_forward_port<=65535):
        p.error('--ts-forward-port requires --ts-output and port 1024..65535')
    if a.ts_output and not a.ts_log:a.ts_log=a.ts_output.with_suffix('.uart.bin')
    if not 1<=a.seconds<=30:p.error('--seconds must be 1..30')
    if not 0<=a.burst<=512 or not 1<=a.window<=8:p.error('Burst/window outside bounds')
    if a.burst and not a.data:p.error('--burst requires --data')
    if a.mtu and not a.data:p.error('--mtu requires --data')
    before=status(a.interface)
    if before.get('State')!='connected' or before.get('Profile')!=a.restore_profile:
        raise RuntimeError('Existing connection does not match restore profile; no changes made')
    profile='TUVL01-test-'+uuid.uuid4().hex
    xml=('<?xml version="1.0"?>'
        '<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
        '<name>'+escape(profile)+'</name><SSIDConfig><SSID><name>TUVL01</name>'
        '</SSID></SSIDConfig><connectionType>ESS</connectionType>'
        '<connectionMode>manual</connectionMode><MSM><security><authEncryption>'
        '<authentication>open</authentication><encryption>none</encryption>'
        '<useOneX>false</useOneX></authEncryption></security></MSM></WLANProfile>')
    result={'connected':False,'restored':False};created=False;attempted=False
    with tempfile.TemporaryDirectory(prefix='tuvl01-wifi-') as td:
        path=pathlib.Path(td)/'profile.xml';path.write_text(xml,encoding='utf8')
        try:
            netsh('add','profile','filename='+str(path),'interface='+a.interface,'user=current')
            created=True;attempted=True
            netsh('connect','name='+profile,'ssid=TUVL01','interface='+a.interface)
            result['connected'],result['test_state']=wait_connected(
                a.interface,profile,a.seconds,'TUVL01')
            if a.ts_output:
                if not result['connected']:raise RuntimeError('Cannot receive TS without association')
                data_test(a.interface,result,0,a.window,a.mtu,a.payload_size)
                from ts_receive import receive
                result['ts']=receive(a.uart_port,a.ts_output,a.ts_log,a.ts_seconds,a.ts_forward_port)
            if a.data:
                if not result['connected']:raise RuntimeError('Cannot test data without association')
                data_test(a.interface,result,a.burst,a.window,a.mtu,a.payload_size)
        finally:
            try:
                if attempted:
                    netsh('disconnect','interface='+a.interface)
                    result['restored'],result['restore_state'],result['restore_errors']=restore_connection(
                        a.interface,a.restore_profile,before.get('SSID'))
            finally:
                if created:netsh('delete','profile','name='+profile,'interface='+a.interface)
                print(json.dumps(result,ensure_ascii=False))
    if not result['restored']:raise RuntimeError('Original connection restoration was not verified')
    return 0 if result['connected'] else 1
if __name__=='__main__':raise SystemExit(main())
