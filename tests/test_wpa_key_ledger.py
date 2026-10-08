"""Actual key metadata ledger and wire serializer; mocked transfer, no radio."""
import pathlib,subprocess,tempfile,ctypes,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class KeyLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)
        (p/'test.c').write_text(r'''#include "key-ledger.h"
#include "mt5931-key.h"
#include <string.h>
#include <assert.h>
static struct tuvl_key_ledger l;static unsigned calls,fail_at,reentrant;
static int send(void *ctx,const uint8_t *p,size_t n){
 (void)ctx;assert(n==64);calls++;
 if(reentrant)assert(tuvl_key_ledger_close(&l,send,0)==-1);
 if(!p[0])for(unsigned i=16;i<64;i++)assert(!p[i]);
 return calls==fail_at?-1:0;
}
int run(unsigned mode){
 memset(&l,0,sizeof l);calls=fail_at=reentrant=0;
 uint8_t key[16],body[64],copy[64];memset(key,0x6a,sizeof key);
 static const uint8_t ap[6]={2,0,0,0,0,2},group[6]={255,255,255,255,255,255};
 struct tuvl_mt5931_key req={1,1,1,0,ap,key,16,0,0};
 assert(tuvl_mt5931_key_body(body,64,&req)==64);memcpy(copy,body,64);
 if(mode==7){assert(!tuvl_key_ledger_close(&l,send,0));assert(!tuvl_key_ledger_close(&l,send,0) && !calls);return 1;}
 if(mode==0){
  for(unsigned i=0;i<64;i++){
   memset(&l,0,sizeof l);memcpy(body,copy,64);body[i]^=128;unsigned before=calls;
   int result=tuvl_key_ledger_submit(&l,send,0,body,64);
   if(i>=16 && i<32)assert(!result && calls==before+1);
   else if(i>=4 && i<10)assert(result==0 && calls==before+1);
   else assert(result==-1 && calls==before);
  }
  return 1;
 }
 if(mode==1)fail_at=1;
 if(mode==4)reentrant=1;
 int result=tuvl_key_ledger_submit(&l,send,0,body,64);
 if(mode==1){assert(result==-1 && l.failed && l.slot[0].pending);assert(tuvl_key_ledger_close(&l,send,0)==-1 && calls==1);return 1;}
 assert(!result && l.slot[0].pending);
 if(mode==5){body[9]^=1;assert(tuvl_key_ledger_submit(&l,send,0,body,64)==-1 && calls==1);assert(l.slot[0].peer[5]==2);assert(!tuvl_key_ledger_close(&l,send,0) && calls==2);return 1;}
 if(mode==6){
  req.pairwise=0;req.transmit=0;req.peer=group;
  for(unsigned i=0;i<4;i++){req.index=i;assert(tuvl_mt5931_key_body(body,64,&req)==64);assert(!tuvl_key_ledger_submit(&l,send,0,body,64));}
  assert(calls==5);assert(!tuvl_key_ledger_close(&l,send,0) && calls==10);return 1;
 }
 /* No opaque key material is retained in the metadata ledger. */
 const uint8_t *raw=(const uint8_t *)&l;for(unsigned i=0;i<sizeof l;i++)assert(raw[i]!=0x6a);
 req.pairwise=0;req.transmit=0;req.peer=group;req.index=3;
 assert(tuvl_mt5931_key_body(body,64,&req)==64);assert(!tuvl_key_ledger_submit(&l,send,0,body,64));
 if(mode==2)fail_at=calls+2; /* Pairwise deleted, then group delete uncertain. */
 result=tuvl_key_ledger_close(&l,send,0);
 if(mode==2){assert(result==-1 && l.failed && !l.slot[0].pending && l.slot[4].pending);unsigned n=calls;assert(tuvl_key_ledger_close(&l,send,0)==-1 && calls==n);}
 else{assert(!result && calls==4);assert(!tuvl_key_ledger_close(&l,send,0) && calls==4);}
 return 1;
}
''')
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'rtos/wpa/port'),str(p/'test.c'),
            str(ROOT/'rtos/wpa/port/key-ledger.c'),str(ROOT/'rtos/wpa/port/mt5931-key.c'),
            '-o',str(p/'test.so')],check=True)
        cls.lib=ctypes.CDLL(str(p/'test.so'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_invalid_wire_fields_never_submit(self):self.assertEqual(self.lib.run(0),1)
    def test_failed_add_preserves_metadata_and_never_retries(self):self.assertEqual(self.lib.run(1),1)
    def test_partial_delete_failure_preserves_only_uncertain_slots(self):self.assertEqual(self.lib.run(2),1)
    def test_successful_close_is_idempotent_and_retains_no_key(self):self.assertEqual(self.lib.run(3),1)
    def test_reentrant_cleanup_cannot_issue_commands(self):self.assertEqual(self.lib.run(4),1)
    def test_existing_slot_cannot_change_peer(self):self.assertEqual(self.lib.run(5),1)
    def test_all_pairwise_and_group_slots_removed(self):self.assertEqual(self.lib.run(6),1)
    def test_empty_close_never_issues_commands(self):self.assertEqual(self.lib.run(7),1)
