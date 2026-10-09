"""UART replies survive asynchronous notifications while UDP is received."""
import io,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from uart import Transport
from wifi_tx_test import BenchUART

class Serial:
    def __init__(self):self.data=bytearray()
    @property
    def in_waiting(self):return len(self.data)
    def read(self,size):
        data=bytes(self.data[:size]);del self.data[:size];return data
    def readline(self):
        end=self.data.find(b'\n')
        return self.read(end+1 if end>=0 else len(self.data))

class Capture(unittest.TestCase):
    def capture(self):
        t=Transport.__new__(Transport);t.ser=Serial();t.log=io.BytesIO();t.pending=b''
        return t,BenchUART(t)
    def test_notifications_larger_than_uart_buffer_do_not_discard_summary(self):
        t,c=self.capture();wire=b''
        for _ in range(200):
            chunk=b'WIFI event id=0000001a\r\n'*10
            t.ser.data.extend(chunk);wire+=chunk;c.pump()
        replies=[b'WIFI TX bench packets=00000001',b'WIFI TX bench timing counts=00000002',
                 b'WIFI TX bench end status=complete']
        chunk=b'\r\n'.join(replies)+b'\r\n';t.ser.data.extend(chunk);wire+=chunk;c.pump()
        for reply in replies:self.assertEqual(c.wait(lambda s:s==reply.decode()),reply.decode())
        self.assertEqual(t.log.getvalue(),wire);self.assertEqual(t.pending,b'')
    def test_partial_summary_survives_pump_and_wait_fallback(self):
        t,c=self.capture();t.pending=b'WIFI TX bench pac'
        t.ser.data.extend(b'kets=000000');c.pump()
        t.ser.data.extend(b'01\r\n');self.assertEqual(c.wait(lambda s:s.startswith('WIFI TX bench packets=')),
            'WIFI TX bench packets=00000001')
        t.ser.data.extend(b'UART application\r\n');self.assertEqual(t.expect('UART application'),'UART application')
    def test_errors_are_not_hidden_in_background_capture(self):
        for data,error in ((b'UART rejected busy\n',RuntimeError),(b'UART timeout\n',RuntimeError),
                           (b'x'*4097,ValueError),(b'x'*4096+b'\n',ValueError)):
            t,c=self.capture();t.ser.data.extend(data)
            with self.assertRaises(error):c.pump()
            self.assertEqual(t.log.getvalue(),data)
    def test_reply_queue_is_bounded(self):
        t,c=self.capture();t.ser.data.extend(b'WIFI TX bench packets=00000000\n'*33)
        with self.assertRaises(ValueError):c.pump()

if __name__=='__main__':unittest.main()
