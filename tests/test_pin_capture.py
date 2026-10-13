import importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location('pin_capture',pathlib.Path(__file__).resolve().parents[1]/'tools/pin_capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
def capture():
    lines=['PIN capture start PD4..7 input-only']
    for mode in (2,0):
        for n in range(512):
            lines.append(f'PIN sample mode={mode:08x} index={n:08x} counts={(0xffffff00+n*4)&0xffffffff:08x} value={n%2:08x}')
    lines.append('PIN capture end status=captured-restored-unclassified')
    return '\n'.join(lines)
def pin_test_capture():
    text=capture().replace('PIN ','PINTST ').replace('mode=00000002','case=00000001').replace('mode=00000000','case=00000002')
    restore=[]
    for b,r,m in [(0x62,0xe8,15),(0x62,0xf8,15),(0x60,0xac,4),(0x61,0xd7,0x70),
                  (0x61,0xda,0x38),(0x61,0xdb,255),(0x61,0xdc,255),(0x61,0xdd,15),(0x61,0xe7,0x71)]:
        restore.append(f'PINTST restore bank={b:08x} reg={r:08x} mask={m:08x} before=00000000 after=00000000')
    return text.replace('PINTST capture end','\n'.join(restore)+'\nPINTST capture end')
class CaptureTests(unittest.TestCase):
    def test_wrap_and_pin_transition_counts(self):
        result=probe.summarize(capture())
        for mode in result['modes']:
            self.assertEqual(mode['span_counts'],2044)
            self.assertEqual(mode['interval_counts_max'],4)
            self.assertEqual(mode['pins'][0]['observed_transitions'],511)
            self.assertEqual(mode['pins'][1]['observed_transitions'],0)
    def test_truncated_or_unrestored_capture_is_rejected(self):
        for text in [capture().replace('captured-restored-unclassified','restore-failed-inputs-retained'),
                     capture().replace('index=00000001','index=00000005'),
                     capture().replace('value=00000000','value=00000010')]:
            with self.assertRaises(ValueError):probe.summarize(text)
    def test_only_last_capture_is_parsed(self):
        self.assertEqual(len(probe.summarize(capture()+'\n'+capture())['modes']),2)
    def test_pin_test_capture_requires_all_restoration_fields(self):
        text=pin_test_capture();result=probe.summarize(text,True)
        self.assertEqual([r['test_case'] for r in result['modes']],[1,2])
        for bad in [text.replace('reg=000000e8','reg=000000e9'),text.replace('after=00000000','after=000000ff')]:
            with self.assertRaises(ValueError):probe.summarize(bad,True)
if __name__=='__main__':unittest.main()
