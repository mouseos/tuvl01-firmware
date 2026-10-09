import contextlib,io,json,pathlib,socket,struct,sys,tempfile,unittest
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from ts_receive import decode,StreamCapture,receive,input_summary
class InputSummary(unittest.TestCase):
    def test_all_counts_and_legacy_line(self):
        text='TS input source=00000000 packets=00000020 sync=00000001 tei=00000002 adaptation=00000003 comparisons=00000004 cc_jumps=00000005 cc_repeats=00000006'
        self.assertEqual(input_summary(text),dict(source=0,packets=32,sync=1,tei=2,adaptation=3,comparisons=4,cc_jumps=5,cc_repeats=6))
        self.assertIsNone(input_summary('TS stream end status=stopped'))
        with self.assertRaises(ValueError):input_summary(text+' extra')
class Datagram(unittest.TestCase):
    def test_sequence_index_and_resync_preserved(self):
        body=(b'\x47'+bytes(187))*7
        self.assertEqual(decode(b'TTS1'+struct.pack('!III',9,63,1)+body),(9,63,1,body))
    def test_invalid_length_magic_and_flags_rejected(self):
        p=b'TTS1'+struct.pack('!III',0,0,0)+bytes(188)
        for v in (p[:-1],b'BAD!'+p[4:],p+bytes(188*7),p[:12]+struct.pack('!I',2)+p[16:]):
            with self.subTest(length=len(v)):
                with self.assertRaises(ValueError):decode(v)

class Capture(unittest.TestCase):
    def test_forwarding_preserves_ts_and_excludes_foreign_invalid_duplicate(self):
        forwarded=[];c=StreamCapture(forwarded.append)
        body=b'\x47\x01\x00\x90'+bytes(range(184))
        packet=b'TTS1'+struct.pack('!III',0,0,0)+body
        c.accept(packet,('192.168.74.99',4202))
        c.accept(b'bad',('192.168.74.1',4202))
        c.accept(packet,('192.168.74.1',4202))
        c.accept(packet,('192.168.74.1',4202))
        self.assertEqual(forwarded,[body])
        self.assertEqual(c.data,body)
        self.assertEqual(c.stats['invalid'],1)
        self.assertEqual(c.stats['reordered'],1)
    def send(self,c,seq,index,count=7,flags=0):
        c.accept(b'TTS1'+struct.pack('!III',seq,index,flags)+(b'\x47'+bytes(187))*count,
                 ('192.168.74.1',4202))
    def test_gap_records_exact_packet_loss_and_reordered_is_not_appended(self):
        c=StreamCapture();self.send(c,0,0);self.send(c,2,11)
        self.send(c,1,7,4)
        self.assertEqual(c.stats['missing_datagrams'],1)
        self.assertEqual(c.stats['gaps'][0]['packet_index_delta'],4)
        self.assertEqual(c.stats['reordered'],1)
        self.assertEqual(len(c.data),14*188)
    def test_initial_loss_tail_and_counter_wrap(self):
        c=StreamCapture();self.send(c,1,4)
        self.assertEqual(c.stats['missing_datagrams'],1)
        self.assertEqual(c.stats['gaps'][0]['expected_index'],0)
        c.expected=0xffffffff;c.next_index=0xfffffffc
        self.send(c,0xffffffff,0xfffffffc,4)
        self.send(c,0,0,4,1)
        self.assertEqual(c.stats['missing_datagrams'],1)
        self.assertEqual(c.stats['fifo_resyncs'],1)
        self.assertEqual(c.next_index,4)

class ReceiverSockets(unittest.TestCase):
    def run_capture(self,send_error=None,quality_watch=False,target_input=False):
        udp=MagicMock();relay=MagicMock()
        udp.__enter__.return_value=udp;relay.__enter__.return_value=relay
        body=b'\x47\x01\x00\x90'+bytes(184)
        udp.recvfrom.side_effect=[(b'TTS1'+struct.pack('!III',0,0,0)+body,('192.168.74.1',4202)),socket.timeout()]
        if send_error:relay.sendto.side_effect=send_error
        t=MagicMock()
        lines=iter(['TS stream datagrams=00000001 packets=00000001 overrun=00000000 underrun=00000000 busy=00000000']+
            (['TS input source=00000000 packets=00000020 sync=00000000 tei=00000002 adaptation=00000000 comparisons=00000010 cc_jumps=00000001 cc_repeats=00000000'] if target_input else [])+
            ['TS stream end status=stopped']+(['QUALITY watch count=00000001 partial_reads=00000000','QUALITY watch sample=00000000 raw=00000074','QUALITY watch end status=raw'] if quality_watch else []))
        def wait(predicate,timeout):
            for line in lines:
                if predicate(line):return line
            raise AssertionError('No matching fake UART line')
        t.wait.side_effect=wait
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'received.ts'
            with patch('ts_receive.socket.socket',side_effect=[udp,relay]), \
                 patch('ts_receive.Transport',return_value=t), \
                 patch('ts_receive.time.monotonic',side_effect=[0,0,2,3,4,5]), \
                 contextlib.redirect_stdout(io.StringIO()):
                if send_error:
                    with self.assertRaises(OSError):receive('test',out,pathlib.Path(td)/'uart.bin',1,1234)
                else:receive('test',out,pathlib.Path(td)/'uart.bin',1,1234,quality_watch)
            saved=out.read_bytes();report=json.loads(out.with_suffix('.ts.json').read_text())
        udp.sendto.assert_not_called()
        relay.sendto.assert_called_once_with(body,('127.0.0.1',1234))
        t.ser.close.assert_called_once()
        self.assertEqual(saved,body)
        self.assertEqual(report['unreceived_packets'],0)
        return report
    def test_quality_watch_saved_after_stream_stops(self):
        r=self.run_capture(quality_watch=True)
        self.assertEqual(r['quality_watch_raw'],['QUALITY watch count=00000001 partial_reads=00000000','QUALITY watch sample=00000000 raw=00000074'])
    def test_forwarding_uses_separate_socket(self):
        r=self.run_capture();self.assertEqual(r['forwarded_datagrams'],1)
        self.assertNotIn('target_input',r)
    def test_input_summary_saved_without_assuming_sent_count(self):
        r=self.run_capture(target_input=True)
        self.assertEqual(r['target_input']['packets'],32)
        self.assertEqual(r['target_input']['tei'],2)
        self.assertEqual(r['target_packets'],1)
    def test_forward_failure_stops_target_and_preserves_received_evidence(self):
        r=self.run_capture(OSError('test relay failure'))
        self.assertIn('test relay failure',r['error'])
        self.assertEqual(r['forwarded_datagrams'],0)
