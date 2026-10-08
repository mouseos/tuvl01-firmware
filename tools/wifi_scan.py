"""Windows fresh Wi-Fi scan; prints only the requested firmware SSID/BSSID."""
import argparse,ctypes as c,json,sys,threading,time
U32=c.c_uint32
class Guid(c.Structure):
    _fields_=[('bytes',c.c_ubyte*16)]
class Interface(c.Structure):
    _fields_=[('guid',Guid),('name',c.c_uint16*256),('state',U32)]
class Ssid(c.Structure):
    _fields_=[('length',U32),('data',c.c_ubyte*32)]
class Rates(c.Structure):
    _fields_=[('length',U32),('data',c.c_uint16*126)]
class Bss(c.Structure):
    _fields_=[('ssid',Ssid),('phy_id',U32),('bssid',c.c_ubyte*6),
              ('type',U32),('phy',U32),('rssi',c.c_int32),('quality',U32),
              ('reg_domain',c.c_ubyte),('beacon_period',c.c_uint16),
              ('timestamp',c.c_uint64),('host_timestamp',c.c_uint64),
              ('capability',c.c_uint16),('frequency',U32),('rates',Rates),
              ('ie_offset',U32),('ie_size',U32)]
class Notification(c.Structure):
    _fields_=[('source',U32),('code',U32),('guid',Guid),('size',U32),('data',c.c_void_p)]
def check(result):
    if result:raise OSError(result,'Windows WLAN API failed')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ssid',default='TUVL01');p.add_argument('--bssid')
    p.add_argument('--interface');a=p.parse_args()
    if sys.platform!='win32':p.error('Windows is required')
    assert c.sizeof(Interface)==532 and c.sizeof(Bss)==360
    api=c.WinDLL('wlanapi');handle=c.c_void_p();version=U32()
    api.WlanOpenHandle.argtypes=[U32,c.c_void_p,c.POINTER(U32),c.POINTER(c.c_void_p)]
    api.WlanCloseHandle.argtypes=[c.c_void_p,c.c_void_p]
    api.WlanFreeMemory.argtypes=[c.c_void_p]
    api.WlanEnumInterfaces.argtypes=[c.c_void_p,c.c_void_p,c.POINTER(c.c_void_p)]
    api.WlanScan.argtypes=[c.c_void_p,c.POINTER(Guid),c.c_void_p,c.c_void_p,c.c_void_p]
    api.WlanGetNetworkBssList.argtypes=[c.c_void_p,c.POINTER(Guid),c.c_void_p,U32,c.c_int,c.c_void_p,c.POINTER(c.c_void_p)]
    callback_type=c.WINFUNCTYPE(None,c.POINTER(Notification),c.c_void_p)
    api.WlanRegisterNotification.argtypes=[c.c_void_p,U32,c.c_int,callback_type,c.c_void_p,c.c_void_p,c.POINTER(U32)]
    check(api.WlanOpenHandle(2,None,c.byref(version),c.byref(handle)))
    try:
        ptr=c.c_void_p();check(api.WlanEnumInterfaces(handle,None,c.byref(ptr)))
        try:
            count=U32.from_address(ptr.value).value
            if count>64:raise ValueError('Invalid interface count')
            interfaces=[Interface.from_buffer_copy(c.string_at(ptr.value+8+i*532,532)) for i in range(count)]
        finally:api.WlanFreeMemory(ptr)
        selected=None
        for interface in interfaces:
            name=bytes(interface.name).decode('utf-16-le').split('\0',1)[0]
            if not a.interface or name==a.interface:selected=interface;break
        if selected is None:raise RuntimeError('No matching WLAN interface')
        completed=threading.Event();result=[]
        def notify(raw,context):
            n=raw.contents
            if n.source==8 and bytes(n.guid.bytes)==bytes(selected.guid.bytes) and n.code in (7,8):
                result.append(n.code);completed.set()
        callback=callback_type(notify);previous=U32()
        check(api.WlanRegisterNotification(handle,8,0,callback,None,None,c.byref(previous)))
        scan_start=int((time.time()+11644473600)*10000000)
        check(api.WlanScan(handle,c.byref(selected.guid),None,None,None))
        if not completed.wait(6) or result[-1]!=7:raise RuntimeError('Fresh WLAN scan did not complete')
        ptr=c.c_void_p()
        check(api.WlanGetNetworkBssList(handle,c.byref(selected.guid),None,3,0,None,c.byref(ptr)))
        found=[]
        try:
            total=U32.from_address(ptr.value).value;count=U32.from_address(ptr.value+4).value
            if total<8 or count>(total-8)//360:raise ValueError('Invalid BSS list')
            for i in range(count):
                entry=Bss.from_address(ptr.value+8+i*360)
                if entry.ssid.length>32:continue
                ssid=bytes(entry.ssid.data[:entry.ssid.length]).decode('utf-8',errors='replace')
                bssid=':'.join(f'{v:02x}' for v in entry.bssid)
                if ssid!=a.ssid or (a.bssid and bssid.lower()!=a.bssid.lower()):continue
                fresh=entry.host_timestamp>=scan_start
                found.append(dict(ssid=ssid,bssid=bssid,rssi_dbm=entry.rssi,
                                  frequency_khz=entry.frequency,beacon_period_tu=entry.beacon_period,
                                  fresh=fresh,host_timestamp=entry.host_timestamp))
        finally:api.WlanFreeMemory(ptr)
        print(json.dumps(dict(scan_complete=True,networks=found),ensure_ascii=False))
        if not any(n['fresh'] for n in found):raise RuntimeError('No fresh matching beacon detected')
    finally:api.WlanCloseHandle(handle,None)
if __name__=='__main__':main()
