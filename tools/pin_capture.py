"""Summarize finite PD4..7 captures saved by tools/uart.py; values are not IQ."""
import argparse,json,pathlib,re,statistics

def summarize(text,pin_test=False):
    prefix='PINTST' if pin_test else 'PIN'
    selector='case' if pin_test else 'mode'
    start=text.rfind(prefix+' capture start PD4..7 input-only')
    if start<0:raise ValueError('No pin capture in log')
    capture=text[start:]
    if prefix+' capture end status=captured-restored-unclassified' not in capture:
        raise ValueError('No complete capture with confirmed restoration')
    samples={1:[],2:[]} if pin_test else {2:[],0:[]}
    pattern='^'+prefix+' sample '+selector+r'=([0-9a-f]{8}) index=([0-9a-f]{8}) counts=([0-9a-f]{8}) value=([0-9a-f]{8})$'
    for line in capture.splitlines():
        if not line.startswith(prefix+' sample '):continue
        match=re.fullmatch(pattern,line)
        if not match:raise ValueError('Malformed sample line')
        mode,index,count,value=(int(v,16) for v in match.groups())
        if mode not in samples or value>15 or index!=len(samples[mode]):raise ValueError('Invalid sample order/value')
        samples[mode].append((count,value))
    result={'classification':'unclassified GPIO levels, not verified IQ',
            'timing':'timestamp before GPIO read; nonuniform software sampling; nominal CMT 4.5 MHz',
            'modes':[]}
    if pin_test:
        restore_pattern=r'^PINTST restore bank=([0-9a-f]{8}) reg=([0-9a-f]{8}) mask=([0-9a-f]{8}) before=([0-9a-f]{8}) after=([0-9a-f]{8})$'
        restored=[]
        for line in capture.splitlines():
            if not line.startswith('PINTST restore '):continue
            match=re.fullmatch(restore_pattern,line)
            if not match:raise ValueError('Malformed restoration line')
            bank,reg,mask,before,after=(int(v,16) for v in match.groups())
            if (before^after)&mask:raise ValueError('Restoration readback mismatch')
            restored.append((bank,reg,mask))
        if set(restored)!={(0x62,0xe8,15),(0x62,0xf8,15),(0x60,0xac,4),(0x61,0xd7,0x70),
                          (0x61,0xda,0x38),(0x61,0xdb,255),(0x61,0xdc,255),(0x61,0xdd,15),(0x61,0xe7,0x71)} or len(restored)!=9:
            raise ValueError('Incomplete restoration evidence')
    for mode,rows in samples.items():
        if len(rows)!=512:raise ValueError('Expected 512 samples per mode')
        intervals=[(b[0]-a[0])&0xffffffff for a,b in zip(rows,rows[1:])]
        if any(v>=0x80000000 for v in intervals):raise ValueError('Timestamp moved backwards')
        pin_stats=[]
        for bit in range(4):
            levels=[(row[1]>>bit)&1 for row in rows]
            pin_stats.append({'pin':'PD'+str(4+bit),'high_samples':sum(levels),
                              'observed_transitions':sum(a!=b for a,b in zip(levels,levels[1:]))})
        result['modes'].append({('test_case' if pin_test else 'e8_low_nibble'):mode,'samples':len(rows),
                               'span_counts':sum(intervals),
                               'interval_counts_min':min(intervals),'interval_counts_median':statistics.median(intervals),
                               'interval_counts_max':max(intervals),'pins':pin_stats})
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=pathlib.Path)
    p.add_argument('--test',action='store_true',help='Parse tuner-pin-test cases 1/2 and restoration evidence')
    a=p.parse_args();print(json.dumps(summarize(a.log.read_text(encoding='ascii'),a.test),indent=2))

if __name__=='__main__':main()
