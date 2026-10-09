"""Actual channel wire/guard logic and stream-stop timing exclusion ordering."""
import ctypes as C
import pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Channels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sdio=(ROOT/'src/sdio.c').read_text()
        select=sdio[sdio.index('void sdio_wifi_channel(void){'):]
        tuner=(ROOT/'src/tuner_ts.c').read_text()
        stop=tuner[tuner.index('void tuner_ts_stream_stop(void){'):tuner.index('static void field(const char *name,unsigned number){')]
        harness=r'''
#include <stdint.h>
#include "wifi_io_timing.h"
#include "wifi_service_timing.h"
static struct wifi_service_timing wifi_service;
static uint32_t board_time_counts(void){return 42;}
static struct wifi_io_timing wifi_io;
static unsigned wifi_wait_yields,wifi_io_yields,wifi_io_irq_waits,wifi_io_irq_ready;
static unsigned wifi_io_yields_begin,wifi_io_irq_begin,wifi_io_ready_begin;

static unsigned sdio_irq_counter(unsigned index){(void)index;return 0;}
#include "wifi_channel.h"
#include "wifi_tx_timing.h"
static unsigned wifi_ap_active,wifi_peer_state,wifi_peer_activate_pending,wifi_hif_ready,wifi_tx_fault;
static unsigned wifi_tc1_free,wifi_tc4_free,wifi_tc5_free,wifi_ap_channel,wifi_timing_enabled,wifi_channel_bssid_mode;
static struct {unsigned pending;} wifi_feedback;
static struct wifi_tx_timing wifi_timing;
static unsigned streaming,pending,position,sequence,packet_index,stream_over,stream_under,stream_busy;
static unsigned stream_read_ticks,stream_tx_ticks,stream_poll_ticks,checking_stop,early_output;
static unsigned stream_dma_reads,stream_dma_ticks;
static unsigned stream_pattern_checks,stream_pattern_errors,stream_pattern_first;
static void stream_pipeline_abort(void){}
static int tuner_ts_stream_active(void){return streaming!=0;}
static void uart_puts(const char *s){(void)s;if(checking_stop && wifi_timing.active)early_output++;}
static void field(const char *s,unsigned n){(void)n;uart_puts(s);}
void reset(unsigned channel,unsigned active,unsigned fault,unsigned free){
    wifi_ap_channel=channel;wifi_channel_bssid_mode=0;wifi_ap_active=active&1;wifi_peer_state=active&2;
    wifi_peer_activate_pending=active&4;streaming=active&8;
    wifi_hif_ready=!(fault&1);wifi_tx_fault=fault&2;wifi_feedback.pending=fault&4;
    wifi_tc1_free=free;wifi_tc4_free=fault&8?3:4;wifi_tc5_free=fault&16?0:1;
    checking_stop=early_output=0;wifi_timing_enabled=0;wifi_tx_timing_reset(&wifi_timing);
}
unsigned selected(void){return wifi_ap_channel;}
unsigned bssid_mode(void){return wifi_channel_bssid_mode;}
void start_timed(void){
    wifi_timing_enabled=checking_stop=1;wifi_tx_timing_begin(&wifi_timing,7,10);
    wifi_feedback.pending=3;wifi_tc1_free=13;streaming=1;pending=7;position=3;
}
void return_credit(void){wifi_tx_timing_credit(&wifi_timing,14,1000);}
unsigned state(unsigned n){unsigned v[]={wifi_timing.active,wifi_timing.excluded,early_output,streaming,pending,position,wifi_feedback.pending,wifi_tc1_free,wifi_timing.bin[6].credits};return v[n];}
'''
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'actual.c').write_text(harness+select+stop)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
            str(p/'actual.c'),str(ROOT/'src/wifi_channel.c'),str(ROOT/'src/wifi_tx_timing.c'),
            str(ROOT/'src/wifi_rates.c'),str(ROOT/'src/wifi_mgmt.c'),str(ROOT/'src/wifi_io_timing.c'),str(ROOT/'src/wifi_service_timing.c'),'-o',str(p/'channel.so')],check=True)
        cls.c=C.CDLL(str(p/'channel.so'))
        cls.c.wifi_channel_request_ap.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_void_p]
        cls.c.wifi_channel_request.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_void_p]
        cls.c.wifi_channel_grant.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint]
        cls.c.wifi_rates_ies_channel.argtypes=[C.c_uint,C.c_uint,C.c_uint,C.c_void_p,C.c_uint]
        cls.c.wifi_mgmt_reply_channel.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint16,C.c_void_p,C.c_uint,C.c_uint,C.c_uint]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_request_fields_and_failed_request_preserves_output(self):
        for channel in (1,6,11):
            out=(C.c_uint8*32)(*([165]*32));mac=bytes.fromhex('000369071d22')
            self.assertEqual(self.c.wifi_channel_request(out,32,channel,7,mac),1)
            self.assertEqual(bytes(out[:28]),bytes(8)+bytes([1,7,0,channel,0,1,0,0])+bytes.fromhex('60ea0000')+mac+bytes(2))
            self.assertEqual(bytes(out[28:]),bytes([165])*4)
        for capacity,channel,token in ((27,1,7),(32,0,7),(32,14,7),(32,6,0),(32,6,256)):
            out=(C.c_uint8*32)(*([165]*32))
            self.assertEqual(self.c.wifi_channel_request(out,capacity,channel,token,mac),0)
            self.assertEqual(bytes(out),bytes([165])*32)
        self.assertEqual(self.c.wifi_channel_request(None,28,1,1,mac),0)
    def test_grant_checks_identity_status_band_and_secondary_channel(self):
        packet=bytearray(20);packet[4]=0x18;packet[8:14]=bytes([1,7,0,6,0,1])
        self.assertEqual(self.c.wifi_channel_grant(bytes(packet),20,6,7),1)
        for offset,value in ((4,0x13),(8,0),(9,8),(10,1),(11,1),(12,1),(13,2)):
            bad=packet.copy();bad[offset]=value
            self.assertEqual(self.c.wifi_channel_grant(bytes(bad),20,6,7),0)
        self.assertEqual(self.c.wifi_channel_grant(bytes(packet),19,6,7),0)
        self.assertEqual(self.c.wifi_channel_grant(None,20,6,7),0)
    @staticmethod
    def ds(data):
        pos=0;channels=[]
        while pos<len(data):
            size=data[pos+1]
            if data[pos]==3:channels.append(data[pos+2:pos+2+size])
            pos+=2+size
        return channels
    def test_beacon_and_real_probe_reply_channel_agree(self):
        mac=bytes.fromhex('000369071d22');peer=bytes.fromhex('020102030405')
        probe=bytes([0x40,0,0,0])+bytes([255])*6+peer+bytes([255])*6+bytes(2)+bytes([0,0])
        for channel in (1,6,11):
            for profile in (0,1):
                ies=(C.c_uint8*48)();n=self.c.wifi_rates_ies_channel(profile,1,channel,ies,48)
                out=(C.c_uint8*128)();m=self.c.wifi_mgmt_reply_channel(probe,len(probe),mac,1,out,128,profile,channel)
                self.assertGreater(m,36)
                self.assertEqual(self.ds(bytes(ies[:n])),[bytes([channel])])
                self.assertEqual(self.ds(bytes(out[36:m])),[bytes([channel])])
        out=(C.c_uint8*48)(*([165]*48))
        self.assertEqual(self.c.wifi_rates_ies_channel(0,1,14,out,48),0)
        self.assertEqual(bytes(out),bytes([165])*48)
    def test_selector_refuses_active_unhealthy_or_unreturned_resources(self):
        for active in (1,2,4,8):
            self.c.reset(1,active,0,14);self.c.sdio_wifi_channel();self.assertEqual(self.c.selected(),1)
        for fault in (1,2,4,8,16):
            self.c.reset(1,0,fault,14);self.c.sdio_wifi_channel();self.assertEqual(self.c.selected(),1)
        self.c.reset(1,0,0,13);self.c.sdio_wifi_channel();self.assertEqual(self.c.selected(),1)
        self.c.reset(1,0,0,14)
        for channel in (6,11,1):self.c.sdio_wifi_channel();self.assertEqual(self.c.selected(),channel)
    def test_stop_excludes_credit_before_output_without_refunding_or_canceling_feedback(self):
        self.c.reset(1,0,0,14);self.c.start_timed();self.c.tuner_ts_stream_stop();self.c.return_credit()
        self.assertEqual([self.c.state(i) for i in range(9)],[0,1,0,0,0,0,3,13,0])
        self.c.tuner_ts_stream_stop();self.assertEqual(self.c.state(1),1)
    def test_ap_zero_request_preserves_every_other_wire_field(self):
        mac=bytes.fromhex('000369071d22')
        for channel in (1,6,11):
            for token in (1,255):
                old=(C.c_uint8*32)(*([165]*32));new=(C.c_uint8*32)(*([165]*32))
                self.assertEqual(self.c.wifi_channel_request_ap(old,32,channel,token,1,mac),1)
                self.assertEqual(self.c.wifi_channel_request_ap(new,32,channel,token,0,mac),1)
                self.assertEqual(bytes(old[20:26]),mac)
                self.assertEqual(bytes(new[20:26]),bytes(6))
                self.assertEqual(bytes(new[:20]),bytes(old[:20]));self.assertEqual(bytes(new[26:]),bytes(old[26:]))
        for args in ((27,1,1,0,mac),(32,14,1,0,mac),(32,1,0,0,mac),(32,1,1,2,mac),(32,1,1,0,None)):
            new[:]=[165]*32
            self.assertEqual(self.c.wifi_channel_request_ap(new,*args),0);self.assertEqual(bytes(new),bytes([165])*32)
    def test_bssid_selector_refuses_live_or_unreturned_state(self):
        for active in (1,2,4,8):
            self.c.reset(1,active,0,14);self.c.sdio_wifi_channel_bssid();self.assertEqual(self.c.bssid_mode(),0)
        for fault in (1,2,4,8,16):
            self.c.reset(1,0,fault,14);self.c.sdio_wifi_channel_bssid();self.assertEqual(self.c.bssid_mode(),0)
        self.c.reset(1,0,0,13);self.c.sdio_wifi_channel_bssid();self.assertEqual(self.c.bssid_mode(),0)
        self.c.reset(6,0,0,14)
        for mode in (1,0,1):
            self.c.sdio_wifi_channel_bssid();self.assertEqual(self.c.bssid_mode(),mode);self.assertEqual(self.c.selected(),6)
if __name__=='__main__':unittest.main()
