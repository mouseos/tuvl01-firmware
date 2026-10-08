/* SPDX-License-Identifier: MIT */
#include "wifi_status.h"
static uint32_t le32(const uint8_t *p){
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static unsigned le16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
int wifi_status_decode(const uint8_t *data,unsigned length,struct wifi_status *out){
    if(!data || !out || length!=88)return 0;
    unsigned count0=le16(data+12),count1=le16(data+14);
    if(count0>1 || count1>1)return 0;
    unsigned rx0=count0?le16(data+16):0,rx1=count1?le16(data+48):0;
    /* RX0 consumes a four-byte trailer; existing receive buffers are 4KiB.
     * Ignore unused slots, which need not contain zero. */
    if((count0 && (rx0<8 || rx0>4092)) || (count1 && (rx1<8 || rx1>4096)))return 0;
    uint32_t tx0=le32(data+4),tx1=le32(data+8),status=le32(data);
    /* The original SH-2A path corrects a stale TX_DONE bit when release
     * counters are present. Those counters must be accounted exactly once. */
    if(tx0 || tx1)status|=1;
    out->interrupt=status;out->tx0=tx0;out->tx1=tx1;
    out->rx_lengths=rx0|(rx1<<16);
    out->mailbox0=le32(data+80);out->mailbox1=le32(data+84);
    return 1;
}
