/* SPDX-License-Identifier: MIT */
#include "tuner_monitor.h"
int tuner_frame_state(uint8_t status95,uint8_t status97){
    if((status95&0xf0) || (status97&8))return -1;
    return (status97&0x10)?1:0;
}
