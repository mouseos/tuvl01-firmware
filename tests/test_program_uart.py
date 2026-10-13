"""UART lifecycle tests without serial hardware or image writes."""
import importlib.util
import pathlib
import unittest
from unittest import mock
import contextlib,io,tempfile,sys

spec=importlib.util.spec_from_file_location('program_uart',pathlib.Path(__file__).resolve().parents[1]/'tools/uart.py')
uart=importlib.util.module_from_spec(spec)
spec.loader.exec_module(uart)

class SerialStub:
    def reset_input_buffer(self):pass
    def close(self):pass

class ScriptedTransport(uart.Transport):
    def __init__(self,responses):
        self.responses=list(responses);self.sent=[];self.ser=SerialStub();self.pending=b'stale'
    def write(self,data):self.sent.append(data)
    def wait(self,predicate,timeout=5):
        response=self.responses.pop(0)
        if not predicate(response):raise AssertionError('Unexpected response: '+response)
        return response

class RecoveryTests(unittest.TestCase):
    status='UART recovery status=00000000 written=00000000 ready=00000000 busy=00000000'
    def test_byte_used_for_autoboot_cancellation_is_not_status_request(self):
        t=ScriptedTransport(['UART application','TUVL01 independent recovery boot','AUTOBOOT cancelled',self.status])
        self.assertEqual(t.recovery(),self.status)
        self.assertEqual(t.sent,[b'i',b'q',b'i',b'i'])
        self.assertEqual(t.responses,[])
    def test_existing_recovery_is_reused(self):
        t=ScriptedTransport([self.status]);t.recovery()
        self.assertEqual(t.sent,[b'i'])
    def test_loader_without_autoboot_keeps_original_handshake(self):
        t=ScriptedTransport(['UART application','TUVL01 independent recovery boot',self.status]);t.recovery()
        self.assertEqual(t.sent,[b'i',b'q',b'i'])
    def test_busy_recovery_does_not_start_an_upload(self):
        t=ScriptedTransport([self.status[:-8]+'00000001'])
        with self.assertRaises(RuntimeError):t.recovery()
        self.assertEqual(t.sent,[b'i'])
    def test_diagnostic_commands_send_only_their_own_opcode(self):
        for command,opcode,prefix in [('tuner-program-port',b'\x01','PROGRAM probe'),('tuner-program-burst',b'*','PROGRAM burst')]:
            with self.subTest(command=command),tempfile.TemporaryDirectory() as directory:
                t=ScriptedTransport(['UART application',prefix+' end status=read-restored-unclassified','UART application'])
                argv=['uart.py',command,'--port','COM_FAKE','--log',str(pathlib.Path(directory)/'uart.bin')]
                with mock.patch.object(uart,'Transport',return_value=t),mock.patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                    uart.main()
                self.assertEqual(t.sent,[b'i',opcode,b'i'])
                self.assertEqual(t.responses,[])

    def test_pin_capture_waits_for_restoration_and_application_response(self):
        with tempfile.TemporaryDirectory() as directory:
            t=ScriptedTransport(['UART application','PIN capture end status=captured-restored-unclassified','UART application'])
            argv=['uart.py','tuner-pin-capture','--port','COM_FAKE','--log',str(pathlib.Path(directory)/'uart.bin')]
            with mock.patch.object(uart,'Transport',return_value=t),mock.patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                uart.main()
            self.assertEqual(t.sent,[b'i',b'`',b'i'])
            self.assertEqual(t.responses,[])

    def test_pin_test_has_dedicated_opcode_and_failure_is_reported(self):
        for outcome in ('captured-restored-unclassified','restore-failed-inputs-retained'):
            with tempfile.TemporaryDirectory() as directory:
                t=ScriptedTransport(['UART application','PINTST capture end status='+outcome]+(['UART application'] if outcome.startswith('captured') else []))
                argv=['uart.py','tuner-pin-test','--port','COM_FAKE','--log',str(pathlib.Path(directory)/'uart.bin')]
                with mock.patch.object(uart,'Transport',return_value=t),mock.patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                    if outcome.startswith('captured'):uart.main()
                    else:
                        with self.assertRaises(RuntimeError):uart.main()
                self.assertEqual(t.sent,[b'i',b'-']+([b'i'] if outcome.startswith('captured') else []))

    def test_probe_opcodes_do_not_dispatch_other_commands(self):
        import re
        source=(pathlib.Path(__file__).resolve().parents[1]/'src/app.c').read_text()
        for opcode,call in [("'*'",'tuner_program_burst_probe'),("'`'",'tuner_pin_capture_probe'),("'-'",'tuner_pin_test_probe')]:
            dispatch=re.findall(r'if\(c=='+re.escape(opcode)+r'\)(\w+)\(',source)
            self.assertEqual(dispatch,[call])

if __name__=='__main__':unittest.main()
