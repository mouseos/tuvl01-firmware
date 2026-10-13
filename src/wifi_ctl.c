/* SPDX-License-Identifier: MIT. Wi-Fi control service for any client. */
#include "wifi_ctl.h"
#include "tuner_ts.h"
#include "tuner_uhf.h"
enum {OP_HELLO=1,OP_START=2,OP_STOP=3,OP_STATUS=4,OP_KEEPALIVE=5,OP_TUNE=6};
enum {ST_OK=0,ST_BAD=1,ST_UNSUPPORTED=2};
enum {TUNE_NONE=0,TUNE_BUSY=1,TUNE_DONE=2,TUNE_FAILED=3};
static volatile int pending=-1;
static volatile unsigned owned,activity,controlled;
static volatile unsigned tune_state,tune_pending,tune_channel,tune_partial; /* requested */
static volatile unsigned cur_channel,cur_partial,lock=255;                   /* last tuned */
static unsigned seen_activity,last_change;
static unsigned state(void){return tuner_ts_stream_active()?1:pending=='B'?2:0;}
unsigned wifi_ctl_service(unsigned port,const uint8_t *body,unsigned n,uint8_t *r,unsigned cap){
    ++activity;
    if(port!=WIFI_CTL_PORT)return 0;
    controlled=1;
    if(n<8 || cap<24 || body[0]!='T' || body[1]!='C' || body[2]!='T' || body[3]!='1')return 0;
    unsigned op=body[4],status=ST_OK,len=8;
    r[0]='T';r[1]='C';r[2]='T';r[3]='1';r[5]=0;r[6]=body[6];r[7]=body[7];
    if(op==OP_HELLO){
        r[8]=WIFI_CTL_VERSION;r[9]=WIFI_CTL_REVISION>>8;r[10]=WIFI_CTL_REVISION;
        r[11]=0;r[12]=0;r[13]=0;r[14]=WIFI_CTL_CAP_STREAM|WIFI_CTL_CAP_TUNE;
        r[15]=4202>>8;r[16]=4202&255;r[17]=state();
        r[18]=TUNER_UHF_FIRST;r[19]=TUNER_UHF_LAST;len=20;
    }else if(op==OP_START){
        if(!tuner_ts_stream_active() && pending!='B'){pending='B';}
        owned=1;r[8]=state();len=9;
    }else if(op==OP_STOP){
        owned=0;if(tuner_ts_stream_active())pending='E';else if(pending=='B')pending=-1;
        r[8]=state();len=9;
    }else if(op==OP_STATUS){
        r[8]=state();r[9]=cur_channel>>8;r[10]=cur_channel;r[11]=cur_partial;
        r[12]=tune_state;r[13]=lock;len=14;
    }else if(op==OP_KEEPALIVE){
        r[8]=state();len=9;
    }else if(op==OP_TUNE){
        unsigned channel=n>=10?body[8]:0,mode=n>=10?body[9]:2;
        if(channel<TUNER_UHF_FIRST || channel>TUNER_UHF_LAST || mode>1)status=ST_BAD;
        else{
            tune_channel=channel;tune_partial=mode;tune_pending=1;tune_state=TUNE_BUSY;
            if(pending=='B')pending=-1;  /* a queued start would race the retune */
            r[8]=tune_state;len=9;
        }
    }else status=ST_UNSUPPORTED;
    r[4]=op|0x80;r[5]=status;
    return len;
}
int wifi_ctl_take_tune(unsigned *channel,unsigned *partial){
    if(!tune_pending)return 0;
    tune_pending=0;*channel=tune_channel;*partial=tune_partial;return 1;
}
void wifi_ctl_tune_done(int ok){
    if(ok){cur_channel=tune_channel;cur_partial=tune_partial;lock=255;}
    /* A newer TUNE may have arrived while this one ran: keep it busy. */
    tune_state=tune_pending?TUNE_BUSY:ok?TUNE_DONE:TUNE_FAILED;
}
void wifi_ctl_set_lock(unsigned value){lock=value;}
int wifi_ctl_client_seen(void){return controlled;}
int wifi_ctl_poll(unsigned now,unsigned timeout){
    int c=pending;
    if(c>=0){pending=-1;return c;}
    unsigned a=activity;
    if(a!=seen_activity){seen_activity=a;last_change=now;}
    if(owned){
        if(!tuner_ts_stream_active()){
            /* Give START time to take effect before concluding it never ran. */
            if((unsigned)(now-last_change)>timeout)owned=0;
        }else if((unsigned)(now-last_change)>timeout){owned=0;return 'E';}
    }
    return -1;
}
