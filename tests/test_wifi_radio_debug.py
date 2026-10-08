"""Exercise actual C wire codec and guarded finite radio query."""
import ctypes
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class RadioDebug(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT/'src/sdio.c').read_text()
        start = source.index('static int radio_debug_read(unsigned group){')
        actual = (source[start:source.index('static int rate_mailbox_read(unsigned index){',start)]
                  + source[source.index('void sdio_wifi_radio_debug(void){',start):
                           source.index('void sdio_wifi_station_stats(void){',start)])
        harness = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "wifi_fw_query.h"
typedef uint32_t TickType_t;
static unsigned mode,calls,ticks,events,wifi_hif_ready,wifi_tx_fault;
static uint8_t wifi_sequence,saved[272];static char output[24000];
static void uart_puts(const char *s){unsigned n=0;while(output[n])n++;while(*s && n<sizeof output-1)output[n++]=*s++;output[n]=0;}
static void field(const char *s,unsigned n){char b[128];snprintf(b,sizeof b,"%s%08x",s,n);uart_puts(b);}
static int tuner_ts_stream_active(void){return mode==1;}
static TickType_t xTaskGetTickCount(void){ticks+=1000;return ticks;}
static void vTaskDelay(unsigned n){(void)n;}
static int control_send(unsigned cid,unsigned set,uint8_t *p,unsigned n){
 if(cid!=0xc6 || set || n!=272)return -1;
 calls++;memcpy(saved,p,n);wifi_sequence++;return mode==4?-1:0;
}
static int event_read(uint8_t *p,unsigned capacity,unsigned *length){
 (void)capacity;events++;if(mode==5)return -1;if(mode==6)return 0;
 memset(p,0,272);*length=272;p[0]=0x10;p[1]=1;p[2]=1;p[4]=0x1f;p[5]=wifi_sequence;p[8]=saved[8];p[11]=0xb0;p[12]=saved[8];
 for(unsigned n=0;n<64;n++){p[16+4*n]=n;p[17+4*n]=0x12;p[18+4*n]=0x34;p[19+4*n]=0x56;}
 if(mode==7){p[4]=1;p[8]=0xc6;p[9]=2;}
 if(mode==8){*length=16;p[0]=16;p[1]=0;}
 if(mode==9)p[11]=0xa0;
 if(mode==10 && events==1)p[5]--;
 if(mode==11)p[8]^=1;
 if(mode==12 && calls==2){p[4]=1;p[8]=0xc6;p[9]=2;}
 return 1;
}
void sdio_wifi_radio_debug(void);
void sdio_wifi_radio_groups(void);
void run(unsigned value){mode=value;calls=ticks=events=0;wifi_sequence=10;wifi_hif_ready=mode!=2;wifi_tx_fault=mode==3;output[0]=0;memset(saved,0xa5,sizeof saved);sdio_wifi_radio_debug();}
void run_groups(unsigned value){run(value);calls=ticks=events=0;output[0]=0;sdio_wifi_radio_groups();}
const char *log_text(void){return output;} unsigned sent(void){return calls;}
const uint8_t *wire(void){return saved;}
'''
        cls.tmp=tempfile.TemporaryDirectory()
        folder=pathlib.Path(cls.tmp.name)
        (folder/'probe.c').write_text(harness+actual)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(folder/'probe.c'),str(ROOT/'src/wifi_fw_query.c'),'-o',str(folder/'probe.so')],check=True)
        cls.c=ctypes.CDLL(str(folder/'probe.so'))
        cls.c.log_text.restype=ctypes.c_char_p
        cls.c.wire.restype=ctypes.c_void_p
        cls.c.wifi_radio_debug_query.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        cls.c.wifi_radio_debug_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint8,ctypes.c_void_p]
        cls.c.wifi_radio_debug_group_query.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint]
        cls.c.wifi_radio_debug_group_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint8,ctypes.c_uint,ctypes.c_void_p]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_zero_initialized_wire_and_guard_boundaries(self):
        buf=(ctypes.c_ubyte*280)(*([0xa5]*280))
        self.assertEqual(self.c.wifi_radio_debug_query(buf,271),0)
        self.assertEqual(bytes(buf),bytes([0xa5])*280)
        self.assertEqual(self.c.wifi_radio_debug_query(None,272),0)
        self.assertEqual(self.c.wifi_radio_debug_query(buf,280),272)
        expected=bytearray(272);expected[11]=0xb0
        self.assertEqual(bytes(buf),bytes(expected)+bytes([0xa5])*8)
    def test_decode_exact_framing_and_output_preservation(self):
        packet=bytearray(272);packet[:6]=bytes([0x10,1,1,0,0x1f,27]);packet[11]=0xb0
        for i in range(64):packet[16+i*4:20+i*4]=(0x56341200+i).to_bytes(4,'little')
        raw=(ctypes.c_ubyte*272).from_buffer_copy(packet)
        out=(ctypes.c_uint32*64)()
        self.assertEqual(self.c.wifi_radio_debug_decode(raw,272,27,out),1)
        self.assertEqual(list(out),[0x56341200+i for i in range(64)])
        for pos in (0,1,2,3,4,5,8,9,10,11,12):
            bad=bytearray(packet);bad[pos]^=1;data=(ctypes.c_ubyte*272).from_buffer_copy(bad)
            for i in range(64):out[i]=0xa5a5a5a5
            self.assertEqual(self.c.wifi_radio_debug_decode(data,272,27,out),0)
            self.assertEqual(list(out),[0xa5a5a5a5]*64)
        for length in (0,16,271,273):self.assertEqual(self.c.wifi_radio_debug_decode(raw,length,27,out),0)
        self.assertEqual(self.c.wifi_radio_debug_decode(None,272,27,out),0)
        self.assertEqual(self.c.wifi_radio_debug_decode(raw,272,27,None),0)
    def test_guarded_failures_and_finite_wait(self):
        cases={1:'refused-stream',2:'refused-state',3:'refused-state',4:'failed',5:'failed',6:'timeout',7:'rejected',8:'unsupported-layout',9:'unsupported-layout'}
        for mode,status in cases.items():
            self.c.run(mode);log=self.c.log_text()
            self.assertIn(('end status='+status).encode(),log)
            self.assertNotIn(b'=read-raw',log)
            self.assertEqual(self.c.sent(),0 if mode<4 else 1)
    def test_exact_words_and_skip_wrong_sequence(self):
        for mode in (0,10):
            self.c.run(mode)
            log=self.c.log_text()
            self.assertIn(b'end status=read-raw',log)
            self.assertIn(b'raw_index=00000020 value=56341220',log)
            self.assertEqual(log.count(b'raw_index='),64)
            self.assertEqual(self.c.sent(),1)
            expected=bytearray(272);expected[11]=0xb0
            self.assertEqual(ctypes.string_at(self.c.wire(),272),bytes(expected))

    def test_group_wire_identity_and_bounded_output(self):
        buf=(ctypes.c_ubyte*280)(*([0xa5]*280))
        for group in range(4):
            self.assertEqual(self.c.wifi_radio_debug_group_query(buf,280,group),272)
            expected=bytearray(272);expected[8]=group;expected[11]=0xb0
            self.assertEqual(bytes(buf),bytes(expected)+b'\xa5'*8)
            packet=bytearray(expected);packet[:6]=bytes([0x10,1,1,0,0x1f,27]);packet[12]=group
            out=(ctypes.c_uint32*64)(*([0xa5a5a5a5]*64))
            self.assertEqual(self.c.wifi_radio_debug_group_decode(bytes(packet),272,27,(group+1)%4,out),0)
            self.assertEqual(list(out),[0xa5a5a5a5]*64)
            self.assertEqual(self.c.wifi_radio_debug_group_decode(bytes(packet),272,27,group,out),1)
            self.assertEqual(list(out),[0]*64)
            packet[12]^=1
            for i in range(64):out[i]=0xa5a5a5a5
            self.assertEqual(self.c.wifi_radio_debug_group_decode(bytes(packet),272,27,group,out),0)
            self.assertEqual(list(out),[0xa5a5a5a5]*64)
        buf[:]=[0xa5]*280
        for capacity,group in ((271,1),(280,4),(280,0xffffffff)):
            self.assertEqual(self.c.wifi_radio_debug_group_query(buf,capacity,group),0)
        self.assertEqual(bytes(buf),b'\xa5'*280)
        self.assertEqual(self.c.wifi_radio_debug_group_decode(bytes(packet),272,27,4,out),0)

    def test_group_batch_completion_and_early_failure(self):
        self.c.run_groups(0);log=self.c.log_text()
        self.assertEqual(self.c.sent(),3)
        self.assertEqual(log.count(b'raw_index='),192)
        self.assertIn(b'groups end status=read-raw',log)
        for group in (1,2,3):self.assertIn(f'group={group:08x}'.encode(),log)
        for mode,expected in ((1,0),(2,0),(3,0),(6,1),(11,1),(12,2)):
            self.c.run_groups(mode);log=self.c.log_text()
            self.assertEqual(self.c.sent(),expected)
            self.assertIn(b'groups end status=failed',log)
            self.assertNotIn(b'groups end status=read-raw',log)

if __name__=='__main__':unittest.main()
