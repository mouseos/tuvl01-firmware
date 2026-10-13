// SPDX-License-Identifier: MIT
// BonDriver for the TUVL01 Wi-Fi tuner. A thin shell over the portable client
// (../tuvl01_*): all protocol knowledge lives there, so other front ends (e.g. an
// Android app) reuse it unchanged. Built without the C runtime; see build.ps1.
#include "IBonDriver.h"
#include "../tuvl01_session.h"
#include <stddef.h>

// ---- minimal Win32 surface (declared here so no SDK headers are needed) ----
typedef void *HANDLE;
struct SRWLOCK_T {void *p;};
#define W32 extern "C" __declspec(dllimport)
W32 HANDLE CreateThread(void *,size_t,unsigned long (*)(void *),void *,DWORD,DWORD *);
W32 DWORD WaitForSingleObject(HANDLE,DWORD);
W32 HANDLE CreateEventW(void *,BOOL,BOOL,const wchar_t *);
W32 BOOL SetEvent(HANDLE);
W32 BOOL ResetEvent(HANDLE);
W32 BOOL CloseHandle(HANDLE);
W32 void Sleep(DWORD);
W32 HANDLE GetProcessHeap(void);
W32 void *HeapAlloc(HANDLE,DWORD,size_t);
W32 BOOL HeapFree(HANDLE,DWORD,void *);
W32 void AcquireSRWLockExclusive(SRWLOCK_T *);
W32 void ReleaseSRWLockExclusive(SRWLOCK_T *);
static const DWORD HEAP_ZERO=8;
inline void *operator new(size_t,void *p){return p;}
extern "C" int _fltused=0;
// Referenced by the compiler-generated RTTI descriptors; only its address is stored.
extern "C" void *const type_info_vftable_stub[2] __asm__("??_7type_info@@6B@")={0,0};

namespace {
const size_t RING_SIZE=4*1024*1024;     // ~1.9 s at 17 Mbps
const size_t CHUNK=188*1024;
const DWORD FIRST_CHANNEL=13,CHANNELS=40,SPACES=2;   // UHF 13..52; space 0 full segment, space 1 one segment
class Lock{SRWLOCK_T &l;public:explicit Lock(SRWLOCK_T &x):l(x){AcquireSRWLockExclusive(&l);}~Lock(){ReleaseSRWLockExclusive(&l);}};

class Driver : public IBonDriver2 {
public:
    static Driver *Create(){
        void *m=HeapAlloc(GetProcessHeap(),HEAP_ZERO,sizeof(Driver));
        return m?new(m) Driver():0;
    }
    const BOOL OpenTuner(void) override {
        if(open_)return 1;
        if(tuvl01_open(&session_))return 0;
        tuvl01_reply r;int rc=-1;
        for(int i=0;i<3 && rc;i++)rc=tuvl01_command(&session_,TUVL01_OP_HELLO,&r,700);
        if(rc || r.version!=1 || (r.caps&(TUVL01_CAP_STREAM|TUVL01_CAP_TUNE))!=(TUVL01_CAP_STREAM|TUVL01_CAP_TUNE)){tuvl01_close(&session_);return 0;}
        ring_=(unsigned char *)HeapAlloc(GetProcessHeap(),0,RING_SIZE);
        event_=CreateEventW(0,1,0,0);
        if(!ring_ || !event_){Cleanup();return 0;}
        rd_=wr_=0;stop_=0;streaming_=0;level_=0;space_=channel_=0xFFFFFFFFUL;
        thread_=CreateThread(0,0,&Driver::Thread,this,0,0);
        if(!thread_){Cleanup();return 0;}
        open_=1;return 1;
    }
    void CloseTuner(void) override {
        if(!open_)return;
        open_=0;
        if(streaming_){Lock g(io_);tuvl01_command(&session_,TUVL01_OP_STOP,0,500);}
        stop_=1;WaitForSingleObject(thread_,3000);
        Cleanup();
    }
    const BOOL SetChannel(const BYTE bCh) override {return SetChannel(0UL,(DWORD)bCh);}
    const BOOL SetChannel(const DWORD space,const DWORD channel) override {
        if(!open_ || space>=SPACES || channel>=CHANNELS)return 0;
        if(streaming_ && space==space_ && channel==channel_)return 1;
        tuvl01_reply r;int rc;
        {
            Lock g(io_);
            // TUNE stops the stream and returns when the device reports it done; START follows.
            rc=tuvl01_tune(&session_,(uint8_t)(FIRST_CHANNEL+channel),(uint8_t)space,12000);
            if(!rc)rc=tuvl01_command(&session_,TUVL01_OP_START,&r,1000);
        }
        if(rc){streaming_=0;space_=channel_=0xFFFFFFFFUL;return 0;}
        PurgeTsStream();space_=space;channel_=channel;streaming_=1;return 1;
    }
    const float GetSignalLevel(void) override {return level_;}  // receive rate in Mbps
    const DWORD WaitTsStream(const DWORD timeout) override {
        if(!open_)return 0x102;
        if(Available())return 0;
        return WaitForSingleObject(event_,timeout);
    }
    const DWORD GetReadyCount(void) override {size_t n=Available();return n?(DWORD)((n+CHUNK-1)/CHUNK):0;}
    const BOOL GetTsStream(BYTE **ppDst,DWORD *pdwSize,DWORD *pdwRemain) override {
        if(!open_)return 0;
        size_t n=Pop(out_,sizeof out_);
        *ppDst=out_;*pdwSize=(DWORD)n;if(pdwRemain){size_t a=Available();*pdwRemain=a?(DWORD)((a+CHUNK-1)/CHUNK):0;}
        return 1;
    }
    const BOOL GetTsStream(BYTE *pDst,DWORD *pdwSize,DWORD *pdwRemain) override {
        if(!open_)return 0;
        size_t n=Pop(pDst,*pdwSize);
        *pdwSize=(DWORD)n;if(pdwRemain){size_t a=Available();*pdwRemain=a?(DWORD)((a+CHUNK-1)/CHUNK):0;}
        return 1;
    }
    void PurgeTsStream(void) override {Lock g(ring_lock_);rd_=wr_;ResetEvent(event_);}
    void Release(void) override {CloseTuner();this->~Driver();HeapFree(GetProcessHeap(),0,this);}
    const wchar_t *GetTunerName(void) override {return L"TUVL01";}
    const BOOL IsTunerOpening(void) override {return open_;}
    const wchar_t *EnumTuningSpace(const DWORD space) override {return space==0?L"UHF":space==1?L"UHF (1seg)":0;}
    const wchar_t *EnumChannelName(const DWORD space,const DWORD channel) override {
        return space<SPACES && channel<CHANNELS?names_[channel]:0;
    }
    const DWORD GetCurSpace(void) override {return space_;}
    const DWORD GetCurChannel(void) override {return channel_;}
private:
    Driver():open_(0),stop_(0),streaming_(0),level_(0),rd_(0),wr_(0),ring_(0),event_(0),thread_(0){
        io_.p=0;ring_lock_.p=0;space_=channel_=0xFFFFFFFFUL;
        // "13ch".."52ch": built by hand because no C runtime is available.
        for(DWORD i=0;i<CHANNELS;i++){
            DWORD n=FIRST_CHANNEL+i;
            names_[i][0]=(wchar_t)(L'0'+n/10);names_[i][1]=(wchar_t)(L'0'+n%10);names_[i][2]=L'c';names_[i][3]=L'h';names_[i][4]=0;
        }
    }
    ~Driver(){}
    size_t Available(){Lock g(ring_lock_);return wr_-rd_;}
    void Push(const unsigned char *d,size_t n){
        Lock g(ring_lock_);
        if(RING_SIZE-(wr_-rd_)<n)return;   // consumer stalled: drop newest (keeps TS packets whole)
        for(size_t i=0;i<n;i++)ring_[(wr_+i)%RING_SIZE]=d[i];
        wr_+=n;SetEvent(event_);
    }
    size_t Pop(unsigned char *out,size_t cap){
        Lock g(ring_lock_);
        size_t n=wr_-rd_;if(n>cap)n=cap;if(n>CHUNK)n=CHUNK;n-=n%188;
        for(size_t i=0;i<n;i++)out[i]=ring_[(rd_+i)%RING_SIZE];
        rd_+=n;if(rd_==wr_)ResetEvent(event_);
        return n;
    }
    void Cleanup(){
        tuvl01_close(&session_);
        if(thread_){CloseHandle(thread_);thread_=0;}
        if(event_){CloseHandle(event_);event_=0;}
        if(ring_){HeapFree(GetProcessHeap(),0,ring_);ring_=0;}
    }
    static unsigned long Thread(void *self){((Driver *)self)->Run();return 0;}
    void Run(){
        unsigned char buffer[1344];
        uint64_t window=tuvl01_now_ms(),last_check=window;size_t bytes=0;
        while(!stop_){
            int n=tuvl01_receive(&session_,buffer,sizeof buffer,5);
            if(n>0){Push(buffer,(size_t)n);bytes+=(size_t)n;}
            {Lock g(io_);tuvl01_service(&session_,streaming_?10:0,1000);}
            uint64_t now=tuvl01_now_ms();
            if(streaming_ && now-last_check>=1000){
                // The device refuses START before broadcast lock. If the stream is wanted but not
                // running, start it as soon as the device reports lock (weak channels lock late).
                last_check=now;
                Lock g(io_);
                tuvl01_reply r;
                if(streaming_ && !tuvl01_command(&session_,TUVL01_OP_STATUS,&r,300) &&
                   r.state==TUVL01_STATE_IDLE && r.tune!=TUVL01_TUNE_BUSY && r.lock==1)
                    tuvl01_command(&session_,TUVL01_OP_START,&r,300);
            }
            if(now-window>=500){level_=(float)((double)bytes*8.0/1e6/((double)(now-window)/1000.0));bytes=0;window=now;}
        }
    }
    volatile int open_,stop_,streaming_;
    volatile DWORD space_,channel_;
    wchar_t names_[CHANNELS][5];
    volatile float level_;
    volatile size_t rd_,wr_;
    unsigned char *ring_;
    HANDLE event_,thread_;
    SRWLOCK_T io_,ring_lock_;
    tuvl01_session session_;
    unsigned char out_[CHUNK];
};
}

extern "C" __declspec(dllexport) IBonDriver *CreateBonDriver(){return Driver::Create();}
extern "C" BOOL __stdcall DllMain(HANDLE,DWORD,void *){return 1;}


