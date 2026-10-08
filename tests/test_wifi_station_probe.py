"""Execute actual two-phase probe with absent features, bad events and timeout."""
import ctypes,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Probe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=(ROOT/'src/sdio.c').read_text();start=source.index('void sdio_wifi_station_stats(void){')
        body=source[start:source.index('\nvoid sdio_wifi_nic_stats',start)]
        harness=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "wifi_fw_query.h"
typedef uint32_t TickType_t;
static unsigned wifi_ap_active,wifi_peer_active,scenario,calls,events,ticks;
static uint8_t wifi_peer[6]={2,3,4,5,6,7},wifi_sequence;
static unsigned cids[2],lengths[2],sets[2];
static uint8_t commands[2][272];
static char output[1024];
static void uart_puts(const char *s){unsigned n=0;while(output[n])n++;while(*s && n<1023)output[n++]=*s++;output[n]=0;}
static void field(const char *s,unsigned n){char v[128];snprintf(v,sizeof v,"%s%08x",s,n);uart_puts(v);}
static TickType_t xTaskGetTickCount(void){ticks+=1000;return ticks;}
static void vTaskDelay(unsigned n){(void)n;}
static int control_send(unsigned cid,unsigned set,uint8_t *p,unsigned length){
 if(calls>=2)return -1;
 cids[calls]=cid;lengths[calls]=length;sets[calls]=set;memcpy(commands[calls],p,length);
 calls++;wifi_sequence++;return scenario==9?-1:0;
}
static int event_read(uint8_t *p,unsigned capacity,unsigned *length){
 (void)capacity;events++;
 if(scenario==8)return -1;
 if((calls==1 && scenario==3) || (calls==2 && scenario==6))return 0;
 memset(p,0,128);p[2]=1;p[5]=wifi_sequence;
 if(calls==1){
  *length=16;p[0]=16;p[4]=0x1f;p[10]=0x24;p[11]=0xa0;
  p[12]=scenario==0?0:1;
  if(scenario==2){p[4]=1;p[8]=0xc6;p[9]=1;}
  if(scenario==5)p[8]=1;
  if(scenario==7 && events==1)p[5]--;
 }else{
  *length=116;p[0]=116;p[4]=0x29;
  if(scenario==4){p[4]=1;p[8]=0x85;p[9]=2;}
  if(scenario==10){*length=129;p[0]=129;}
 }
 return 1;
}
void reset(unsigned value,unsigned active){
 scenario=value;wifi_ap_active=wifi_peer_active=active;calls=events=ticks=0;wifi_sequence=32;
 memset(output,0,sizeof output);memset(commands,0,sizeof commands);
}
const char *log_output(void){return output;}
unsigned state(unsigned i){return i==0?calls:i==1?events:ticks;}
unsigned command(unsigned i,unsigned field){return field==0?cids[i]:field==1?sets[i]:lengths[i];}
unsigned byte(unsigned i,unsigned offset){return commands[i][offset];}
'''
        cls.tmp=tempfile.TemporaryDirectory();path=pathlib.Path(cls.tmp.name)
        (path/'probe.c').write_text(harness+body)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
                        str(path/'probe.c'),str(ROOT/'src/wifi_fw_query.c'),'-o',str(path/'probe.so')],check=True)
        cls.lib=ctypes.CDLL(str(path/'probe.so'));cls.lib.log_output.restype=ctypes.c_char_p
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_probe(self,scenario,active=1):
        self.lib.reset(scenario,active);self.lib.sdio_wifi_station_stats()
        return self.lib.log_output().decode()
    def test_peer_and_feature_gates_prevent_station_command(self):
        self.assertIn('status=refused-peer',self.run_probe(1,0));self.assertEqual(self.lib.state(0),0)
        self.assertIn('status=unsupported',self.run_probe(0));self.assertEqual(self.lib.state(0),1)
        self.assertEqual([self.lib.command(0,i) for i in range(3)],[0xc6,0,272])
    def test_supported_feature_reads_raw_and_never_sets_read_clear(self):
        for scenario in (1,7):
            self.assertIn('status=read-raw',self.run_probe(scenario));self.assertEqual(self.lib.state(0),2)
            self.assertEqual([self.lib.command(1,i) for i in range(3)],[0x85,0,36])
            self.assertEqual(bytes(self.lib.byte(1,n) for n in range(36)),b'\0'*12+bytes((2,3,4,5,6,7))+b'\0'*18)
    def test_rejection_malformed_transport_error_and_layout_are_not_success(self):
        for scenario,status in ((2,'rejected'),(4,'rejected'),(5,'malformed'),(8,'failed'),(9,'failed'),(10,'unsupported-layout')):
            self.assertIn('status='+status,self.run_probe(scenario))
    def test_both_response_phases_have_finite_timeouts(self):
        for scenario,status in ((3,'timeout-compile'),(6,'timeout-station')):
            self.assertIn('status='+status,self.run_probe(scenario));self.assertLessEqual(self.lib.state(1),6)
if __name__=='__main__':unittest.main()
