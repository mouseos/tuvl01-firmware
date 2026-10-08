"""Bounded scan descriptors, ownership, expiry and failed-scan isolation."""
import ctypes as C
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class Cache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'cache.c').write_text(r'''
#include "wifi_scan_cache.h"
static struct wifi_scan_cache cache;
static struct wifi_ais_beacon output;
static uint8_t rcpi;
void begin(void){wifi_scan_cache_begin(&cache);}
void finish(unsigned ok){wifi_scan_cache_finish(&cache,ok);}
void observe(unsigned ap,unsigned ch,unsigned rx,unsigned profile,unsigned tick,unsigned value){
 struct wifi_ais_beacon b={0};b.ap[0]=2;b.ap[5]=ap;
 b.channel=ch;b.rx_channel=rx;b.ssid[0]=value;b.ssid_length=1;
 b.rsn[0]=value;b.rsn_length=1;
 wifi_scan_cache_observe(&cache,&b,tick,profile,(uint8_t)value);
 b.ssid[0]=b.rsn[0]=0;
}
int select(unsigned ap,unsigned ch,unsigned profile,unsigned now,unsigned age){
 uint8_t mac[6]={2,0,0,0,0,ap};
 return wifi_scan_cache_select(&cache,now,age,profile,mac,ch,&output,&rcpi);
}
unsigned value(unsigned i){unsigned a[]={cache.count,output.ssid[0],output.rsn[0],rcpi};return a[i];}
''')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',
                        '-I'+str(ROOT/'include'),str(p/'cache.c'),
                        str(ROOT/'src/wifi_scan_cache.c'),'-o',str(p/'cache.so')],check=True)
        cls.c=C.CDLL(str(p/'cache.so'))
        cls.c.observe.argtypes=[C.c_uint]*6;cls.c.select.argtypes=[C.c_uint]*5
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.c.begin()
    def test_only_successful_complete_scan_is_usable(self):
        self.c.observe(1,11,11,0,100,77)
        self.assertEqual(self.c.select(1,11,0,100,5000),0)
        self.c.finish(0)
        self.assertEqual(self.c.select(1,11,0,100,5000),0)
        self.c.begin();self.c.observe(1,11,11,0,100,77);self.c.finish(1)
        self.assertEqual(self.c.select(1,11,0,100,5000),1)
        self.c.begin()
        self.assertEqual(self.c.select(1,11,0,100,5000),0)
    def test_exact_ap_channel_profile_and_rx_channel(self):
        self.c.observe(1,11,12,0,100,77);self.c.finish(1)
        self.assertEqual(self.c.select(1,11,0,100,5000),0)
        self.c.begin();self.c.observe(1,11,11,0,100,77);self.c.finish(1)
        for args in ((2,11,0,100,5000),(1,10,0,100,5000),(1,11,1,100,5000)):
            self.assertEqual(self.c.select(*args),0)
    def test_age_boundary_wrap_and_future_timestamp(self):
        self.c.observe(1,11,11,0,0xfffffff0,77);self.c.finish(1)
        for age,ok in ((5000,1),(5001,0)):
            self.assertEqual(self.c.select(1,11,0,(0xfffffff0+age)&0xffffffff,5000),ok)
        self.assertEqual(self.c.select(1,11,0,0xffffffef,5000),0)
        self.assertEqual(self.c.select(1,11,0,0xfffffff0,0),0)
        self.assertEqual(self.c.select(1,11,0,0xfffffff0,0x80000000),0)
    def test_owned_copy_and_duplicate_update(self):
        self.c.observe(1,11,11,0,100,77);self.c.observe(1,11,11,0,101,88);self.c.finish(1)
        self.assertEqual(self.c.value(0),1)
        self.assertEqual(self.c.select(1,11,0,101,5000),1)
        self.assertEqual([self.c.value(i) for i in (1,2,3)],[88,88,88])
    def test_capacity_and_eviction(self):
        for ap in range(1,20):self.c.observe(ap,11,11,0,ap,77)
        self.c.finish(1);self.assertEqual(self.c.value(0),16)
        for ap in (1,2,3):self.assertEqual(self.c.select(ap,11,0,20,5000),0)
        for ap in range(4,20):self.assertEqual(self.c.select(ap,11,0,20,5000),1)
    def test_observations_after_finish_do_not_change_snapshot(self):
        self.c.observe(1,11,11,0,100,77);self.c.finish(1)
        self.c.observe(1,11,11,0,101,88)
        self.assertEqual(self.c.select(1,11,0,101,5000),1)
        self.assertEqual(self.c.value(3),77)
