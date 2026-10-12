// SPDX-License-Identifier: MIT
// BonDriver interface (IBonDriver / IBonDriver2) as consumed by TVTest and similar
// players. Method order is part of the binary contract, including the order of the
// two GetTsStream overloads under the MSVC ABI: do not reorder.
#ifndef IBONDRIVER_H
#define IBONDRIVER_H
typedef int BOOL;
typedef unsigned char BYTE;
typedef unsigned long DWORD;

class IBonDriver {
public:
    virtual const BOOL OpenTuner(void)=0;
    virtual void CloseTuner(void)=0;
    virtual const BOOL SetChannel(const BYTE bCh)=0;
    virtual const float GetSignalLevel(void)=0;
    virtual const DWORD WaitTsStream(const DWORD dwTimeOut=0)=0;
    virtual const DWORD GetReadyCount(void)=0;
    virtual const BOOL GetTsStream(BYTE *pDst,DWORD *pdwSize,DWORD *pdwRemain)=0;
    virtual const BOOL GetTsStream(BYTE **ppDst,DWORD *pdwSize,DWORD *pdwRemain)=0;
    virtual void PurgeTsStream(void)=0;
    virtual void Release(void)=0;
};

class IBonDriver2 : public IBonDriver {
public:
    virtual const wchar_t *GetTunerName(void)=0;
    virtual const BOOL IsTunerOpening(void)=0;
    virtual const wchar_t *EnumTuningSpace(const DWORD dwSpace)=0;
    virtual const wchar_t *EnumChannelName(const DWORD dwSpace,const DWORD dwChannel)=0;
    virtual const BOOL SetChannel(const DWORD dwSpace,const DWORD dwChannel)=0;
    virtual const DWORD GetCurSpace(void)=0;
    virtual const DWORD GetCurChannel(void)=0;
    virtual void Release(void)=0;
};
#endif
