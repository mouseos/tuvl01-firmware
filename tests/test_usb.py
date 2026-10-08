import pathlib, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class UsbDisconnect(unittest.TestCase):
    def test_vbus_loss_and_reconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / 'usb_disconnect'
            subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra',
                            '-Werror', '-I' + str(ROOT / 'include'),
                            str(ROOT / 'tests/usb_disconnect.c'), '-o', str(exe)],
                           check=True)
            subprocess.run([str(exe)], check=True)
