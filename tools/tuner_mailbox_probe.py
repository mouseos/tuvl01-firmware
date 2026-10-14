"""Finite experimental PSEQ operand readout, with full normal patch reload.

Requires the corresponding opcode0x81/0x82/0x84/0x88/0x89/0x8a RAM firmware. Runs normal SERVE/default channel14 before
and after the diagnostic. This verifies a candidate bridge, not IQ samples.
"""
import argparse,json,pathlib,re
from uart import Transport
from tuner_pattern_capture import capture
from ts_capture import inspect
REFERENCE_REGS=(0xd4,0x28,0x95)
KNOWN_OPERANDS=(0x0f05,0x0f06,0x0f07,0x0f08,0x0f09,0x0f0a,0x0f0b,
                0x0f0c,0x0f0d,0x0fff,0x1ff0,0x1ff1,0x1ff2,
                0x0f0e,0x0ffe,0x1ff3)

def observations(raw):
    """Keep complete UART rows only; do not repair interleaved/partial rows."""
    items=[];current=None;parities=[]
    for line in raw.decode('ascii','replace').splitlines():
        start=re.fullmatch(r'MAILBOX probe start address=([0-9a-f]{8}) count=([0-9a-f]{8}) operand=([0-9a-f]{8})',line)
        if start:
            current={'operand':int(start[3],16),'samples':[],'transfers':[]}
            items.append(current)
        source_start=re.fullmatch(r'MAILBOX probe start source=((?:register-D5(?:-write20)?|register-(?:D4|28|95)-write20)) address=00000298 count=00000518',line)
        if source_start:
            current={'source':source_start[1],'output_opcode':0x20 if source_start[1].endswith('write20') else 0x21,'samples':[],'transfers':[],'source_rows':[]};items.append(current)
        if current is None:continue
        transfer=re.fullmatch(r'MAILBOX transfer operand=([0-9a-f]{8})',line)
        if transfer:
            parities=[];current['transfers'].append({'operand':int(transfer[1],16),'parity':parities})
        source_transfer=re.fullmatch(r'MAILBOX transfer source=((?:register-D5(?:-write20)?|register-(?:D4|28|95)-write20))',line)
        if source_transfer:
            parities=[];current['transfers'].append({'source':source_transfer[1],'parity':parities})
        source=re.fullmatch(r'MAILBOX source phase=([0-9a-f]{8}) index=([0-9a-f]{8}) d4=([0-9a-f]{8}) d5=([0-9a-f]{8})',line)
        if source:current.setdefault('source_rows',[]).append(dict(zip(['phase','index','d4','d5'],[int(x,16) for x in source.groups()])))
        reference=re.fullmatch(r'MAILBOX reference phase=([0-9a-f]{8}) index=([0-9a-f]{8}) register=([0-9a-f]{8}) value=([0-9a-f]{8})',line)
        if reference:current.setdefault('reference_rows',[]).append(dict(zip(['phase','index','register','value'],[int(x,16) for x in reference.groups()])))
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

def probe(t,output,report=None,known_operands=False,operand=None,snapshot_state=False,register_d5=False,register_d5_write20=False,register_check=None):
    if register_check is not None and (register_check not in REFERENCE_REGS or register_d5 or register_d5_write20 or known_operands or operand is not None):raise ValueError('Choose one reference register')
    if register_d5_write20:register_d5=True
    if register_d5 and (known_operands or operand is not None):raise ValueError('Choose D5 or internal operands')
    if operand is not None and (known_operands or operand not in KNOWN_OPERANDS):
        raise ValueError('Choose one known operand or the sweep')
    if report is None:report={}
    if snapshot_state:from tuner_monitor_state_control import snapshot
    report.update(iq_identified=False,initialization=normal(t))
    prefix='MAILBOX sweep end status=' if known_operands else 'MAILBOX probe end status='
    report['known_operands']=known_operands
    report['operand']=operand
    report['snapshot_state']=snapshot_state
    report['register_d5']=register_d5
    report['register_d5_write20']=register_d5_write20
    report['register_check']=register_check
    try:
        if snapshot_state:report['state_before_probe']=snapshot(t)
        t.write(bytes([0x8a,REFERENCE_REGS.index(register_check)]) if register_check is not None else (b'\x89' if register_d5_write20 else b'\x88') if register_d5 else bytes([0x84,KNOWN_OPERANDS.index(operand)]) if operand is not None
                else b'\x82' if known_operands else b'\x81')
        if register_d5 or register_check is not None:
            source=f'register-{register_check:02X}-write20' if register_check is not None else 'register-D5-write20' if register_d5_write20 else 'register-D5'
            t.expect(f'MAILBOX probe start source={source} address=00000298 count=00000518');report['probe_started']=True
        report['probe']=t.wait(lambda s:s.startswith(prefix),180 if known_operands else 30)
        if snapshot_state:report['state_after_probe']=snapshot(t)
    except Exception as error:
        report['probe_error']=str(error)
        raise
    finally:
        # Even a timed-out or failed probe may have modified chip RAM.
        report['normal_reload']=normal(t)
        try:
            if snapshot_state:report['state_after_reload']=snapshot(t)
            data,summary=capture(t,output)
            report['normal_capture']={**summary,**(inspect(data) if data else {})}
        except Exception as error:
            report['capture_error']=str(error)
            raise
        finally:
            t.write(b'i');t.expect('UART application');report['uart_responding']=True
            if snapshot_state:report['state_after_capture']=snapshot(t)
    if report['probe']!=prefix+'read-restored-unclassified-reinitialize-required':
        raise RuntimeError(report['probe'])
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--known-operands',action='store_true',help='Compare 16 stock operand candidates; restores full record after each')
    mode.add_argument('--operand',type=lambda s:int(s,16),metavar='HEX',help='One known operand, e.g. 0f07, after fresh initialization (opcode0x84)')
    mode.add_argument('--register-d5',action='store_true',help='Experimental live PSEQ 30 D5 -> 21 6D bridge; six-byte slot, opcode0x88')
    mode.add_argument('--register-d5-write20',action='store_true',help='Compare register-write candidate 20 6D, opcode0x89; IQ unconfirmed')
    mode.add_argument('--register-check',type=lambda s:int(s,16),choices=REFERENCE_REGS,help='Known Main1 reference D4/28/95, opcode0x8a plus index')
    p.add_argument('--snapshot-state',action='store_true',help='Record 13 known demod/control registers at four lifecycle boundaries; not simultaneous')
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    if a.operand is not None and a.operand not in KNOWN_OPERANDS:p.error('Unknown operand')
    a.output_dir.mkdir(parents=True,exist_ok=True)
    log_offset=a.log.stat().st_size if a.log.exists() else 0
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        report={'iq_identified':False}
        try:
            t.write(b'i');t.expect('UART application')
            probe(t,a.output_dir/'normal.ts',report,a.known_operands,a.operand,a.snapshot_state,a.register_d5,a.register_d5_write20,a.register_check)
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
