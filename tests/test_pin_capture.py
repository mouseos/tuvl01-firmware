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
if __name__=='__main__':unittest.main()
