import pathlib,sys,unittest,subprocess
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import wifi_connect

class Restoration(unittest.TestCase):
    def test_ipv4_query_failure_can_recover_before_lease_deadline(self):
        failed=subprocess.CompletedProcess([],1,stdout=b'')
        ready=subprocess.CompletedProcess([],0,stdout=b'"192.168.74.2"')
        result={}
        with patch.object(wifi_connect.subprocess,'run',side_effect=[failed,ready,RuntimeError('ping reached')]) as run, \
             patch.object(wifi_connect.time,'monotonic',return_value=0), \
             patch.object(wifi_connect.time,'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError,'ping reached'):
                wifi_connect.data_test('test',result,0,1,False,1316)
            self.assertEqual(result['data']['lease'],'192.168.74.2')
            self.assertEqual(run.call_count,3)
            sleep.assert_called_once_with(.5)
    def test_ipv4_query_failure_is_bounded_without_success(self):
        failed=subprocess.CompletedProcess([],1,stdout=b'')
        result={}
        with patch.object(wifi_connect.subprocess,'run',return_value=failed) as run, \
             patch.object(wifi_connect.time,'monotonic',side_effect=[0,19]), \
             patch.object(wifi_connect.time,'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError,'before lease deadline'):
                wifi_connect.data_test('test',result,0,1,False,1316)
            self.assertNotIn('data',result)
            self.assertEqual(run.call_count,1)
            sleep.assert_not_called()
    def test_transient_missing_network_retried_and_verified(self):
        with patch.object(wifi_connect,'netsh',side_effect=[RuntimeError('unavailable'),'networks','connected']) as n, \
             patch.object(wifi_connect,'wait_connected',return_value=(True,{'Profile':'original'})) as w, \
             patch.object(wifi_connect.time,'sleep'):
            ok,state,errors=wifi_connect.restore_connection('test','original','ssid')
            self.assertTrue(ok);self.assertEqual(state['Profile'],'original')
            self.assertEqual(errors,['unavailable']);self.assertEqual(n.call_count,3)
            w.assert_called_once_with('test','original',25,'ssid')
    def test_unavailable_network_is_bounded_and_not_success(self):
        def call(*args):
            if args[0]=='connect':raise RuntimeError('unavailable')
            return 'networks'
        with patch.object(wifi_connect,'netsh',side_effect=call) as n, \
             patch.object(wifi_connect,'wait_connected') as w, \
             patch.object(wifi_connect.time,'sleep'):
            ok,state,errors=wifi_connect.restore_connection('test','original','ssid')
            self.assertFalse(ok);self.assertEqual(len(errors),3)
            self.assertEqual(n.call_count,6);w.assert_not_called()
