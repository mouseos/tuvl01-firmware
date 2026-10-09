import contextlib, io, pathlib, sys, tempfile, unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import uart

class Commands(unittest.TestCase):
    def test_dma_source_selection_and_refusal_close_transport(self):
        for status in ('selected','refused-active','refused-dma-state'):
            t,error=self.invoke('ts-dma-source','TS DMA source end status='+status)
            self.assertEqual([c.args[0] for c in t.write.call_args_list],[b'i',bytes([11]),b'i'])
            self.assertEqual(error is None,status=='selected');t.ser.close.assert_called_once()
    def test_variable_benchmark_frame_duration_and_serial_cleanup(self):
        t,error=self.invoke('ts-benchmark','TS benchmark end status=measured',
                            ['--benchmark-seconds','60'])
        self.assertIsNone(error)
        import struct,zlib
        data=b'TSB1'+struct.pack('>I',60)
        self.assertEqual([c.args[0] for c in t.write.call_args_list],
                         [b'i',b'\x05',data+struct.pack('>I',zlib.crc32(data)),b'i'])
        self.assertEqual(t.wait.call_args.args[1],70)
        t.expect.assert_any_call('TS benchmark configuration bytes=12 version=1')
        t.ser.close.assert_called_once()
    def test_legacy_benchmark_keeps_ten_second_command(self):
        t,error=self.invoke('ts-benchmark','TS benchmark end status=measured')
        self.assertIsNone(error)
        self.assertEqual([c.args[0] for c in t.write.call_args_list],[b'i',b'H',b'i'])
        self.assertEqual(t.wait.call_args.args[1],20)
    def test_benchmark_input_rejection_precedes_serial_access(self):
        for command,seconds in [('ts-benchmark','0'),('ts-benchmark','301'),('diag','60')]:
            with patch.object(sys,'argv',['uart.py',command,'--port','TEST','--log','unused.log',
                '--benchmark-seconds',seconds]),patch.object(uart,'Transport') as transport,\
                contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):uart.main()
                transport.assert_not_called()
    def test_variable_benchmark_failure_does_not_report_success(self):
        t,error=self.invoke('ts-benchmark','TS benchmark end status=rejected',
                            ['--benchmark-seconds','300'])
        self.assertIsInstance(error,RuntimeError)
        self.assertEqual(t.wait.call_args.args[1],310)
        t.ser.close.assert_called_once()
    def test_wifi_restart_requires_ready_and_closes_transport(self):
        for status in ('ready','failed','refused-active','refused-state'):
            t,error=self.invoke('wifi-restart','WIFI restart end status='+status)
            self.assertEqual(t.write.call_args_list[:2], [unittest.mock.call(b'i'),unittest.mock.call(b'|')])
            self.assertEqual(error is None,status=='ready')
            t.ser.close.assert_called_once()
    def invoke(self, command, response, extra=()):
        transport=SimpleNamespace(write=Mock(),expect=Mock(),
            wait=Mock(return_value=response),ser=SimpleNamespace(close=Mock()))
        with tempfile.TemporaryDirectory() as directory:
            args=['uart.py',command,'--port','TEST','--log',str(pathlib.Path(directory)/'uart.bin')]
            args.extend(extra)
            if isinstance(response,list):transport.wait.side_effect=response
            with patch.object(sys,'argv',args),patch.object(uart,'Transport',return_value=transport),contextlib.redirect_stdout(io.StringIO()):
                try:
                    uart.main()
                    error=None
                except Exception as caught:
                    error=caught
        return transport,error

    def test_ais_probe_sends_explicit_target_only_after_ready_and_closes(self):
        for status in ('ready','failed'):
            t,error=self.invoke('ais-channel',['WIFI AIS channel target bytes=7',
                'WIFI AIS channel probe end status='+status],
                ['--ais-channel','11','--ais-bssid','02:00:00:00:00:01'])
            if status=='ready':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([c.args[0] for c in t.write.call_args_list],
                [b'i',b'}',bytes([11,2,0,0,0,0,1])])
            t.ser.close.assert_called_once()

    def test_ais_probe_refusal_does_not_send_target(self):
        t,error=self.invoke('ais-channel','WIFI AIS channel probe end status=refused-active',
            ['--ais-channel','11','--ais-bssid','02:00:00:00:00:01'])
        self.assertIsInstance(error,RuntimeError)
        self.assertEqual([c.args[0] for c in t.write.call_args_list],[b'i',b'}'])
        t.ser.close.assert_called_once()

    def test_ais_auth_ready_failure_and_refusal_close_serial(self):
        for status in ('ready','failed','refused-active'):
            responses=['WIFI AIS auth probe end status='+status]
            if status!='refused-active':responses.insert(0,'WIFI AIS auth target bytes=7')
            t,error=self.invoke('ais-auth',responses,
                ['--ais-channel','11','--ais-bssid','02:00:00:00:00:01'])
            if status=='ready':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            sent=[b'i',b'{']
            if status!='refused-active':sent.append(bytes([11,2,0,0,0,0,1]))
            self.assertEqual([c.args[0] for c in t.write.call_args_list],sent)
            t.ser.close.assert_called_once()

    def test_ais_invalid_target_rejected_before_serial_open(self):
        for channel,mac in [('0','02:00:00:00:00:01'),('14','02:00:00:00:00:01'),
            ('1','00:00:00:00:00:00'),('1','03:00:00:00:00:01'),('1','garbage')]:
            with patch.object(sys,'argv',['uart.py','ais-channel','--port','TEST',
                '--log','unused.log','--ais-channel',channel,'--ais-bssid',mac]),\
                patch.object(uart,'Transport') as transport,\
                contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:uart.main()
                self.assertEqual(caught.exception.code,2)
                transport.assert_not_called()

    def test_write_toggle_has_no_dependency_on_dma_result(self):
        transport,error=self.invoke('wifi-write-poll','WIFI write polling=00000001')
        self.assertIsNone(error)
        self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'Y',b'i'])
        transport.ser.close.assert_called_once()

    def test_long_dma_failure_is_reported_and_port_is_closed(self):
        for status in ('verified','failed'):
            transport,error=self.invoke('ts-dma-long','TS DMA long end status='+status)
            if status=='verified':self.assertIsNone(error)
            else:
                self.assertIsInstance(error,RuntimeError)
                self.assertIn('Longword DMA probe failed',str(error))
            transport.ser.close.assert_called_once()

    def test_pipeline_selection_uses_binary_key_and_reports_refusal(self):
        for status in ('selected','refused-active','refused-dma-state'):
            transport,error=self.invoke('ts-pipeline','TS pipeline end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',bytes([9]),b'i'])
            transport.ser.close.assert_called_once()
    def test_width_failure_is_not_reported_as_verified(self):
        for status in ('verified-reads','failed'):
            transport,error=self.invoke('wifi-width','WIFI width end status='+status)
            if status=='verified-reads':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'W',b'i'])
            transport.ser.close.assert_called_once()

    def test_link_query_failure_is_reported_and_port_is_closed(self):
        for status in ('read','failed'):
            transport,error=self.invoke('wifi-link','WIFI link quality end status='+status)
            if status=='read':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'K',b'i'])
            transport.ser.close.assert_called_once()

    def test_rate_refusal_requires_ap_stop_and_closes_port(self):
        for status in ('selected','refused-active'):
            transport,error=self.invoke('wifi-rate','WIFI rate end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:
                self.assertIsInstance(error,RuntimeError)
                self.assertIn('Stop AP',str(error))
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'R',b'i'])
            transport.ser.close.assert_called_once()

    def test_poll_reuse_refusal_is_not_success_and_closes_port(self):
        for status in ('selected','refused-active'):
            transport,error=self.invoke('wifi-poll-reuse','WIFI poll reuse end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'Z',b'i'])
            transport.ser.close.assert_called_once()

    def test_status_poll_selection_or_refusal_drains_response_and_closes_port(self):
        for status in ('selected','refused-active','refused-state'):
            transport,error=self.invoke('wifi-status-poll','WIFI status poll end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'A',b'i'])
            transport.ser.close.assert_called_once()

    def test_poll_budget_refusal_is_not_success_and_closes_port(self):
        for status in ('selected','refused-active'):
            transport,error=self.invoke('wifi-poll-budget','WIFI poll budget end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'G',b'i'])
            transport.ser.close.assert_called_once()

    def test_irq_selection_refusal_drains_and_closes_port(self):
        for status in ('selected','refused-active','refused-state'):
            transport,error=self.invoke('wifi-irq','WIFI IRQ end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'X',b'i'])
            transport.ser.close.assert_called_once()

    def test_queue_selection_refusal_drains_and_closes_port(self):
        for status in ('selected','refused-active'):
            transport,error=self.invoke('wifi-queues','WIFI queues end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'8',b'i'])
            transport.ser.close.assert_called_once()
    def test_test_source_refusal_drains_and_closes_port(self):
        for status in ('selected','refused-active'):
            transport,error=self.invoke('ts-test-source','TS test source end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'7',b'i'])
            transport.ser.close.assert_called_once()
    def test_station_stats_raw_success_or_failure_drains_and_closes_port(self):
        for status in ('read-raw','unsupported','refused-peer','timeout-compile','rejected'):
            transport,error=self.invoke('wifi-station-stats','WIFI station stats end status='+status)
            if status=='read-raw':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'6',b'i'])
            transport.ser.close.assert_called_once()

    def test_window_selection_refusal_drains_and_closes_port(self):
        for status in ('selected','refused-active','refused-state'):
            transport,error=self.invoke('wifi-tx-window','WIFI TX window end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',b'9',b'i'])
            transport.ser.close.assert_called_once()
    def test_latency_selectors_refuse_and_release_port(self):
        for command,prefix,key in (('ts-frame-size','TS frame size',b'5'),('wifi-tx-timing','WIFI TX timing',b'4')):
            for status in ('selected','refused-active','refused-state'):
                transport,error=self.invoke(command,prefix+' end status='+status)
                if status=='selected':self.assertIsNone(error)
                else:self.assertIsInstance(error,RuntimeError)
                self.assertEqual([call.args[0] for call in transport.write.call_args_list],[b'i',key,b'i'])
                transport.ser.close.assert_called_once()
    def test_rate_profile_refusal_releases_port(self):
        for status in ('selected','refused-active'):
            t,error=self.invoke('wifi-rate-profile','WIFI rate profile end status='+status)
            if status=='selected':self.assertIsNone(error)
            else:self.assertIsInstance(error,RuntimeError)
            self.assertEqual([c.args[0] for c in t.write.call_args_list],[b'i',b'3',b'i'])
            t.ser.close.assert_called_once()

if __name__=='__main__':unittest.main()
