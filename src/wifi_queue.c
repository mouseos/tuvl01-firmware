/* SPDX-License-Identifier: MIT. Independently serialized protocol values. */
#include "wifi_queue.h"
unsigned wifi_queue_pack(uint8_t *out,unsigned capacity,unsigned mode){
    static const uint16_t values[2][4][4]={
        {{15,127,0,3},{15,1023,0,7},{7,15,94,1},{3,7,47,1}},
        {{7,15,94,1},{15,1023,0,7},{7,15,94,1},{1,7,47,1}}
    };
    if(!out || capacity<52 || mode>2)return 0;
    for(unsigned i=0;i<52;i++)out[i]=0;
    for(unsigned ac=0;ac<4;ac++)for(unsigned field=0;field<4;field++){
        unsigned value=values[mode!=0][ac][field],offset=8+ac*10+field*2;
        out[offset+(mode==2)]=(uint8_t)value;
        out[offset+(mode!=2)]=(uint8_t)(value>>8);
    }
    out[48]=1; /* network1; QBSS=0 agrees with non-QoS beacon/station */
    return 52;
}
