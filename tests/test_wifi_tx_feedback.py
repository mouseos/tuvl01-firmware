import ctypes, pathlib, subprocess, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

class State(ctypes.Structure):
    _fields_ = [('sequence', ctypes.c_uint32 * 128), ('status', ctypes.c_uint32 * 256),
                ('occupied', ctypes.c_uint8 * 128), ('next', ctypes.c_uint8)] + [
                    (name, ctypes.c_uint32) for name in
                    ('requested', 'completed', 'pending', 'skipped', 'unmatched', 'cancelled')]

class Feedback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        library = pathlib.Path(cls.tmp.name) / 'feedback.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'include'), str(ROOT/'src/wifi_tx_feedback.c'),
                        '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.wifi_tx_feedback_reserve.argtypes = [ctypes.POINTER(State), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8)]
        cls.lib.wifi_tx_feedback_complete.argtypes = [ctypes.POINTER(State), ctypes.c_uint8, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint32)]
        cls.lib.wifi_tx_feedback_cancel.argtypes = [ctypes.POINTER(State), ctypes.c_uint8]
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def reserve(self, state, sequence):
        tag = ctypes.c_uint8()
        self.assertEqual(self.lib.wifi_tx_feedback_reserve(ctypes.byref(state), sequence, ctypes.byref(tag)), 1)
        self.assertGreaterEqual(tag.value, 128)
        return tag.value
    def complete(self, state, tag, status):
        sequence = ctypes.c_uint32()
        result = self.lib.wifi_tx_feedback_complete(ctypes.byref(state), tag, status, ctypes.byref(sequence))
        return result, sequence.value
    def test_completion_attributes_raw_status_to_full_width_sequence(self):
        state = State()
        tags = [self.reserve(state, seq) for seq in (0, 0xffffffff, 65536)]
        for tag, seq, status in zip(reversed(tags), (65536, 0xffffffff, 0), (255, 1, 0)):
            self.assertEqual(self.complete(state, tag, status), (1, seq))
            self.assertEqual(state.status[status], 1)
        self.assertEqual((state.requested, state.completed, state.pending), (3, 3, 0))
    def test_all_tags_in_use_refuse_overwrite_then_reuse_only_freed_slot(self):
        state = State()
        tags = [self.reserve(state, seq) for seq in range(128)]
        tag = ctypes.c_uint8(7)
        self.assertEqual(len(set(tags)), 128)
        self.assertEqual(self.lib.wifi_tx_feedback_reserve(ctypes.byref(state), 500, ctypes.byref(tag)), 0)
        self.assertEqual((tag.value, state.pending, state.skipped), (7, 128, 1))
        self.assertEqual(self.complete(state, tags[63], 3), (1, 63))
        self.assertEqual(self.reserve(state, 500), tags[63])
        self.assertEqual(self.complete(state, tags[63], 0), (1, 500))
    def test_management_tags_cannot_complete_a_data_sample(self):
        state = State()
        tag = self.reserve(state, 41)
        self.assertEqual(self.complete(state, tag & 127, 0)[0], 0)
        self.assertEqual((state.pending, state.completed, state.unmatched), (1, 0, 0))
    def test_duplicate_and_unassigned_events_do_not_count_as_success(self):
        state = State()
        tag = self.reserve(state, 8)
        self.assertEqual(self.complete(state, tag, 2), (1, 8))
        self.assertEqual(self.complete(state, tag, 0)[0], 0)
        self.assertEqual(self.complete(state, 255, 0)[0], 0)
        self.assertEqual((state.completed, state.status[0], state.unmatched), (1, 0, 2))
    def test_cancelled_submission_does_not_become_radio_completion(self):
        state = State()
        tag = self.reserve(state, 17)
        self.lib.wifi_tx_feedback_cancel(ctypes.byref(state), tag)
        self.lib.wifi_tx_feedback_cancel(ctypes.byref(state), tag)
        self.assertEqual((state.pending, state.cancelled), (0, 1))
        self.assertEqual(self.complete(state, tag, 0)[0], 0)
        self.assertEqual(state.completed, 0)

if __name__ == '__main__':
    unittest.main()
