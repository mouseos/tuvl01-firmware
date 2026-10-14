"""Finite stock D4 selection/D5 scalar comparison over UART; IQ unproven."""
import argparse,json,pathlib,time,re
from uart import Transport
from tuner_mailbox_probe import normal
from tuner_pattern_capture import register,capture
from tuner_monitor_state_control import snapshot
from ts_capture import inspect

# Observed Main1 PSEQ motifs at 05C9..05F5, conditional on AND/OR decoding.
# No arbitrary field values or PSEQ halt/patch writes in this experiment.
SELECTORS=((2,0xd7,0x14),(3,0xdf,0x1c),(4,0xe7,0x24))

def _live_probe(t,output,report):
    report.update(iq_identified=False,initialization=normal(t),rows=[],blocks=[])
    saved=None;touched=False
    try:
        report['state_before_probe']=snapshot(t)
        saved=register(t,0x61,0xd4);report['saved_d4']=saved
        for selector,mask,bits in SELECTORS:
            requested=(saved&mask)|bits
            report['blocks'].append(dict(selector=selector,mask=mask,bits=bits,requested_d4=requested))
            touched=True # Even a transport error may follow an accepted write.
            register(t,0x61,0xd4,requested)
            for index in range(16):
                before=register(t,0x61,0xd4)
                value=register(t,0x61,0xd5)
                after=register(t,0x61,0xd4)
                report['rows'].append(dict(selector=selector,index=index,requested_d4=requested,
                    d4_before=before,d5=value,d4_after=after,host_monotonic_ns=time.monotonic_ns()))
                if before!=requested or after!=requested:
                    raise RuntimeError('D4 selection changed during sample; PSEQ contention possible')
        report['probe']='selected-scalar-unclassified'
    except Exception as error:
        report['probe_error']=str(error);raise
    finally:
        try:
            if touched:
                register(t,0x61,0xd4,saved);report['d4_restored']=True
            report['state_after_probe']=snapshot(t)
        except Exception as error:report['restore_error']=str(error)
        finally:
            report['normal_reload']=normal(t)
            try:
                report['state_after_reload']=snapshot(t)
                data,summary=capture(t,output)
                report['normal_capture']={**summary,**(inspect(data) if data else {})}
            except Exception as error:
                report['capture_error']=str(error);raise
            finally:
                t.write(b'i');t.expect('UART application');report['uart_responding']=True
                report['state_after_capture']=snapshot(t)

def observations(raw):
    fields=('phase','index','first','data','last','before','after')
    sample=rb'^D4WIN sample phase=([0-9a-f]{8}) index=([0-9a-f]{8}) first=([0-9a-f]{8}) data=([0-9a-f]{8}) last=([0-9a-f]{8}) before=([0-9a-f]{8}) after=([0-9a-f]{8})\r?$'
    readback=rb'^D4WIN readback requested=([0-9a-f]{8}) observed=([0-9a-f]{8})\r?$'
    live_fields=('phase','index','selector','requested','first','data','last','before','after','selected')
    live=rb'^D4LIVE sample '+rb' '.join(key.encode()+rb'=([0-9a-f]{8})' for key in live_fields)+rb'\r?$'
    live_readback=readback.replace(b'D4WIN',b'D4LIVE')
    return dict(live_rows=[dict(zip(live_fields,[int(x,16) for x in row])) for row in re.findall(live,raw,re.M)],
        live_readbacks=[dict(zip(('requested','observed'),[int(x,16) for x in row])) for row in re.findall(live_readback,raw,re.M)],scope='Complete UART rows; scalar and timestamp interpretation unproven',
        rows=[dict(zip(fields,[int(x,16) for x in m])) for m in re.findall(sample,raw,re.M)],
        readbacks=[dict(zip(('requested','observed'),[int(x,16) for x in m])) for m in re.findall(readback,raw,re.M)])

def probe(t,output,report,halted=False,buffered_live=False):
    if halted and buffered_live:raise ValueError('Choose halted or buffered live')
    report['halted']=halted
    report['buffered_live']=buffered_live
    if not halted and not buffered_live:return _live_probe(t,output,report)
    report.update(iq_identified=False,initialization=normal(t))
    try:
        report['state_before_probe']=snapshot(t)
        prefix='D4LIVE' if buffered_live else 'D4WIN'
        t.write(b'\x8b' if buffered_live else b'\x87');t.expect(prefix+' probe start');report['probe_started']=True
        report['probe']=t.wait(lambda s:s.startswith(prefix+' probe end status='),30)
        report['state_after_probe']=snapshot(t)
    except Exception as error:
        report['probe_error']=str(error);raise
    finally:
        report['normal_reload']=normal(t)
        try:
            report['state_after_reload']=snapshot(t)
            data,summary=capture(t,output)
            report['normal_capture']={**summary,**(inspect(data) if data else {})}
        except Exception as error:
            report['capture_error']=str(error);raise
        finally:
            t.write(b'i');t.expect('UART application');report['uart_responding']=True
            report['state_after_capture']=snapshot(t)
    if report['probe']!=prefix+' probe end status=read-restored-unclassified-reinitialize-required':
        raise RuntimeError(report['probe'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--log',required=True,type=pathlib.Path)
    p.add_argument('--output-dir',required=True,type=pathlib.Path)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--halted',action='store_true',help='RAM opcode0x87: halt PSEQ, buffer stock D4 selections, restore D4 before resume')
    mode.add_argument('--buffered-live',action='store_true',help='RAM opcode0x8b: six native selectors, 8-row buffers, PSEQ running, strict D4 guards')
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True)
    a.output_dir.mkdir(parents=True,exist_ok=True);report={'iq_identified':False}
    offset=a.log.stat().st_size if a.log.exists() else 0
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        try:
            t.write(b'i');t.expect('UART application');probe(t,a.output_dir/'normal.ts',report,a.halted,a.buffered_live)
        except Exception as error:report['error']=str(error);raise
        finally:
            t.ser.close();log.flush();report['observations']=observations(a.log.read_bytes()[offset:])
            (a.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
