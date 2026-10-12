"""Query or set the Windows WLAN 'background scan' flag of one interface (no admin tools, WLAN API only).

A station that scans other channels leaves the AP's channel for 15..130 ms at a time; a full-segment TS
stream at 17 Mbps loses every datagram sent in that window. Disable the flag only for a test and restore it.
Usage: python tools/wifi_bgscan.py --interface "Wi-Fi 2" [--set on|off]
"""
import argparse,ctypes as c,sys
from ctypes import wintypes as w
OPCODES={'background-scan':2,'media-streaming':3}  # wlan_intf_opcode_* values in wlanapi.h
OPCODE_BACKGROUND_SCAN=2
class GUID(c.Structure):_fields_=[('d1',c.c_uint32),('d2',c.c_uint16),('d3',c.c_uint16),('d4',c.c_ubyte*8)]
class IFINFO(c.Structure):_fields_=[('guid',GUID),('desc',c.c_wchar*256),('state',c.c_uint32)]
class IFLIST(c.Structure):_fields_=[('n',w.DWORD),('idx',w.DWORD),('items',IFINFO*1)]
wlan=c.WinDLL('wlanapi')
def run(a):
    h=w.HANDLE();ver=w.DWORD()
    if wlan.WlanOpenHandle(2,None,c.byref(ver),c.byref(h)):raise OSError('WlanOpenHandle failed')
    try:
        lst=c.c_void_p()
        if wlan.WlanEnumInterfaces(h,None,c.byref(lst)):raise OSError('WlanEnumInterfaces failed')
        base=lst.value;n=c.cast(base,c.POINTER(w.DWORD))[0]
        found=None
        for i in range(n):
            info=IFINFO.from_address(base+8+i*c.sizeof(IFINFO))
            if a.interface.lower() in info.desc.lower() or a.match and a.match.lower() in info.desc.lower():
                found=info;break
        if found is None:
            names=[IFINFO.from_address(base+8+i*c.sizeof(IFINFO)).desc for i in range(n)]
            raise SystemExit('no interface description contains %r; found %s'%(a.match or a.interface,names))
        size=w.DWORD();data=c.c_void_p();opcode_type=w.DWORD()
        rc=wlan.WlanQueryInterface(h,c.byref(found.guid),OPCODE_BACKGROUND_SCAN,None,c.byref(size),c.byref(data),c.byref(opcode_type))
        cur=None if rc else bool(c.cast(data,c.POINTER(w.BOOL))[0])
        print('interface:',found.desc.strip(),'| background scan enabled:',cur,'(query rc=%d)'%rc)
        if a.set:
            value=w.BOOL(1 if a.set=='on' else 0)
            rc=wlan.WlanSetInterface(h,c.byref(found.guid),OPCODE_BACKGROUND_SCAN,c.sizeof(value),c.byref(value),None)
            print('set',a.set,'rc=%d'%rc)
            rc=wlan.WlanQueryInterface(h,c.byref(found.guid),OPCODE_BACKGROUND_SCAN,None,c.byref(size),c.byref(data),c.byref(opcode_type))
            print('after:',None if rc else bool(c.cast(data,c.POINTER(w.BOOL))[0]))
        return 0
    finally:wlan.WlanCloseHandle(h,None)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--interface',default='Wi-Fi 6E AX210');p.add_argument('--match',default='AX210')
    p.add_argument('--set',choices=['on','off'])
    p.add_argument('--flag',choices=sorted(OPCODES),default='background-scan',help='which WLAN interface flag to read/set')
    a=p.parse_args();global OPCODE_BACKGROUND_SCAN;OPCODE_BACKGROUND_SCAN=OPCODES[a.flag];return run(a)
if __name__=='__main__':sys.exit(main())
