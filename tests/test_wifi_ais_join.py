"""Compile the production join collector; exercise command-wait RX ordering."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Join(unittest.TestCase):
    def test_negotiated_settings_activation_and_post_activation_tim(self):
        source = r'''
#include <assert.h>
#include <string.h>
#include "wifi_ais_join.h"
int main(void){
 const unsigned char own[]={2,0,0,0,0,1},ap[]={2,0,0,0,0,2};
 struct wifi_ais_beacon b={0};memcpy(b.ap,ap,6);memcpy(b.ssid,"test",4);
 b.ssid_length=4;b.channel=b.rx_channel=6;b.interval=0x123;
 b.short_preamble=b.short_slot=1;b.erp_protection=1;
 /* Cached TIM must not be accepted for the post-activation PM gate. */
 b.tim_present=1;b.dtim_period=7;
 struct wifi_ais_assoc a={0};a.aid=0x321;a.capability=0x411;
 a.operational=0x3fcf;a.basic=0x054f;
 struct wifi_ais_join j;unsigned char out[88];
 assert(wifi_ais_join_prepare(&j,own,&b,&a,0,123));
 assert(wifi_ais_join_bss(&j,out,88)==88);
 assert(out[9]==0 && out[56]==0 && out[61]==6 && out[85]==0 && out[86]==1);
 assert(out[52]==0xcf && out[53]==0x3f && out[54]==0x4f && out[55]==5);
 assert(wifi_ais_join_station(&j,out,88)==48);
 assert(out[16]==0x21 && out[17]==3 && out[28]==3 && out[42]==1 && out[20]==0);
 memset(out,0xa5,sizeof out);assert(!wifi_ais_join_pm(&j,out,88));
 assert(out[0]==0xa5);wifi_ais_join_watch(&j);assert(!wifi_ais_join_pm(&j,out,88));
 unsigned char beacon[128]={0};unsigned char *p=beacon+12;
 beacon[2]=3;beacon[5]=1;beacon[10]=6;p[0]=0x80;
 memset(p+4,255,6);memcpy(p+10,ap,6);memcpy(p+16,ap,6);
 p[32]=0x23;p[33]=1;p[34]=0x11;p[35]=4;
 unsigned char ies[]={0,4,'t','e','s','t',1,4,0x82,0x84,0x8b,0x96,3,1,6,5,4,0,3,0,0};
 memcpy(p+36,ies,sizeof ies);unsigned n=48+sizeof ies;beacon[0]=n;
 /* Cached TIM and pre-watch frames cannot establish the live gate. */
 j.watch=0;wifi_ais_join_observe(&j,beacon,n);assert(!j.beacon_seen);
 wifi_ais_join_watch(&j);
 wifi_ais_join_observe(&j,beacon,n);assert(j.beacon_seen && !j.activated);
 assert(!wifi_ais_join_pm(&j,out,88));
 unsigned char activate[20]={20,0,1,0,0x13,0,0,0};
 memcpy(activate+8,ap,6);activate[17]=1;
 /* Wrong network, station, peer, or AP role never opens the gate. */
 for(unsigned k=0;k<4;k++){
  unsigned char bad[20];memcpy(bad,activate,20);
  if(k==0)bad[15]=1;if(k==1)bad[14]=1;if(k==2)bad[8]^=2;if(k==3)bad[17]=0;
  wifi_ais_join_observe(&j,bad,20);assert(!j.activated);
 }
 wifi_ais_join_observe(&j,activate,20);assert(j.activated && j.beacon_seen);
 assert(wifi_ais_join_pm(&j,out,88)==20);
 /* Exercise the opposite order independently. */
 wifi_ais_join_watch(&j);wifi_ais_join_observe(&j,activate,20);
 assert(j.activated && !j.beacon_seen);
 memset(out,0xa5,sizeof out);assert(!wifi_ais_join_pm(&j,out,88));
 for(unsigned k=0;k<5;k++){
  unsigned char bad[128];memcpy(bad,beacon,n);
  if(k==0)bad[10]=11;if(k==1)bad[5]=3;if(k==2)bad[7]=0x80;
  if(k==3)bad[12+38]='X';if(k==4)bad[12+36+sizeof ies-3]=0;
  wifi_ais_join_observe(&j,bad,n);assert(!j.beacon_seen);
 }
 wifi_ais_join_observe(&j,beacon,n);assert(j.beacon_seen);
 assert(wifi_ais_join_pm(&j,out,19)==0 && out[0]==0xa5);
 assert(wifi_ais_join_pm(&j,out,88)==20);
 unsigned char expected[20]={0};expected[9]=3;expected[10]=0x21;
 expected[11]=3;expected[12]=0x23;expected[13]=1;assert(!memcmp(out,expected,20));
 /* Borrowed association response storage is not retained. */
 a.aid=1;a.operational=15;assert(j.aid==0x321 && j.operational==0x3fcf);
 j.watch=0;memset(out,0xa5,88);assert(!wifi_ais_join_pm(&j,out,88));
 a.status=13;assert(!wifi_ais_join_prepare(&j,own,&b,&a,0,123) && !j.aid);
 a.status=0;a.aid=0;assert(!wifi_ais_join_prepare(&j,own,&b,&a,0,123));
 a.aid=1;b.rx_channel=11;assert(!wifi_ais_join_prepare(&j,own,&b,&a,0,123));
 return 0;
}
'''
        # Avoid misleading indentation in compact fixture source.
        source = source.replace(';if(', ';\n if(')
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp)
            (p/'join.c').write_text(source)
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-I'+str(ROOT/'include'),
                            str(p/'join.c'), *[str(ROOT/'src'/name) for name in
                            ('wifi_ais_join.c', 'wifi_ais_bss.c', 'wifi_station.c',
                             'wifi_ais_beacon.c', 'wifi_rates.c')], '-o', str(p/'join')], check=True)
            subprocess.run([str(p/'join')], check=True)


if __name__ == '__main__':
    unittest.main()
