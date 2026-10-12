// SPDX-License-Identifier: MIT
// Loads BonDriver_TUVL01.dll the way TVTest does (LoadLibrary, CreateBonDriver,
// dynamic_cast to IBonDriver2 with MSVC RTTI) and reads TS for a few seconds.
#include "IBonDriver.h"
typedef void *HANDLE;
#define W32 extern "C" __declspec(dllimport)
W32 HANDLE LoadLibraryA(const char *);
W32 void *GetProcAddress(HANDLE,const char *);
W32 void ExitProcess(unsigned);
W32 unsigned long GetTickCount(void);
extern "C" int printf(const char *,...);
extern "C" int _fltused=0;
extern "C" void *const type_info_vftable_stub[2] __asm__("??_7type_info@@6B@")={0,0};
typedef IBonDriver *(*CreateFn)(void);
static int run(const char *dll,int seconds){
    HANDLE h=LoadLibraryA(dll);if(!h){printf("LoadLibrary failed\n");return 2;}
    CreateFn create=(CreateFn)GetProcAddress(h,"CreateBonDriver");if(!create){printf("no CreateBonDriver\n");return 2;}
    IBonDriver *base=create();
    IBonDriver2 *d=dynamic_cast<IBonDriver2 *>(base);
    printf("dynamic_cast<IBonDriver2*>: %s\n",d?"ok":"NULL");
    if(!d)return 3;
    printf("tuner=%ls space0=%ls ch0=%ls ch1=%p\n",d->GetTunerName(),d->EnumTuningSpace(0),d->EnumChannelName(0,0),(const void *)d->EnumChannelName(0,1));
    if(!d->OpenTuner()){printf("OpenTuner failed\n");d->Release();return 4;}
    if(!d->SetChannel(0UL,0UL)){printf("SetChannel failed\n");d->Release();return 5;}
    unsigned long start=GetTickCount(),total=0,sync_bad=0,calls=0,last=start;
    while(GetTickCount()-start<(unsigned long)seconds*1000){
        if(d->WaitTsStream(200)!=0)continue;
        BYTE *p;DWORD n,remain;
        if(!d->GetTsStream(&p,&n,&remain))break;
        ++calls;total+=n;
        for(DWORD i=0;i+188<=n;i+=188)if(p[i]!=0x47)++sync_bad;
        if(GetTickCount()-last>=1000){last=GetTickCount();printf("  level=%.2f Mbps total=%lu bytes sync_bad=%lu\n",d->GetSignalLevel(),total,sync_bad);}
    }
    printf("received %lu bytes in %lu reads, bad sync %lu\n",total,calls,sync_bad);
    d->CloseTuner();d->Release();
    return total && !sync_bad?0:6;
}
extern "C" void entry(void){
    ExitProcess((unsigned)run("BonDriver_TUVL01.dll",8));
}
