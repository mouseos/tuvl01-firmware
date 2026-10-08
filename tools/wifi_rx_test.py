"""Finite PC-to-TUVL01 RX-only diagnostic; restore the original Wi-Fi profile."""
import argparse,json,pathlib,re,socket,struct,subprocess,sys,time
import wifi_connect
def pattern(sequence,length):
    return b'TWR1'+struct.pack('!II',sequence,length)+bytes((i+sequence%251)%251 for i in range(12,length))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface',required=True);p.add_argument('--restore-profile',required=True)
    p.add_argument('--uart-port',required=True);p.add_argument('--output',type=pathlib.Path,required=True)
    p.add_argument('--mbps',type=float,required=True);p.add_argument('--seconds',type=float,default=10)
    p.add_argument('--payload',type=int,default=1316)
    a=p.parse_args()
    if not .1<=a.mbps<=10 or not 1<=a.seconds<=30 or not 12<=a.payload<=1472:p.error('Outside finite diagnostic bounds')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    original=wifi_connect.data_test;results=[]
    def uart(command):
        log=a.output.with_name(a.output.stem+'-'+command+'.bin')
        subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('uart.py')),command,
            '--port',a.uart_port,'--log',str(log)],check=True)
        return log.read_text(encoding='ascii')
    def diagnostic(interface,result,*args,**kwargs):
        results.append(result)
        original(interface,result,*args,**kwargs)
        client=result['data']['lease'];server=result['data']['server']
        started=False;trial={'requested_mbps':a.mbps,'payload_bytes':a.payload,'requested_seconds':a.seconds}
        result['rx_sink']=trial
        try:
            uart('wifi-rx-start');started=True
            target=int(a.mbps*1e6*a.seconds/(8*a.payload))
            interval=8*a.payload/(a.mbps*1e6);sent=0;maximum_late=0
            templates=[pattern(i,a.payload)[12:] for i in range(251)]
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
                udp.bind((client,0));udp.settimeout(3)
                start=time.monotonic()
                for sequence in range(target):
                    due=start+sequence*interval
                    remaining=due-time.monotonic()
                    if remaining>0:time.sleep(remaining)
                    maximum_late=max(maximum_late,time.monotonic()-due)
                    body=b'TWR1'+struct.pack('!II',sequence,a.payload)+templates[sequence%251]
                    if udp.sendto(body,(server,4203))!=len(body):raise RuntimeError('Incomplete UDP send')
                    sent+=1
                elapsed=time.monotonic()-start
            trial.update(sent_packets=sent,sent_bytes=sent*a.payload,send_elapsed_seconds=elapsed,
                actual_sender_mbps=sent*a.payload*8/elapsed/1e6,maximum_schedule_late_seconds=maximum_late)
            # Bounded drain, then freeze counters before querying larger stats.
            time.sleep(1)
        finally:
            if started:
                text=uart('wifi-rx-stop')
                matches=re.findall(r'^WIFI RX sink active=(.*)$',text,re.M)
                if not matches:raise RuntimeError('Missing RX sink counters')
                counters={k:int(v,16) for k,v in re.findall(r'(\w+)=([0-9a-f]{8})', 'active='+matches[-1])}
                trial['target']=counters
                if 'sent_packets' in trial:
                    trial['not_received']=trial['sent_packets']-counters['packets']
                    trial['tail_missing']=trial['sent_packets']-counters['next_sequence']
                    if trial['not_received']<0 or trial['tail_missing']<0:raise RuntimeError('RX counters exceed finite sender')
                trial['target_receive_span_ticks']=(counters['last_tick']-counters['first_tick'])&0xffffffff
                if counters['overflow']:raise RuntimeError('RX counter overflow')
                trial['wifi_stats_log']=str(a.output.with_name(a.output.stem+'-wifi-stats.bin'))
                stats=uart('wifi-stats')
                if not re.search(r' fault=00000000',stats) or not re.search(r' irq_timeouts=00000000',stats):
                    raise RuntimeError('Radio fault or IRQ timeout')
    wifi_connect.data_test=diagnostic
    saved=sys.argv
    sys.argv=[saved[0],'--interface',a.interface,'--restore-profile',a.restore_profile,'--seconds','30','--data','--mtu']
    try:return wifi_connect.main()
    finally:
        sys.argv=saved;wifi_connect.data_test=original
        a.output.write_text(json.dumps(results[-1] if results else {'error':'No diagnostic result'},indent=2),encoding='utf-8')
if __name__=='__main__':raise SystemExit(main())
