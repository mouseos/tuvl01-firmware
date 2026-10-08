"""Actual SDIO-owner AIS lease probe: bounded input, correlated grant, cleanup."""
import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AisProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        p = pathlib.Path(cls.tmp.name)
        source = (ROOT/'src/sdio.c').read_text()
        start = source.index('static unsigned ais_lease_left(')
        body = source[start:source.index('\nstatic int control_set(', start)]
        harness = r'''
#include <stdint.h>
#include <string.h>
#include "wifi_channel.h"
#include "wifi_ais_mgmt.h"
#include "wifi_ais_beacon.h"
#include "wifi_scan_cache.h"
#include "wifi_ais_rsn.h"
#include "wifi_ais_join.h"
static struct wifi_ais_join wifi_ais_connection;
static struct wifi_scan_cache wifi_bss_cache;
#include "wifi_station.h"
typedef uint32_t TickType_t;
static unsigned wifi_hif_ready,wifi_tx_fault,wifi_ap_active,wifi_peer_state;
static unsigned wifi_peer_activate_pending,wifi_management_pending,wifi_bench_active;
static unsigned wifi_sink_active,wifi_scan_active,wifi_scan_unresolved;
static unsigned wifi_connection_unresolved,wifi_ais_cam_attempted,wifi_ais_cam_transferred;
static unsigned wifi_ais_retained_active,wifi_ais_retained_teardown;
static void reset_retained(void);
static uint8_t wifi_channel_token,wifi_sequence;
static uint8_t wifi_mac[6]={2,0,0,0,0,2},wifi_management_tx_sequence;
static unsigned wifi_mac_valid,wifi_rate_profile;
static uint16_t wifi_management_sequence;
static unsigned mode,input,activation,deactivation,submissions,aborts,ready,failed,refused;
static uint8_t target[7],saved[28];static uint32_t ticks,grant;
static unsigned auth_mode,rx,station_writes,station_removes,txs,txdone_seen,auth_seen;
static uint8_t saved_station[48],saved_tx[48];
static uint8_t saved_assoc_tx[128];static unsigned assoc_rx,assoc_length;
static unsigned bss_writes,pm_writes,pm_aborts,join_order;
static unsigned filter_writes;
static uint8_t saved_bss[88],saved_pm[20];
static void join_events(void);
static void join_beacon(void);
static int wifi_wpa_radio_validate(const uint8_t *own,const struct wifi_ais_beacon *b){
 (void)own;(void)b;return mode==54?-1:0;
}
static unsigned wifi_wpa_radio_assoc_ie(uint8_t *p,unsigned capacity){
 static const uint8_t rsn[]={48,20,1,0,0,15,172,4,1,0,0,15,172,4,1,0,0,15,172,2,0,0};
 if(mode==56 || capacity<sizeof rsn)return 0;
 memcpy(p,rsn,sizeof rsn);return sizeof rsn;
}
static int same_text(const char *a,const char *b){
 unsigned i=0;while(a[i] && a[i]==b[i])i++;return a[i]==b[i];
}
static void uart_puts(const char *s){
 if(same_text(s,"WIFI AIS channel probe end status=ready\n"))ready++;
 if(same_text(s,"WIFI AIS channel probe end status=refused-active\n"))refused++;
 if(same_text(s,"WIFI AIS auth probe end status=ready\n"))ready++;
 if(same_text(s,"WIFI AIS auth probe end status=refused-active\n"))refused++;
 if(same_text(s,"WIFI AIS auth probe end status=failed\n") ||
    same_text(s,"WIFI AIS auth probe end status=invalid-target\n") ||
    same_text(s,"WIFI AIS auth probe end status=input-timeout\n"))failed++;
 if(same_text(s,"WIFI AIS channel probe end status=failed\n") ||
    same_text(s,"WIFI AIS channel probe end status=invalid-target\n") ||
    same_text(s,"WIFI AIS channel probe end status=input-timeout\n"))failed++;
}
static void field(const char *s,unsigned n){
 if(same_text(s," interval_ms="))grant=n;
 if(same_text(s,"WIFI AIS authentication TXdone status="))txdone_seen++;
 if(same_text(s,"WIFI AIS authentication response status="))auth_seen++;
}
static int uart_getc(void){return mode==1 || input>=7?-1:target[input++];}
static TickType_t xTaskGetTickCount(void){return ticks;}
static void vTaskDelay(unsigned n){ticks+=n;}
static int control_set(unsigned cid,uint8_t *p,unsigned n){
 if(cid==0x0b && n==12){
  if(join_order || !wifi_ais_cam_transferred || txs!=2 || p[8]!=0x0b)return -1;
  for(unsigned i=9;i<n;i++)if(p[i])return -1;
  filter_writes++;return mode==52?-1:0;
 }
 if(cid==6 && n==12){
  if(join_order)return -1;
  for(unsigned i=8;i<n;i++)if(p[i])return -1;
  return mode==51?-1:0;
 }
 if(cid==0x17 && n==48){
  station_writes++;memcpy(saved_station,p,n);
  if(p[28]==3){if(join_order!=1)return -1;join_order=2;join_events();}
  return mode==12 || (mode==30 && p[28]==2) || (mode==42 && p[28]==3)?-1:0;
 }
 if(cid==0x16 && n==88){
  bss_writes++;memcpy(saved_bss,p,n);
  if(!p[9]){
   if(join_order || filter_writes!=1)return -1;
   join_order=1;if(mode==57 || mode==61)join_beacon();
   return mode==41 || mode==61?-1:0;
  }
  return mode==48?-1:0;
 }
 if(cid==0x1a && n==20){
  if(join_order!=2)return -1;
  join_order=3;pm_writes++;memcpy(saved_pm,p,n);return mode==46?-1:0;
 }
 if(cid==0x1b && n==12){pm_aborts++;return mode==47?-1:0;}
 if(cid==0x18 && n==16){
  for(unsigned i=0;i<6;i++)if(p[10+i]!=target[1+i])return -1;
  station_removes++;return mode==20?-1:0;
 }
 if(cid==0x15 && n==12 && !p[8]){
  if(p[9]){activation++;return mode==2?-1:0;}
  deactivation++;return mode==8?-1:0;
 }
 if(cid==0x20 && n==28 && !p[8] && p[9]==wifi_channel_token && p[10]==1){
  for(unsigned i=11;i<28;i++)if(p[i])return -1;
  aborts++;return mode==7 || mode==55?-1:0;
 }
 return -1;
}
static int control_send(unsigned cid,unsigned set,uint8_t *p,unsigned n){
 if(cid!=0x20 || set!=1 || n!=28)return -1;
 submissions++;memcpy(saved,p,n);wifi_sequence++;return mode==3?-1:0;
}
static int radio_read(unsigned a,uint32_t *value){
 if(a==0){*value=0x335931;return 0;}
 if(a==4){*value=0x101;return 0;}
 if(a==0x50){*value=0;return 0;}
 return -1;
}
static int event_read(uint8_t *p,unsigned capacity,unsigned *n){
 (void)capacity;if(mode==4){*n=0;return 0;}if(mode==5)return -1;
 if(auth_mode && txs==2){
  memset(p,0,100);unsigned step=assoc_rx++;
  unsigned reverse=mode==29;
  if(step==(reverse?1:0)){
   *n=12;p[0]=12;p[2]=1;p[4]=0x17;
   p[8]=saved_assoc_tx[12]+(mode==31);p[9]=mode==32?1:0;
   if(mode==36){*n=0;return 0;}return 1;
  }
  if(step==(reverse?0:1)){
   uint8_t *b=p+12;*n=48;p[0]=48;p[2]=3;p[5]=mode==38?3:1;
   b[0]=0x10;memcpy(b+4,wifi_mac,6);memcpy(b+10,target+1,6);memcpy(b+16,target+1,6);
   if(mode==34)b[10]^=2;
   b[24]=0x31;b[26]=mode==33?13:0;b[28]=mode==35?0:7;b[29]=0xc0;
   b[30]=1;b[31]=4;b[32]=0x82;b[33]=0x84;b[34]=0x8b;b[35]=0x96;
   if(mode==37){*n=0;return 0;}return 0;
  }
  *n=0;return 0;
 }
 if(auth_mode && rx++){
  memset(p,0,100);
  if(rx==2){
   if(mode==10 || mode==21 || mode==26){*n=0;return 0;}
   uint8_t *b=p+12;*n=63;p[0]=63;p[2]=3;p[5]=1;p[9]=100;p[10]=11;
   b[0]=0x80;memset(b+4,255,6);memcpy(b+10,target+1,6);memcpy(b+16,target+1,6);
   b[32]=100;b[34]=0x31;b[35]=4;
   b[36]=0;b[37]=4;memcpy(b+38,"TEST",4);b[42]=1;b[43]=4;
   b[44]=0x82;b[45]=0x84;b[46]=0x8b;b[47]=0x96;b[48]=3;b[49]=1;
   b[50]=mode==11?10:11;return 0;
  }
  if(mode==10 || mode==11){*n=0;return 0;}
  if(mode==23)return -1;
  unsigned auth_first=(mode==19);
  if(rx==(auth_first?4:3)){
   *n=12;p[0]=12;p[2]=1;p[4]=0x17;
   p[8]=saved_tx[12]+(mode==15);p[9]=mode==16?1:0;
   if(mode==22){*n=0;return 0;}return 1;
  }
  if(rx==(auth_first?3:4)){
   uint8_t *b=p+12;*n=42;p[0]=42;p[2]=3;p[5]=mode==24?0x11:mode==25?3:1;
   b[0]=0xb0;memcpy(b+4,wifi_mac,6);memcpy(b+10,target+1,6);memcpy(b+16,target+1,6);
   if(mode==18)b[10]^=2;
   b[26]=2;b[28]=mode==17?13:0;return 0;
  }
  *n=0;return 0;
 }
 memset(p,0,20);p[0]=20;p[2]=1;p[4]=0x18;p[9]=saved[9]+(mode==6);
 p[11]=saved[11];p[13]=1;
 unsigned interval=auth_mode?(mode==21?500:5000):2000;
 p[16]=interval;p[17]=interval>>8;*n=20;
 if(mode==27)ticks+=5001;
 return 1;
}
static int tc4_wait(void){return mode==13 || (mode==30 && txs==1)?-1:0;}
static int tc4_write(const uint8_t *p,unsigned n){
 if(!txs && n!=48)return -1;
 if(n>128)return -1;
 if(txs){memcpy(saved_assoc_tx,p,n);assoc_length=n;}
 else memcpy(saved_tx,p,n);
 txs++;return mode==14 || (mode==39 && txs==2)?-1:0;
}
void reset(unsigned selected_mode,unsigned flags,unsigned invalid,uint32_t tick){
 reset_retained();
 mode=selected_mode;ticks=tick;input=0;wifi_channel_token=255;wifi_sequence=0;
 wifi_hif_ready=!(flags&1);wifi_tx_fault=flags&2;wifi_ap_active=flags&4;
 wifi_peer_state=flags&8;wifi_peer_activate_pending=flags&16;
 wifi_management_pending=flags&32;wifi_bench_active=flags&64;
 wifi_sink_active=flags&128;wifi_scan_active=flags&256;wifi_scan_unresolved=flags&512;
 wifi_connection_unresolved=flags&1024;wifi_ais_cam_attempted=wifi_ais_cam_transferred=0;
 activation=deactivation=submissions=aborts=ready=failed=refused=grant=0;
 auth_mode=rx=station_writes=station_removes=txs=txdone_seen=auth_seen=0;
 assoc_rx=assoc_length=0;
 bss_writes=pm_writes=pm_aborts=join_order=0;
 filter_writes=0;
 wifi_ais_connection=(struct wifi_ais_join){0};
 wifi_mac_valid=mode!=9;wifi_rate_profile=0;wifi_management_sequence=0;
 wifi_management_tx_sequence=127;
 memset(target,0,7);target[0]=11;target[1]=2;target[6]=1;
 if(invalid==1)target[0]=14;if(invalid==2)target[1]=3;
 if(invalid==3)memset(target+1,0,6);
}
unsigned state(unsigned i){unsigned s[]={activation,deactivation,submissions,aborts,
 ready,failed,refused,grant,input,wifi_channel_token,station_writes,station_removes,
 txs,txdone_seen,auth_seen};return s[i];}
const uint8_t *request(void){return saved;}
const uint8_t *station_request(void){return saved_station;}
const uint8_t *tx_request(void){return saved_tx;}
void run_auth(void){
 struct wifi_ais_beacon b={0};
 memcpy(b.ap,target+1,6);b.channel=11;b.rx_channel=mode==11?10:11;
 b.operational=b.basic=15;
 wifi_scan_cache_begin(&wifi_bss_cache);
 if(mode!=10)wifi_scan_cache_observe(&wifi_bss_cache,&b,ticks,wifi_rate_profile,100);
 wifi_scan_cache_finish(&wifi_bss_cache,1);
 auth_mode=1;sdio_wifi_ais_auth_probe();
}
'''
        harness=harness.replace('void run_auth(void)', 'void sdio_wifi_ais_auth_probe(void);\nvoid run_auth(void)')
        # Keep consecutive conditions on separate lines for -Werror diagnostics.
        harness = harness.replace('target[0]=14;if', 'target[0]=14;\n if')
        extra = r'''
static void reset_retained(void){
 ais_retained=(struct ais_resources){0};wifi_ais_retained_active=wifi_ais_retained_teardown=0;
}
static struct ais_resources retained;
static int cleanup_result;
void prepare_cleanup(void){
 retained=(struct ais_resources){0};memcpy(retained.target,target,7);retained.token=wifi_channel_token;
 retained.activated=retained.requested=retained.station_attempted=1;
}
void begin_cleanup(void){
 prepare_cleanup();
 cleanup_result=ais_cleanup(&retained);
}
int repeat_cleanup(void){return ais_cleanup(&retained);}
int cleanup_state(unsigned i){int s[]={cleanup_result,(int)retained.closed,(int)retained.failed};return s[i];}
void foreign_cleanup(void){
 wifi_ais_connection.aid=7;memcpy(wifi_ais_connection.selected.ap,target+1,6);
 wifi_ais_connection.selected.ap[5]^=1;begin_cleanup();
}
void foreign_token_cleanup(void){
 prepare_cleanup();retained.token^=1;cleanup_result=ais_cleanup(&retained);
}
void run_assoc(void){
 struct wifi_ais_beacon b={0};
 static const uint8_t rsn[]={48,20,1,0,0,15,172,4,1,0,0,15,172,4,1,0,0,15,172,2,0,0};
 memcpy(b.ap,target+1,6);b.channel=b.rx_channel=11;
 b.operational=b.basic=15;b.capability=0x31;b.ssid_length=4;memcpy(b.ssid,"TEST",4);b.interval=100;
 memcpy(b.rsn,rsn,sizeof rsn);b.rsn_length=sizeof rsn;
 if(mode==40)b.rsn[20]=64;
 wifi_scan_cache_begin(&wifi_bss_cache);
 wifi_scan_cache_observe(&wifi_bss_cache,&b,ticks,wifi_rate_profile,100);
 wifi_scan_cache_finish(&wifi_bss_cache,1);
 auth_mode=1;
 if(mode>=53)sdio_wifi_wpa_join(target);
 else if(mode>=41)sdio_wifi_ais_connect_probe();else sdio_wifi_ais_assoc_probe();
}
unsigned retained_state(unsigned i){unsigned s[]={wifi_ais_retained_active,ais_retained.requested,
 ais_retained.closed,ais_retained.failed,wifi_ais_connection.aid};return s[i];}
int retry_retained(void){return sdio_wifi_wpa_join(target);}
int release_join_again(void){return ais_release_join(&ais_retained);}
const uint8_t *assoc_request(void){return saved_assoc_tx;}
unsigned assoc_size(void){return assoc_length;}
static void join_beacon(void){
 uint8_t packet[128]={0};uint8_t *b=packet+12;
 packet[2]=3;packet[5]=1;packet[10]=mode==60?10:11;b[0]=0x80;
 memset(b+4,255,6);memcpy(b+10,target+1,6);memcpy(b+16,target+1,6);
 b[32]=100;b[34]=0x31;b[36]=0;b[37]=4;memcpy(b+38,"TEST",4);
 const uint8_t rates[]={1,4,0x82,0x84,0x8b,0x96,3,1,11,5,4,0,3,0,0};
 memcpy(b+42,rates,sizeof rates);
 memcpy(b+42+sizeof rates,wifi_ais_connection.selected.rsn,22);
 unsigned n=12+42+sizeof rates+22;packet[0]=n;
 wifi_ais_join_observe(&wifi_ais_connection,packet,n);
}
static void join_events(void){
 /* Both events arrive while control_set is waiting for credit return. */
 uint8_t activate[20]={20,0,1,0,0x13,0,0,0};
 memcpy(activate+8,target+1,6);activate[17]=1;
 if(mode==45)activate[15]=1;
 if(mode==58)join_beacon();
 if(mode!=43 && mode!=59)wifi_ais_join_observe(&wifi_ais_connection,activate,20);
 if(mode==44 || mode==57 || mode==58)return;
 join_beacon();
}

unsigned join_state(unsigned i){unsigned s[]={bss_writes,pm_writes,pm_aborts,join_order};return s[i];}
unsigned cam_state(unsigned i){unsigned s[]={wifi_ais_cam_attempted,wifi_ais_cam_transferred,wifi_connection_unresolved};return s[i];}
unsigned filter_count(void){return filter_writes;}
const uint8_t *pm_request(void){return saved_pm;}
'''
        (p/'probe.c').write_text(harness+body+extra)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
                        '-I'+str(ROOT/'include'),str(p/'probe.c'),
                        *[str(ROOT/'src'/name) for name in ('wifi_channel.c','wifi_ais_mgmt.c',
                          'wifi_ais_beacon.c','wifi_station.c','wifi_rates.c','wifi_scan_cache.c',
                          'wifi_ais_rsn.c','wifi_ais_join.c','wifi_ais_bss.c')],
                        '-o',str(p/'probe.so')],check=True)
        cls.c=C.CDLL(str(p/'probe.so'))
        cls.c.reset.argtypes=[C.c_uint,C.c_uint,C.c_uint,C.c_uint32]
        cls.c.request.restype=C.c_void_p
        cls.c.station_request.restype=cls.c.tx_request.restype=C.c_void_p
        cls.c.assoc_request.restype=C.c_void_p
        cls.c.pm_request.restype=C.c_void_p

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, mode=0, flags=0, invalid=0, tick=0):
        self.c.reset(mode,flags,invalid,tick)
        self.c.sdio_wifi_ais_channel_probe()
        return [self.c.state(i) for i in range(10)]

    def test_real_request_correlated_grant_and_release(self):
        self.assertEqual(self.run_probe(),[1,1,1,1,1,0,0,2000,7,1])
        expected=bytearray(28);expected[9]=1;expected[11]=11;expected[13]=1
        expected[16:20]=(5000).to_bytes(4,'little')
        expected[20:26]=bytes([2,0,0,0,0,1])
        self.assertEqual(C.string_at(self.c.request(),28),expected)

    def test_active_or_faulted_refused_before_input_or_io(self):
        for flag in (1,2,4,8,16,32,64,128,256,512,1024):
            self.assertEqual(self.run_probe(flags=flag)[:9],[0,0,0,0,0,0,1,0,0])

    def test_auth_refuses_unresolved_scan_before_reading_target_or_sending(self):
        self.c.reset(0,512,0,0)
        self.c.sdio_wifi_ais_auth_probe()
        self.assertEqual([self.c.state(i) for i in range(9)],[0,0,0,0,0,0,1,0,0])

    def test_invalid_input_and_timeout_before_mutation(self):
        for invalid in (1,2,3):
            self.assertEqual(self.run_probe(invalid=invalid)[:7],[0,0,0,0,0,1,0])
        for tick in (0,0xfffffff0):
            self.assertEqual(self.run_probe(mode=1,tick=tick)[:7],[0,0,0,0,0,1,0])

    def test_uncertain_activation_submission_and_rx_failures_cleanup(self):
        self.assertEqual(self.run_probe(mode=2)[:7],[1,1,0,0,0,1,0])
        for mode in (3,4,5,6):
            for tick in (0,0xfffffff0):
                self.assertEqual(self.run_probe(mode=mode,tick=tick)[:7],[1,1,1,1,0,1,0])

    def test_cleanup_failure_prevents_success(self):
        for mode in (7,8):
            self.assertEqual(self.run_probe(mode=mode)[:8],[1,1,1,1,0,1,0,2000])

    def run_auth(self,mode=0,tick=0):
        self.c.reset(mode,0,0,tick);self.c.run_auth()
        return [self.c.state(i) for i in range(15)]

    def test_auth_uses_actual_beacon_rates_and_complete_native_hif(self):
        for mode in (0,19):
            self.assertEqual(self.run_auth(mode),[1,1,1,1,1,0,0,5000,7,1,1,1,1,1,1])
            p=C.string_at(self.c.station_request(),48)
            self.assertEqual(p[9],0x41);self.assertEqual(p[10:16],bytes([2,0,0,0,0,1]))
            self.assertEqual(p[20:26],bytes([0,3,15,0,15,0]));self.assertEqual(p[28],1)
            self.assertEqual(p[41],100);self.assertEqual(p[42],0)
            expected=bytearray(48);expected[:6]=bytes([46,0,20,0xd0,24,0x80])
            expected[11:14]=bytes([0x20,1,5]);expected[16]=0xb0
            expected[20:26]=expected[32:38]=bytes([2,0,0,0,0,1])
            expected[26:32]=bytes([2,0,0,0,0,2]);expected[38]=16;expected[42]=1
            self.assertEqual(C.string_at(self.c.tx_request(),48),expected)

    def test_auth_failure_does_not_report_success_and_releases_attempted_station(self):
        for mode in (12,13,14,15,16,17,18,20,22,23,24,25):
            s=self.run_auth(mode)
            self.assertEqual(s[:7],[1,1,1,1,0,1,0],mode)
            self.assertEqual(s[10:12],[1,1],mode)
        for mode in (10,11):
            s=self.run_auth(mode)
            self.assertEqual(s[:7],[0,0,0,0,0,1,0],mode)
            self.assertEqual(s[10:13],[0,0,0],mode)
        for mode in (21,):
            s=self.run_auth(mode)
            self.assertEqual(s[:7],[1,1,1,1,0,1,0],mode)
            self.assertEqual(s[10:13],[0,0,0],mode)
        self.assertEqual(self.run_auth(9)[:9],[0,0,0,0,0,0,1,0,0])

    def test_auth_grant_deadline_wrap_and_missing_txdone(self):
        self.assertEqual(self.run_auth(tick=0xfffffff0)[4:7],[1,0,0])
        self.assertEqual(self.run_auth(22,tick=0xfffffff0)[4:7],[0,1,0])

    def test_completed_scan_does_not_require_a_second_beacon_after_grant(self):
        self.assertEqual(self.run_auth(26)[4:7],[1,0,0])

    def test_scan_expiring_while_waiting_for_grant_never_creates_station(self):
        s=self.run_auth(27)
        self.assertEqual(s[:7],[1,1,1,1,0,1,0])
        self.assertEqual(s[10:13],[0,0,0])

    def run_assoc(self, mode=28, tick=0):
        self.c.reset(mode, 0, 0, tick); self.c.run_assoc()
        return [self.c.state(i) for i in range(15)]

    def test_assoc_requires_auth_txdone_and_response_then_state2(self):
        for mode in (28, 29):
            s = self.run_assoc(mode)
            self.assertEqual(s[:7], [1,1,1,1,1,0,0])
            self.assertEqual(s[10:13], [1,1,2])
            station = C.string_at(self.c.station_request(), 48)
            self.assertEqual(station[28], 1)
            self.assertEqual(station[16:18], b'\0\0')
            p = C.string_at(self.c.assoc_request(), self.c.assoc_size())
            n = int.from_bytes(p[:2], 'little')
            self.assertEqual(len(p), (n+3)&~3)
            self.assertEqual(p[2:6], bytes([20,0xd0,24,0x80]))
            self.assertEqual(p[11:14], bytes([0x20,2,5]))
            self.assertEqual(p[16:18], b'\0\0')
            self.assertEqual(p[44:50], b'\0\4TEST')
            self.assertEqual(p[n-22:n], bytes.fromhex('30140100000fac040100000fac040100000fac020000'))
            self.assertEqual(p[n:], bytes(len(p)-n))

    def test_assoc_does_not_succeed_on_failure_missing_wrong_peer_or_network(self):
        for mode in (30,31,32,33,34,35,36,37,38,39):
            s = self.run_assoc(mode)
            self.assertEqual(s[:7], [1,1,1,1,0,1,0], mode)
            self.assertEqual(s[10:12], [1,1], mode)

    def test_assoc_unsupported_rsn_fails_before_radio_mutation(self):
        s = self.run_assoc(40)
        self.assertEqual(s[:4], [0,0,0,0])
        self.assertEqual(s[10:13], [0,0,0])

    def test_assoc_lease_uses_wrap_safe_deadline(self):
        self.assertEqual(self.run_assoc(tick=0xfffffff0)[4:7], [1,0,0])
        self.assertEqual(self.run_assoc(36,tick=0xfffffff0)[4:7], [0,1,0])

    def test_assoc_cleanup_failure_prevents_ready_result(self):
        for mode in (7,8,20):
            s = self.run_assoc(mode)
            self.assertEqual(s[:7], [1,1,1,1,0,1,0], mode)
            self.assertEqual(s[10:13], [1,1,2], mode)

    def test_connect_uses_ap_aid_waits_for_events_inside_command_then_cleans_up(self):
        for tick in (0,0xfffffff0):
            s=self.run_assoc(50,tick)
            self.assertEqual(s[:7],[1,1,1,1,1,0,0])
            self.assertEqual(s[10:13],[2,1,2])
            self.assertEqual([self.c.join_state(i) for i in range(4)],[2,1,1,3])
            p=C.string_at(self.c.station_request(),48)
            self.assertEqual(p[16:18],b'\x07\x00')
            self.assertEqual((p[20],p[28],p[42]),(0,3,1))
            expected=bytearray(20);expected[9:14]=bytes([3,7,0,100,0])
            self.assertEqual(C.string_at(self.c.pm_request(),20),expected)
            self.assertEqual([self.c.cam_state(i) for i in range(3)],[1,1,0])
            self.assertEqual(self.c.filter_count(),1)

    def test_connect_failure_or_missing_activation_beacon_never_reports_ready(self):
        for mode in range(41,49):
            s=self.run_assoc(mode)
            self.assertEqual(s[:7],[1,1,1,1,0,1,0],mode)
            self.assertEqual(s[11],1,mode)
            self.assertEqual(self.c.join_state(2),1,mode)
            if mode in (41,42,43,44,45):self.assertEqual(self.c.join_state(1),0,mode)

    def test_cam_transfer_failure_does_not_enter_state3(self):
        s=self.run_assoc(51)
        self.assertEqual(s[:7],[1,1,1,1,0,1,0])
        self.assertEqual(s[10],1)
        self.assertEqual(self.c.join_state(1),0)
        self.assertEqual([self.c.cam_state(i) for i in range(3)],[1,0,0])

    def test_rx_filter_transfer_failure_prevents_connected_bss_and_state3(self):
        s=self.run_assoc(52)
        self.assertEqual(s[:7],[1,1,1,1,0,1,0])
        self.assertEqual(s[10],1)
        self.assertEqual(self.c.filter_count(),1)
        self.assertEqual(self.c.join_state(1),0)
        self.assertEqual(self.c.join_state(3),0)
        self.assertEqual([self.c.cam_state(i) for i in range(3)],[1,1,0])

    def test_failed_cleanup_blocks_a_second_trial_before_input_or_io(self):
        for mode in (47,48):
            self.run_assoc(mode)
            self.assertEqual(self.c.cam_state(2),1)
            before=[self.c.state(i) for i in range(15)]
            self.c.sdio_wifi_ais_connect_probe()
            after=[self.c.state(i) for i in range(15)]
            self.assertEqual(after[:6],before[:6])
            self.assertEqual(after[6],before[6]+1)
            self.assertEqual(after[8:],before[8:])

    def test_shared_cleanup_releases_owned_resources_once(self):
        self.c.reset(0,0,0,0);self.c.begin_cleanup()
        before=[self.c.state(i) for i in range(15)]
        self.assertEqual([before[i] for i in (1,3,11)],[1,1,1])
        self.assertEqual([self.c.cleanup_state(i) for i in range(3)],[0,1,0])
        self.assertEqual(self.c.repeat_cleanup(),0)
        self.assertEqual([self.c.state(i) for i in range(15)],before)

    def test_shared_uncertain_cleanup_remembers_failure_without_retry(self):
        self.c.reset(7,0,0,0);self.c.begin_cleanup()
        self.assertEqual([self.c.cleanup_state(i) for i in range(3)],[-1,1,1])
        self.assertEqual(self.c.cam_state(2),1)
        before=[self.c.state(i) for i in range(15)]
        self.assertEqual(self.c.repeat_cleanup(),-1)
        self.assertEqual([self.c.state(i) for i in range(15)],before)

    def test_foreign_connection_is_not_removed_by_stale_resource_owner(self):
        self.c.reset(0,0,0,0);self.c.foreign_cleanup()
        self.assertEqual([self.c.cleanup_state(i) for i in range(3)],[-1,1,1])
        self.assertEqual(self.c.cam_state(2),1)
        self.assertEqual([self.c.state(i) for i in (0,1,2,3,10,11,12)],[0]*7)

    def test_stale_channel_token_cannot_release_a_new_attempt(self):
        self.c.reset(0,0,0,0);self.c.foreign_token_cleanup()
        self.assertEqual([self.c.cleanup_state(i) for i in range(3)],[-1,1,1])
        self.assertEqual(self.c.cam_state(2),1)
        self.assertEqual([self.c.state(i) for i in (0,1,2,3,10,11,12)],[0]*7)

    def test_retained_join_releases_only_join_privilege_then_full_leave_once(self):
        for tick in (0,0xfffffff0):
            self.run_assoc(53,tick)
            self.assertEqual([self.c.retained_state(i) for i in range(5)],[1,0,0,0,7])
            self.assertEqual([self.c.state(i) for i in (1,3,11)],[0,1,0])
            before=[self.c.state(i) for i in range(15)]
            self.assertEqual(self.c.release_join_again(),0)
            self.assertEqual(self.c.retry_retained(),-1)
            after=[self.c.state(i) for i in range(15)]
            self.assertEqual(after[:6],before[:6]);self.assertEqual(after[8:],before[8:])
            self.assertEqual(self.c.sdio_wifi_wpa_leave(),0)
            self.assertEqual([self.c.retained_state(i) for i in range(5)],[0,0,1,0,0])
            self.assertEqual([self.c.state(i) for i in (1,3,11)],[1,1,1])
            before=[self.c.state(i) for i in range(15)]
            self.assertEqual(self.c.sdio_wifi_wpa_leave(),0)
            self.assertEqual([self.c.state(i) for i in range(15)],before)

    def test_retained_join_owner_mismatch_does_not_mutate_radio(self):
        self.run_assoc(54)
        self.assertEqual([self.c.state(i) for i in (0,1,2,3,10,11,12)],[0]*7)
        self.assertEqual(self.c.retained_state(0),0)

    def test_retained_join_abort_failure_is_not_repeated_on_leave(self):
        self.run_assoc(55)
        self.assertEqual(self.c.state(3),1)
        self.assertEqual(self.c.cam_state(2),1)
        self.assertEqual(self.c.retained_state(0),0)
        before=[self.c.state(i) for i in range(15)]
        self.assertEqual(self.c.sdio_wifi_wpa_leave(),-1)
        self.assertEqual([self.c.state(i) for i in range(15)],before)

    def test_retained_join_rejects_missing_supplicant_assoc_ie(self):
        self.run_assoc(56)
        self.assertEqual(self.c.state(12),1)
        self.assertEqual(self.c.retained_state(0),0)
        self.assertEqual([self.c.state(i) for i in (1,3,11)],[1,1,1])

    def test_first_live_beacon_during_bss_credit_wait_is_retained(self):
        self.run_assoc(57)
        self.assertEqual(self.c.retained_state(0),1)
        self.assertEqual(self.c.join_state(1),1)
        self.assertEqual(self.c.join_state(3),3)
        self.assertEqual(self.c.sdio_wifi_wpa_leave(),0)

    def test_live_beacon_before_activation_during_station_wait_is_retained(self):
        self.run_assoc(58)
        self.assertEqual(self.c.retained_state(0),1)
        self.assertEqual(self.c.join_state(1),1)
        self.assertEqual(self.c.sdio_wifi_wpa_leave(),0)

    def test_beacon_alone_wrong_channel_or_failed_bss_cannot_connect(self):
        for mode in (59,60,61):
            with self.subTest(mode=mode):
                self.run_assoc(mode)
                self.assertEqual(self.c.retained_state(0),0)
                self.assertEqual(self.c.join_state(1),0)
                if mode==61:self.assertEqual(self.c.state(10),1)

if __name__=='__main__':
    unittest.main()
