/* SPDX-License-Identifier: MIT */
#include "ts_benchmark_protocol.h"
#include "image.h"
static uint32_t be32(const uint8_t *p){
    return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];
}
unsigned ts_benchmark_seconds(const uint8_t *p,unsigned n){
    if(!p || n!=12 || p[0]!='T' || p[1]!='S' || p[2]!='B' || p[3]!='1' ||
       crc32(p,8)!=be32(p+8))return 0;
    unsigned seconds=be32(p+4);
    return seconds && seconds<=300?seconds:0;
}
