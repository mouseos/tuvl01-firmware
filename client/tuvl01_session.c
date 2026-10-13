/* SPDX-License-Identifier: MIT */
#include "tuvl01_session.h"
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef int addrlen_t;
#define INVALID INVALID_SOCKET
static void sock_close(uintptr_t s){closesocket((SOCKET)s);}
uint64_t tuvl01_now_ms(void){return GetTickCount64();}
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
typedef socklen_t addrlen_t;
#define INVALID ((uintptr_t)-1)
typedef int SOCKET;
static void sock_close(uintptr_t s){close((int)s);}
uint64_t tuvl01_now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
#endif

static void pause_ms(unsigned ms){
#ifdef _WIN32
    Sleep(ms);
#else
    usleep(ms*1000);
#endif
}
static int wait_readable(uintptr_t sock,int timeout_ms){
    fd_set set;struct timeval tv;
    FD_ZERO(&set);FD_SET((SOCKET)sock,&set);
    tv.tv_sec=timeout_ms/1000;tv.tv_usec=(timeout_ms%1000)*1000;
    return select((int)sock+1,&set,0,0,&tv);
}
static uintptr_t udp_socket(uint16_t port,int rcvbuf){
    SOCKET s=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
    if((uintptr_t)s==INVALID)return INVALID;
    struct sockaddr_in a;
    a.sin_family=AF_INET;a.sin_port=htons(port);a.sin_addr.s_addr=htonl(INADDR_ANY);
    for(unsigned i=0;i<sizeof a.sin_zero;i++)a.sin_zero[i]=0;
    if(rcvbuf)setsockopt(s,SOL_SOCKET,SO_RCVBUF,(const char *)&rcvbuf,sizeof rcvbuf);
    if(bind(s,(struct sockaddr *)&a,sizeof a)){sock_close(s);return INVALID;}
    return (uintptr_t)s;
}
static int send_to(uintptr_t sock,uint16_t port,const void *data,size_t n){
    struct sockaddr_in a;
    a.sin_family=AF_INET;a.sin_port=htons(port);a.sin_addr.s_addr=inet_addr(TUVL01_DEVICE_IP);
    for(unsigned i=0;i<sizeof a.sin_zero;i++)a.sin_zero[i]=0;
    return sendto((SOCKET)sock,(const char *)data,(int)n,0,(struct sockaddr *)&a,sizeof a)==(int)n?0:-1;
}
int tuvl01_open(tuvl01_session *s){
#ifdef _WIN32
    WSADATA w;
    if(WSAStartup(MAKEWORD(2,2),&w))return -1;
#endif
    s->control=s->data=INVALID;s->next_id=1;s->last_ping_ms=s->last_keepalive_ms=0;s->open=0;
    tuvl01_loss_init(&s->loss);
    s->data=udp_socket(TUVL01_STREAM_PORT,4*1024*1024);
    if(s->data==INVALID)return -2;
    s->control=udp_socket(0,65536);
    if(s->control==INVALID){sock_close(s->data);s->data=INVALID;return -3;}
    s->open=1;return 0;
}
void tuvl01_close(tuvl01_session *s){
    if(!s->open)return;
    sock_close(s->control);sock_close(s->data);s->open=0;
#ifdef _WIN32
    WSACleanup();
#endif
}
static int exchange(tuvl01_session *s,const uint8_t *request,size_t length,uint8_t op,uint16_t id,
                    tuvl01_reply *reply,int timeout_ms){
    uint8_t buffer[64];
    if(send_to(s->control,TUVL01_CONTROL_PORT,request,length))return -1;
    uint64_t end=tuvl01_now_ms()+(uint64_t)timeout_ms;
    for(;;){
        uint64_t now=tuvl01_now_ms();
        if(now>=end)return -2;
        int ready=wait_readable(s->control,(int)(end-now));
        if(ready<=0)return -2;
        struct sockaddr_in from;addrlen_t fl=sizeof from;
        int n=recvfrom((SOCKET)s->control,(char *)buffer,sizeof buffer,0,(struct sockaddr *)&from,&fl);
        if(n<=0 || from.sin_addr.s_addr!=inet_addr(TUVL01_DEVICE_IP) || ntohs(from.sin_port)!=TUVL01_CONTROL_PORT)continue;
        tuvl01_reply r;
        if(tuvl01_parse_reply(buffer,(size_t)n,&r) || r.id!=id || r.op!=op)continue;
        if(reply)*reply=r;
        return r.status==TUVL01_STATUS_OK?0:-3;
    }
}
int tuvl01_command(tuvl01_session *s,uint8_t op,tuvl01_reply *reply,int timeout_ms){
    uint8_t request[TUVL01_REQUEST_SIZE];
    uint16_t id=s->next_id++;
    tuvl01_build_request(request,op,id);
    return exchange(s,request,sizeof request,op,id,reply,timeout_ms);
}
int tuvl01_tune(tuvl01_session *s,uint8_t channel,uint8_t partial,int timeout_ms){
    uint8_t request[TUVL01_REQUEST_SIZE+2];
    uint16_t id=s->next_id++;
    tuvl01_reply r;
    tuvl01_build_tune_request(request,channel,partial,id);
    int rc=exchange(s,request,sizeof request,TUVL01_OP_TUNE,id,&r,1500);
    if(rc)return rc;
    uint64_t end=tuvl01_now_ms()+(uint64_t)timeout_ms;
    for(;;){
        /* The device may be busy retuning and answer late: keep polling until the deadline. */
        if(!tuvl01_command(s,TUVL01_OP_STATUS,&r,1000)){
            if(r.tune==TUVL01_TUNE_FAILED)return -4;
            if(r.tune==TUVL01_TUNE_DONE && r.channel==channel && r.partial==partial)return 0;
        }
        if(tuvl01_now_ms()>=end)return -5;
        pause_ms(100);
    }
}
int tuvl01_receive(tuvl01_session *s,uint8_t *out,size_t capacity,int timeout_ms){
    uint8_t buffer[1500];
    if(wait_readable(s->data,timeout_ms)<=0)return 0;
    struct sockaddr_in from;addrlen_t fl=sizeof from;
    int n=recvfrom((SOCKET)s->data,(char *)buffer,sizeof buffer,0,(struct sockaddr *)&from,&fl);
    if(n<=0)return 0;
    if(from.sin_addr.s_addr!=inet_addr(TUVL01_DEVICE_IP) || ntohs(from.sin_port)!=TUVL01_STREAM_PORT)return 0;
    tuvl01_stream st;
    if(tuvl01_parse_stream(buffer,(size_t)n,&st)){++s->loss.invalid;return 0;}
    if(tuvl01_loss_update(&s->loss,&st))return 0;
    size_t bytes=st.packets*188;
    if(bytes>capacity)return -1;
    for(size_t i=0;i<bytes;i++)out[i]=st.ts[i];
    return (int)bytes;
}
void tuvl01_service(tuvl01_session *s,int ping_ms,int keepalive_ms){
    uint8_t buffer[64];uint64_t now=tuvl01_now_ms();
    while(wait_readable(s->control,0)>0){  /* drop echo/keepalive replies */
        if(recvfrom((SOCKET)s->control,(char *)buffer,sizeof buffer,0,0,0)<=0)break;
    }
    if(ping_ms>0 && now-s->last_ping_ms>=(uint64_t)ping_ms){
        s->last_ping_ms=now;send_to(s->control,TUVL01_ECHO_PORT,"K",1);
    }
    if(keepalive_ms>0 && now-s->last_keepalive_ms>=(uint64_t)keepalive_ms){
        uint8_t request[TUVL01_REQUEST_SIZE];
        s->last_keepalive_ms=now;
        tuvl01_build_request(request,TUVL01_OP_KEEPALIVE,s->next_id++);
        send_to(s->control,TUVL01_CONTROL_PORT,request,sizeof request);
    }
}


