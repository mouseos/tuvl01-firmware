import pathlib,subprocess,tempfile,unittest,json,sys,select
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import wpa_uart
class PipeSerial:
    def __init__(self,exe):
        self.proc=subprocess.Popen([str(exe),'--serve'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    def write(self,p):return self.proc.stdin.write(p)
    def flush(self):self.proc.stdin.flush()
    def readline(self):
        if select.select([self.proc.stdout],[],[],.05)[0]:return self.proc.stdout.readline()
        return b''
    def close(self):
        self.proc.stdin.close();code=self.proc.wait(timeout=5)
        error=self.proc.stderr.read();self.proc.stdout.close();self.proc.stderr.close()
        if code:raise RuntimeError('Native firmware fixture failed: '+error.decode(errors='replace'))
class WPAConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vendor=ROOT/'third_party/wpa_supplicant'
        manifest=json.loads((vendor/'manifest.json').read_text())
        sources=[str(vendor/'src'/n) for n in manifest['sources']]
        sources += [str(p) for p in (ROOT/'rtos/wpa/port').glob('*.c')]
        flags=['-O2','-g','-fno-builtin','-fno-strict-aliasing','-ffunction-sections',
            '-fdata-sections','-Wall','-Wextra','-Wno-unused-parameter',
            '-Wno-unused-but-set-variable','-Werror=implicit-function-declaration',
            '-fsanitize=address,undefined','-DOS_NO_C_LIB_DEFINES',
            '-DCONFIG_NO_STDOUT_DEBUG','-DCONFIG_NO_EAPOL','-DCONFIG_NO_TKIP',
            '-DCONFIG_NO_RC4','-DCONFIG_CRYPTO_INTERNAL']
        for path in (vendor/'src',vendor/'src/utils',ROOT/'rtos/wpa/port',
                     ROOT/'third_party/nanoprintf'):
            flags+=['-I'+str(path)]
        # Host system headers/byte order must precede freestanding shims.
        flags+=['-idirafter',str(ROOT/'include')]
        cls.tmp=tempfile.TemporaryDirectory();cls.exe=pathlib.Path(cls.tmp.name)/'console-test'
        subprocess.run(['cc',*flags,*sources,
            str(ROOT/'tests/wpa_console_fixture.c'),'-Wl,--gc-sections','-o',str(cls.exe)],check=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_real_rsn_console_lifecycle_under_sanitizers(self):
        r=subprocess.run([str(self.exe)],capture_output=True,text=True,check=True)
        self.assertIn('PASS firmware WPA console',r.stdout)
    def test_real_console_key_cleanup_success_failure_and_reaped_owner(self):
        for mode in range(5):
            with self.subTest(mode=mode):
                r=subprocess.run([str(self.exe),'--cleanup',str(mode)],capture_output=True,text=True,check=True)
                self.assertIn('PASS cleanup',r.stdout)
    def test_pc_cleanup_failure_is_never_reported_as_closed(self):
        class Fail:
            def readline(self):return b'WPA key cleanup unresolved\n'
        with self.assertRaises(RuntimeError):wpa_uart.wait(Fail(),{b'WPA volatile session closed'})
    def test_pc_sender_to_actual_console_and_close(self):
        ser=PipeSerial(self.exe)
        try:
            result=wpa_uart.provision(ser,b'test',bytes.fromhex('020000000002'),6,b'password')
            self.assertIn('association is not implemented',result)
            wpa_uart.close_session(ser)
        finally:ser.close()
    def test_pc_rejected_target_resynchronizes(self):
        ser=PipeSerial(self.exe)
        try:
            with self.assertRaises(RuntimeError):
                wpa_uart.provision(ser,b'test',bytes.fromhex('020000000002'),11,b'password')
            wpa_uart.identify(ser)
        finally:ser.close()
    def test_pc_failed_join_trial_closes_session_and_preserves_console(self):
        ser=PipeSerial(self.exe)
        try:
            wpa_uart.provision(ser,b'test',bytes.fromhex('020000000002'),6,b'password')
            with self.assertRaises(RuntimeError):wpa_uart.join_trial(ser)
            wpa_uart.identify(ser)
        finally:ser.close()
    def test_pc_crc_valid_ssid_mismatch_resynchronizes(self):
        ser=PipeSerial(self.exe)
        try:
            with self.assertRaises(RuntimeError):
                wpa_uart.provision(ser,b'wrong',bytes.fromhex('020000000002'),6,b'password')
            wpa_uart.identify(ser)
        finally:ser.close()
    def test_unknown_firmware_receives_no_credentials(self):
        class Old:
            def __init__(self):self.writes=[]
            def write(self,p):self.writes.append(bytes(p));return len(p)
            def flush(self):pass
            def readline(self):return b'UART application\n'
        ser=Old()
        with patch('wpa_uart.time.monotonic',side_effect=range(20)):
            with self.assertRaises(TimeoutError):
                wpa_uart.provision(ser,b'test',bytes.fromhex('020000000002'),6,b'password')
        self.assertEqual(ser.writes,[b'i'])
    def test_unknown_uart_output_is_not_exposed(self):
        class Echo:
            def readline(self):return b'PRIVATE TEST VALUE\n'
        with self.assertRaises(RuntimeError) as caught:wpa_uart.wait(Echo(),{b'UART application'})
        self.assertNotIn('PRIVATE TEST VALUE',str(caught.exception))
    def test_binary_interception_precedes_legacy_dispatch(self):
        source=(ROOT/'src/app.c').read_text()
        self.assertLess(source.index('wifi_wpa_uart_intercept(c,'),source.index("if(c>=0 && c!='i'"))
        self.assertIn('if(c==2)wifi_wpa_uart_begin(',source)
        self.assertIn('if(c==3)wifi_wpa_uart_close();',source)
    def test_vendor_sources_and_nano_match_pinned_manifests(self):
        import hashlib
        for name in ('wpa_supplicant','nanoprintf'):
            base=ROOT/'third_party'/name;m=json.loads((base/'manifest.json').read_text())
            for path,entry in m['files'].items():
                self.assertEqual(hashlib.sha256((base/path).read_bytes()).hexdigest(),entry['sha256'])
