import importlib.util,pathlib,struct,unittest,zlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('uart',ROOT/'tools/uart.py')
uart=importlib.util.module_from_spec(spec);spec.loader.exec_module(uart)

def image(payload):
    h=struct.pack('>7I',0x5455564c,1,0x1c000000,len(payload),zlib.crc32(payload),0x1c000000,0)
    return h+struct.pack('>I',zlib.crc32(h))+payload

class Fake(uart.Transport):
    def __init__(self,state):self.state=state;self.commands=[];self.expected=[]
    def recovery(self):return self.state
    def write(self,data):self.commands.append(data)
    def expect(self,line,timeout=5):self.expected.append(line)

class Resume(unittest.TestCase):
    def state(self,written,**kw):
        v=dict(status=0,ready=0,busy=0);v.update(kw)
        return f'UART recovery status={v["status"]:08x} written={written:08x} ready={v["ready"]:08x} busy={v["busy"]:08x}'
    def test_resume_uses_reported_offset_and_requires_crc_seal(self):
        p=bytes(range(130));t=Fake(self.state(64));t.resume(image(p))
        self.assertEqual(t.commands,[b'w',struct.pack('>IH',64,64),p[64:128],b'w',struct.pack('>IH',128,2),p[128:],b's'])
        self.assertEqual(t.expected[-1],'UART sealed')
        self.assertNotIn(b'r',t.commands)
    def test_complete_unsealed_tail_only_seals(self):
        t=Fake(self.state(130));t.resume(image(bytes(130)))
        self.assertEqual(t.commands,[b's'])
        self.assertEqual(t.expected,['UART sealed'])
    def test_bad_recovery_state_never_sends_data(self):
        for state in (self.state(1),self.state(192),self.state(64,status=1),self.state(64,ready=1),self.state(64,busy=1)):
            t=Fake(state)
            with self.assertRaises(RuntimeError):t.resume(image(bytes(130)))
            self.assertEqual(t.commands,[])

if __name__=='__main__':unittest.main()
