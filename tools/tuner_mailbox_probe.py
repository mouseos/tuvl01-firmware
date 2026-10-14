"""Finite experimental PSEQ operand readout, with full normal patch reload.

Requires opcode0x81/0x82 RAM firmware. Runs normal SERVE/default channel14 before
and after the diagnostic. This verifies a candidate bridge, not IQ samples.
"""
import argparse,json,pathlib,re
from uart import Transport
from tuner_pattern_capture import capture
from ts_capture import inspect

def observations(raw):
    """Keep complete UART rows only; do not repair interleaved/partial rows."""
    items=[];current=None;parities=[]
    for line in raw.decode('ascii','replace').splitlines():
        start=re.fullmatch(r'MAILBOX probe start address=([0-9a-f]{8}) count=([0-9a-f]{8}) operand=([0-9a-f]{8})',line)
        if start:
            current={'operand':int(start[3],16),'samples':[],'transfers':[]}
            items.append(current)
        if current is None:continue
        transfer=re.fullmatch(r'MAILBOX transfer operand=([0-9a-f]{8})',line)
        if transfer:
            parities=[];current['transfers'].append({'operand':int(transfer[1],16),'parity':parities})
        parity=re.fullmatch(r'MAILBOX transfer parity index=([0-9a-f]{8}) f8=([0-9a-f]{8}) expected=([0-9a-f]{8})',line)
        if parity:parities.append(dict(zip(['index','f8','expected'],[int(x,16) for x in parity.groups()])))
        sample=re.fullmatch(r'MAILBOX sample phase=([0-9a-f]{8}) index=([0-9a-f]{8}) sub6d=([0-9a-f]{8}) main6d=([0-9a-f]{8})',line)
        if sample:current['samples'].append(dict(zip(['phase','index','sub6d','main6d'],[int(x,16) for x in sample.groups()])))
        if line.startswith('MAILBOX probe end status='):current['status']=line.split('=',1)[1]
    return {'scope':'Complete UART rows only; sample timing/rate uncalibrated','items':items}

def normal(t):
    t.write(bytes([16]))
    result=t.wait(lambda s:s.startswith('SERVE end status='),90)
    if result!='SERVE end status=ready':raise RuntimeError(result)
    t.write(b'E');t.wait(lambda s:s.startswith('TS stream end status='),15)
    return result

def probe(t,output,report=None,known_operands=False):
    if report is None:report={}
    report.update(iq_identified=False,initialization=normal(t))
    prefix='MAILBOX sweep end status=' if known_operands else 'MAILBOX probe end status='
    report['known_operands']=known_operands
    try:
        t.write(b'\x82' if known_operands else b'\x81')
        report['probe']=t.wait(lambda s:s.startswith(prefix),180 if known_operands else 30)
    finally:
        # Even a timed-out or failed probe may have modified chip RAM.
        report['normal_reload']=normal(t)
        data,summary=capture(t,output)
        report['normal_capture']={**summary,**(inspect(data) if data else {})}
        t.write(b'i');t.expect('UART application');report['uart_responding']=True
    if report['probe']!=prefix+'read-restored-unclassified-reinitialize-required':
        raise RuntimeError(report['probe'])
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    p.add_argument('--known-operands',action='store_true',help='Compare 13 known operand candidates; restores full record after each')
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    log_offset=a.log.stat().st_size if a.log.exists() else 0
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        report={'iq_identified':False}
        try:
            t.write(b'i');t.expect('UART application')
            probe(t,a.output_dir/'normal.ts',report,a.known_operands)
            print(json.dumps(report,indent=2))
        except Exception as error:
            report['error']=str(error)
            raise
        finally:
            t.ser.close()
            log.flush()
            report['observations']=observations(a.log.read_bytes()[log_offset:])
            (a.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
