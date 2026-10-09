#include "wifi_tx_power.h"
int wifi_tx_power_command(uint8_t *packet,unsigned capacity,int offset){
    if(!packet || capacity<40 || (offset!=0 && offset!=-12 && offset!=-24))return 0;
    for(unsigned i=0;i<40;i++)packet[i]=0;
    /* CID38: 32-byte body. Lower all 2.4GHz roles equally; leave 5GHz
     * offsets and concurrency policy at zero. Preserve channel limits at
     * the protocol default (63 half-dBm), not an absolute TX power table. */
    for(unsigned i=8;i<12;i++)packet[i]=(uint8_t)offset;
    for(unsigned i=20;i<38;i++)packet[i]=63;
    return 1;
}
