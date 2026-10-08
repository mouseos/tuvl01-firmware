import io,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from uart import Transport
class Serial:
    def __init__(self,chunks):self.chunks=iter(chunks)
    def readline(self):return next(self.chunks,b'')
class Lines(unittest.TestCase):
    def transport(self,chunks):
        t=Transport.__new__(Transport);t.ser=Serial(chunks);t.log=io.BytesIO();t.pending=b'';return t
    def test_read_timeout_fragment_does_not_end_line(self):
        line=b'TS DATA '+b'47'*188+b'\r\n'
        t=self.transport([line[:108],line[108:220],line[220:]])
        self.assertEqual(t.wait(lambda s:s.startswith('TS DATA ')),line.decode().strip())
        self.assertEqual(t.log.getvalue(),line)
    def test_pending_fragment_survives_observation_timeout(self):
        t=self.transport([b'UART app'])
        with self.assertRaises(TimeoutError):t.wait(lambda s:s=='UART application',.001)
        t.ser=Serial([b'lication\r\n'])
        self.assertEqual(t.wait(lambda s:s=='UART application'),'UART application')
    def test_line_limit(self):
        t=self.transport([b'x'*4097])
        with self.assertRaises(ValueError):t.wait(lambda s:True)
