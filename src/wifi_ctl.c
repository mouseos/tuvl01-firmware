/* SPDX-License-Identifier: MIT. Wi-Fi control service for any client. */
#include "wifi_ctl.h"
#include "tuner_ts.h"
enum {OP_HELLO=1,OP_START=2,OP_STOP=3,OP_STATUS=4,OP_KEEPALIVE=5};
enum {ST_OK=0,ST_BAD=1,ST_UNSUPPORTED=2};
static volatile int pending=-1;
static volatile unsigned owned,activity;
static unsigned seen_activity,last_change;
static unsigned state(void){return tuner_ts_stream_active()?1:pending=='B'?2:0;}
unsigned wifi_ctl_service(unsigned port,const uint8_t *body,unsigned n,uint8_t *r,unsigned cap){
    ++activity;
    if(port!=WIFI_CTL_PORT)return 0;
    if(n<8 || cap<24 || body[0]!='T' || body[1]!='C' || body[2]!='T' || body[3]!='1')return 0;
    unsigned op=body[4],status=ST_OK,len=8;
    r[0]='T';r[1]='C';r[2]='T';r[3]='1';r[5]=0;r[6]=body[6];r[7]=body[7];
    if(op==OP_HELLO){
        r[8]=WIFI_CTL_VERSION;r[9]=WIFI_CTL_REVISION>>8;r[10]=WIFI_CTL_REVISION;
        r[11]=0;r[12]=0;r[13]=0;r[14]=WIFI_CTL_CAP_STREAM;
        r[15]=4202>>8;r[16]=4202&255;r[17]=state();len=18;
    }else if(op==OP_START){
        if(!tuner_ts_stream_active() && pending!='B'){pending='B';}
        owned=1;r[8]=state();len=9;
    }else if(op==OP_STOP){
        owned=0;if(tuner_ts_stream_active())pending='E';else if(pending=='B')pending=-1;
        r[8]=state();len=9;
    }else if(op==OP_STATUS){
        r[8]=state();r[9]=0;r[10]=0;r[11]=0;len=12; /* channel field reserved: 0 = unspecified */
    }else if(op==OP_KEEPALIVE){
        r[8]=state();len=9;
    }else status=ST_UNSUPPORTED;
    r[4]=op|0x80;r[5]=status;
    return len;
}
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
