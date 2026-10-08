/* Synthetic UART input and selected beacon; no board peripheral access. */
#include "wifi_wpa_console.h"
#include "wifi_ais_beacon.h"
#include "entropy.h"
#include "eapol_queue.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Include production console to exercise its internal driver callbacks. */
#include "../src/wifi_wpa_console.c"
static int serve;
static char log_text[4096];static size_t log_n;
static int radio_ready=1,invalid_beacon;
void uart_puts(const char *s){if(serve){fputs(s,stdout);fflush(stdout);return;}size_t n=strlen(s);assert(log_n+n<sizeof log_text);memcpy(log_text+log_n,s,n+1);log_n+=n;}
_Noreturn void fault(void){_Exit(99);}
int sdio_wifi_wpa_eapol_submit(unsigned port,unsigned tc,const unsigned char *p,unsigned n)
{(void)port;(void)tc;(void)p;(void)n;assert(!"Provisioning must not submit radio EAPOL");return -1;}
static int allow_keys,key_fail,leave_fail;static unsigned adds,removes;
int sdio_wifi_wpa_key_submit(const unsigned char *p,unsigned n)
{
    assert(allow_keys && n==64);
    if(p[0])adds++;else{
        removes++;assert(owner.session || !owner.associated);
        for(unsigned i=16;i<64;i++)assert(!p[i]);
        assert(p[1]==0 && p[11]==0 && p[13]==0);
    }
    return key_fail?-1:0;
}
static int join_result=-1;static unsigned join_calls,leave_calls;
int sdio_wifi_wpa_join(const unsigned char *p)
{
    assert(p && p[0]==6 && p[1]==2 && p[6]==2);join_calls++;
    if(!join_result){
        /* Arrives inside the SDIO join wait, before associated notification.
         * Deliberately short EAPOL-Key: parser must reject after deferred RX. */
        unsigned char rx[30]={30,0,0,0};rx[12]=2;rx[17]=1;rx[18]=2;rx[23]=2;
        rx[24]=0x88;rx[25]=0x8e;rx[26]=2;rx[27]=3;
        wifi_wpa_radio_rx(rx,sizeof rx);
    }
    return join_result;
}
int sdio_wifi_wpa_leave(void){
    for(unsigned i=0;i<5;i++)assert(!key_ledger.slot[i].pending);
    leave_calls++;return leave_fail?-1:0;
}
unsigned sdio_wifi_milliseconds(void){return 7;}
int sdio_wifi_wpa_select(unsigned channel,const unsigned char *ap,
    unsigned char *own,struct wifi_ais_beacon *b)
{
    static const unsigned char rsn[]={48,20,1,0,0,15,172,4,1,0,0,15,172,4,1,0,0,15,172,2,0,0};
    if(!radio_ready || channel!=6 || ap[0]!=2 || ap[5]!=2)return -1;
    memset(b,0,sizeof *b);memcpy(b->ap,ap,6);memcpy(b->ssid,"test",4);
    b->ssid_length=4;b->channel=b->rx_channel=6;
    memcpy(b->rsn,rsn,sizeof rsn);b->rsn_length=invalid_beacon?258:sizeof rsn;
    memset(own,0,6);own[0]=2;own[5]=1;return 0;
}
static void reset_log(void){log_n=0;log_text[0]=0;}
static void sync_uart(unsigned now)
{
    const char *s="TUVL-WPA-RESYNC\n";
    while(*s)assert(wifi_wpa_uart_intercept((unsigned char)*s++,now));
    assert(strstr(log_text,"WPA UART resynchronized\n"));
    assert(!wifi_wpa_uart_intercept(-1,now));
}
static void target_input(unsigned now)
{
    const unsigned char p[]={6,2,0,0,0,0,2};
    wifi_wpa_uart_begin(now);assert(strstr(log_text,"WPA target bytes=7 version=1\n"));
    for(unsigned i=0;i<7;i++)assert(wifi_wpa_uart_intercept(p[i],now));
}
static void packet(unsigned char *p)
{
    memset(p,0,148);memcpy(p,"TPMK",4);p[4]=1;p[5]=6;p[6]=4;p[8]=2;p[13]=2;memcpy(p+16,"test",4);
    /* Includes legacy command/control values; receiver must intercept all. */
    for(unsigned i=0;i<32;i++)p[48+i]=(unsigned char)(i+96);
    for(unsigned i=0;i<64;i++)p[80+i]=(unsigned char)(i+33);
    unsigned c=0xffffffffu;
    for(unsigned j=0;j<144;j++){c^=p[j];for(unsigned i=0;i<8;i++)c=(c>>1)^((0u-(c&1u))&0xedb88320u);}
    c=~c;for(unsigned i=0;i<4;i++)p[144+i]=(unsigned char)(c>>(8*i));
}
static void queue_test(void)
{
    static struct tuvl_eapol_queue q;
    unsigned char p[TUVL_EAPOL_RX_MAX];memset(p,0x5a,sizeof p);
    for(unsigned i=0;i<4;i++){p[0]=(unsigned char)i;assert(!tuvl_eapol_queue_push(&q,p,sizeof p));}
    memset(p,0,sizeof p);
    for(unsigned i=0;i<4;i++){
        size_t n;const unsigned char *front=tuvl_eapol_queue_front(&q,&n);
        assert(front && n==sizeof p && front[0]==i && front[n-1]==0x5a);
        unsigned slot=q.head;tuvl_eapol_queue_pop(&q);
        for(size_t j=0;j<sizeof p;j++)assert(!q.packet[slot][j]);
    }
    for(unsigned i=0;i<20;i++){assert(!tuvl_eapol_queue_push(&q,p,30));tuvl_eapol_queue_pop(&q);}
    for(unsigned i=0;i<4;i++)assert(!tuvl_eapol_queue_push(&q,p,30));
    assert(tuvl_eapol_queue_push(&q,p,30)==-1 && q.failed);
    size_t n=1;assert(!tuvl_eapol_queue_front(&q,&n) && !n);
    tuvl_eapol_queue_clear(&q);
    const unsigned char *raw=(const unsigned char *)&q;
    for(size_t i=0;i<sizeof q;i++)assert(!raw[i]);
    assert(tuvl_eapol_queue_push(&q,p,sizeof p+1)==-1 && q.failed);
    tuvl_eapol_queue_clear(&q);assert(tuvl_eapol_queue_push(&q,NULL,30)==-1);
    tuvl_eapol_queue_clear(&q);
}
static void cleanup_test(unsigned mode)
{
    unsigned char p[148];packet(p);target_input(0);
    for(unsigned i=0;i<148;i++)assert(wifi_wpa_uart_intercept(p[i],1));
    sync_uart(2);join_result=0;wifi_wpa_uart_join();assert(owner.associated);
    allow_keys=1;unsigned char key[16];memset(key,0x6a,sizeof key);
    static const unsigned char group[6]={255,255,255,255,255,255};
    if(mode!=0){
        if(mode==2)key_fail=1;
        int result=radio_key(NULL,-1,WPA_ALG_CCMP,owner.target.ap,0,1,NULL,0,key,16,KEY_FLAG_PAIRWISE_RX_TX);
        assert(result==(mode==2?-1:0));
        if(mode!=2)assert(!radio_key(NULL,-1,WPA_ALG_CCMP,group,2,0,NULL,0,key,16,KEY_FLAG_GROUP_RX));
    }
    if(mode==1)key_fail=1;
    if(mode==3)leave_fail=1;
    if(mode==4){tuvl_rsn_owner_close(&owner);assert(!owner.session);}
    unsigned before=leave_calls;wifi_wpa_uart_close();
    assert(!owner.session && !tuvl_rsn_entropy_remaining());
    if(mode==1 || mode==2){
        assert(key_ledger.failed && cleanup_unresolved==1 && leave_calls==before);
        unsigned n=adds+removes;wifi_wpa_uart_close();assert(adds+removes==n && leave_calls==before);
    }else{
        assert(removes==(mode?2:0) && leave_calls==before+1);
        if(mode==3){assert(cleanup_unresolved==2);wifi_wpa_uart_close();assert(leave_calls==before+1);}
        else assert(!cleanup_unresolved);
    }
    if(mode==1 || mode==2 || mode==3){
        reset_log();wifi_wpa_uart_begin(20);assert(strstr(log_text,"WPA cleanup refused-unresolved"));
        wifi_wpa_uart_join();assert(strstr(log_text,"WPA association refused"));
    }
    puts("PASS cleanup: software erase, ordered deletion transfer and failure latch; no hardware erasure proof");
}
int main(int argc,char **argv)
{
    if(argc==3 && !strcmp(argv[1],"--cleanup")){cleanup_test((unsigned)atoi(argv[2]));return 0;}
    if(argc==2 && !strcmp(argv[1],"--serve")){
        int c;serve=1;
        while((c=getchar())!=EOF){
            if(wifi_wpa_uart_intercept(c,0))continue;
            if(c=='i'){uart_puts("UART application\n");wifi_wpa_uart_info();}
            else if(c==2)wifi_wpa_uart_begin(0);
            else if(c==3)wifi_wpa_uart_close();
            else if(c==4)wifi_wpa_uart_join();
            else uart_puts("Unexpected legacy command\n");
        }
        wifi_wpa_uart_close();return 0;
    }
    queue_test();
    unsigned char p[148];packet(p);
    target_input(0);assert(strstr(log_text,"WPA credentials bytes=148 version=1\n"));
    for(unsigned i=0;i<148;i++)assert(wifi_wpa_uart_intercept(p[i],1));
    assert(strstr(log_text,"WPA provisioning accepted; association=unimplemented\n"));
    assert(tuvl_rsn_entropy_remaining()==64);
    size_t before=log_n;
    for(unsigned i=0;i<148;i++)assert(wifi_wpa_uart_intercept(p[i],2));
    const char *tail=log_text+before;
    const char *probe="WPA waiting-for-resync version=1\n";
    while(*tail){assert(!strncmp(tail,probe,strlen(probe)));tail+=strlen(probe);}
    sync_uart(3);
    assert(!wifi_wpa_uart_intercept('q',4));
    wifi_wpa_uart_begin(4);assert(strstr(log_text,"WPA provisioning refused-active\n"));
    unsigned leave_before=leave_calls;
    wifi_wpa_uart_join();assert(join_calls==1 && leave_calls==leave_before+1);
    assert(strstr(log_text,"WPA association failed\n") && !tuvl_rsn_entropy_remaining());
    wifi_wpa_uart_close();assert(!tuvl_rsn_entropy_remaining());
    reset_log();target_input(5);
    for(unsigned i=0;i<148;i++)assert(wifi_wpa_uart_intercept(p[i],6));
    sync_uart(6);join_result=0;wifi_wpa_uart_join();
    assert(strstr(log_text,"WPA association ready; protection=unimplemented\n"));
    assert(wifi_wpa_uart_intercept('h',7));
    assert(strstr(log_text,"WPA command refused-active\n"));
    assert(!wifi_wpa_uart_intercept('i',7));
    assert(!wifi_wpa_uart_intercept(3,7));
    wifi_wpa_uart_close();assert(!tuvl_rsn_entropy_remaining());join_result=-1;
    reset_log();target_input(10);p[147]^=1;
    for(unsigned i=0;i<148;i++)assert(wifi_wpa_uart_intercept(p[i],11));
    assert(strstr(log_text,"WPA provisioning rejected\n") && !tuvl_rsn_entropy_remaining());sync_uart(12);p[147]^=1;
    reset_log();target_input(20);
    for(unsigned i=0;i<80;i++)assert(wifi_wpa_uart_intercept(p[i],21));
    assert(wifi_wpa_uart_intercept(-1,2020));
    assert(strstr(log_text,"WPA provisioning input-timeout\n"));
    before=log_n;for(unsigned i=80;i<148;i++)assert(wifi_wpa_uart_intercept(p[i],2021));
    assert(log_n==before && !tuvl_rsn_entropy_remaining());sync_uart(2022);
    reset_log();wifi_wpa_uart_begin(0xfffffff0u);
    assert(wifi_wpa_uart_intercept(-1,0xfffffff0u+3000u));
    assert(strstr(log_text,"WPA provisioning target-timeout\n"));sync_uart(3010);
    reset_log();radio_ready=0;target_input(4000);
    assert(strstr(log_text,"WPA provisioning target-refused\n"));sync_uart(4001);radio_ready=1;
    reset_log();invalid_beacon=1;target_input(5000);
    assert(strstr(log_text,"WPA provisioning target-refused\n"));sync_uart(5001);invalid_beacon=0;
    wifi_wpa_uart_close();assert(!tuvl_rsn_entropy_remaining());
    puts("PASS firmware WPA console: actual RSN open, binary interception, timeout/CRC/radio gates, resync and close; no hardware UART/WPA2");
    return 0;
}
