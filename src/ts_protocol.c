/* SPDX-License-Identifier: MIT */
#include "tuner_ts.h"
int tuner_ts_classify(uint8_t status){
    /* Unknown/reserved bits must not become a ready/overflow diagnosis. */
    if(status&0xf8)return -4;
    if(status==0)return 0;
    if(status==1)return 1;
    if(status&2)return -2;
    if(status&4)return -3;
    return -4;
}
