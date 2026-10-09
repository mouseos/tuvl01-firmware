"""Finite direct UDP download diagnostic with Wi-Fi profile restoration."""
import argparse,hashlib,json,pathlib,re,socket,struct,sys,time
import wifi_connect
from uart import Transport
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface',required=True);p.add_argument('--restore-profile',required=True)
    p.add_argument('--uart-port',required=True);p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    original=wifi_connect.data_test;results=[]
    def diagnostic(interface,result,*args,**kwargs):
        results.append(result);original(interface,result,*args,**kwargs)
        client=result['data']['lease'];server=result['data']['server']
        payload_path=a.output.with_name(a.output.stem+'-payload.bin')
        trial={'payload_file':str(payload_path),'payload_bytes':1332,'received':0,'invalid':0,'reordered':0,'duplicates':0}
        result['tx_bench']=trial;packets={};last=-1;digest=hashlib.sha256()
        log_path=a.output.with_name(a.output.stem+'-uart.bin');trial['uart_log']=str(log_path)
        with log_path.open('ab') as log,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            udp.bind((client,4204));udp.settimeout(.2);t=Transport(a.uart_port,log)
            started=False
            try:
                t.write(b'i');t.expect('UART application');t.write(b'<')
                status=t.wait(lambda x:x.startswith('WIFI TX bench begin status='))
                if status!='WIFI TX bench begin status=active':raise RuntimeError(status)
                started=True;start=time.monotonic();first=last_time=None
                expected=bytes(i%251 for i in range(12,1332))
                while time.monotonic()-start<11.5:
                    try:data,source=udp.recvfrom(2048)
                    except socket.timeout:continue
                    now=time.monotonic()
                    if source!=(server,4204) or len(data)!=1332 or data[:4]!=b'TWT1':
                        trial['invalid']+=1;continue
                    seq,length=struct.unpack('!II',data[4:12])
                    if seq>=20000 or length!=1332 or data[12:]!=expected:
                        trial['invalid']+=1;continue
                    if seq in packets:trial['duplicates']+=1;continue
                    if seq<last:trial['reordered']+=1
                    last=seq;packets[seq]=data;digest.update(data)
                    if first is None:first=now
                    last_time=now
                counters=t.wait(lambda x:x.startswith('WIFI TX bench packets='),5)
                trial['target']={k:int(v,16) for k,v in re.findall(r'(\w+)=([0-9a-f]{8})',counters)}
                trial['target_end']=t.wait(lambda x:x.startswith('WIFI TX bench end status='),5)
                count=trial['target']['packets']
                trial.update(received=len(packets),received_bytes=len(packets)*1332,
                    missing=[i for i in range(count) if i not in packets],
                    sha256_in_receive_order=digest.hexdigest(),
                    receive_span_seconds=None if first is None else last_time-first)
                if any(i>=count for i in packets):raise RuntimeError('Received beyond target count')
                if trial['target_end']!='WIFI TX bench end status=complete' or trial['target']['failed'] or trial['invalid']:
                    raise RuntimeError('Direct sender failed or invalid payload received')
            finally:
                payload_path.write_bytes(b''.join(packets.values()))
                if started:
                    t.write(b'>');t.write(b'i');t.expect('UART application')
                t.ser.close()
    wifi_connect.data_test=diagnostic;saved=sys.argv
    sys.argv=[saved[0],'--interface',a.interface,'--restore-profile',a.restore_profile,'--seconds','30','--data','--mtu']
    try:return wifi_connect.main()
    finally:
        sys.argv=saved;wifi_connect.data_test=original
        a.output.write_text(json.dumps(results[-1] if results else {'error':'No result'},indent=2),encoding='utf-8')
if __name__=='__main__':raise SystemExit(main())
