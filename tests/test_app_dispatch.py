"""Compile the real UART command routes to detect overlapping operations."""
import ctypes
import ast
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AppDispatch(unittest.TestCase):
    def test_tuner_switch_does_not_stop_active_transfers(self):
        self.assertEqual(self.route(22),{'tuner_profile_switch':1})
        self.c.clear();self.c.pre_dispatch(22)
        self.assertFalse(any(self.c.count(n) for n in range(len(self.names))))
    def test_idle_sample_does_not_stop_active_transfers(self):
        self.assertEqual(self.route(21),{'sdio_wifi_idle_sample':1})
        self.c.clear();self.c.pre_dispatch(21)
        self.assertFalse(any(self.c.count(n) for n in range(len(self.names))))
    def test_clock_profile_does_not_stop_active_transfers(self):
        self.assertEqual(self.route(20),{'sdio_wifi_clock_profile':1})
        self.c.clear();self.c.pre_dispatch(20)
        self.assertFalse(any(self.c.count(n) for n in range(len(self.names))))
    def test_ts_state_command_does_not_interrupt_stream_or_benchmark(self):
        self.assertEqual(self.route(18),{'tuner_ts_state':1})
        self.c.clear();self.c.pre_dispatch(18)
        self.assertFalse(any(self.c.count(n) for n in range(len(self.names))))
    @classmethod
    def setUpClass(cls):
        app = (ROOT / 'src/app.c').read_text()
        start = app.index("        if(c=='u')usb_debug();")
        routes = app[start:app.index('        sdio_wifi_service_mark(1);', start)]
        stop_start = app.index("        if(c>=0 && c!='i'")
        prelude = app[stop_start:start]
        calls = re.findall(r'\b((?:(?:usb_|sdio_|tuner_|wifi_wpa_|loader_|board_led_)\w+|instruction_cache_toggle))\(([^)]*)\)', routes)
        calls += re.findall(r'\b((?:sdio_|tuner_)\w+)\(([^)]*)\)', prelude)
        names = sorted(set(name for name, _ in calls))
        stubs = []
        for index, name in enumerate(names):
            args = {args for called, args in calls if called == name}
            signature = ('void (*value)(void)' if args == {'tuner_quality'} else
                         'unsigned value' if args != {''} else 'void')
            ignore = '(void)value;' if args != {''} else ''
            stubs.append(f'static void {name}({signature})'
                         f'{{{ignore}seen[{index}]++;}}')
        source = ('static void tuner_quality(void);\nstatic unsigned seen[' + str(len(names)) + '];\n' +
                  '\n'.join(stubs) + '\nstatic unsigned xTaskGetTickCount(void){return 0;}\nvoid dispatch(int c){' + routes + '}\n' +
                  'void pre_dispatch(int c){' + prelude + '}\n' +
                  'void clear(void){for(unsigned i=0;i<sizeof seen/sizeof seen[0];i++)seen[i]=0;}\n'
                  'unsigned count(unsigned i){return seen[i];}\n')
        cls.names = names
        cls.tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(cls.tmp.name)
        (path / 'dispatch.c').write_text(source)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(path / 'dispatch.c'), '-o', str(path / 'dispatch.so')], check=True)
        cls.c = ctypes.CDLL(str(path / 'dispatch.so'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def route(self, byte):
        self.c.clear()
        self.c.dispatch(byte)
        return {name: self.c.count(i) for i, name in enumerate(self.names)
                if self.c.count(i)}

    def test_each_byte_selects_at_most_one_operation(self):
        for byte in range(256):
            with self.subTest(byte=byte):
                self.assertLessEqual(sum(self.route(byte).values()), 1)

    def test_ais_diagnostics_cannot_start_or_stop_a_benchmark(self):
        self.assertEqual(self.route(ord('{')), {'sdio_wifi_ais_auth_probe': 1})
        self.assertEqual(self.route(ord('}')), {'sdio_wifi_ais_channel_probe': 1})

    def test_benchmark_has_independent_commands(self):
        self.assertEqual(self.route(ord('<')), {'sdio_wifi_tx_bench_start': 1})
        self.assertEqual(self.route(ord('>')), {'sdio_wifi_tx_bench_stop': 1})

    def test_pc_download_tool_uses_benchmark_routes(self):
        tree = ast.parse((ROOT / 'tools/wifi_tx_test.py').read_text())
        operations = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    isinstance(node.func.value, ast.Name) and
                    node.func.value.id == 't' and node.func.attr == 'write' and
                    len(node.args) == 1 and isinstance(node.args[0], ast.Constant)):
                data = node.args[0].value
                if isinstance(data, bytes) and data != b'i':
                    self.assertEqual(len(data), 1)
                    operations.append(self.route(data[0]))
        self.assertCountEqual(operations, [
            {'sdio_wifi_tx_bench_start': 1}, {'sdio_wifi_tx_bench_stop': 1}])

    def test_restart_guard_receives_active_stream_and_benchmark_state(self):
        self.c.clear()
        self.c.pre_dispatch(ord('|'))
        self.assertEqual(sum(self.c.count(i) for i in range(len(self.names))), 0)
        self.c.pre_dispatch(ord('c'))
        self.assertEqual(self.c.count(self.names.index('sdio_wifi_tx_bench_stop')), 1)
        self.assertEqual(self.c.count(self.names.index('tuner_ts_stream_interrupt')), 1)


if __name__ == '__main__':
    unittest.main()
