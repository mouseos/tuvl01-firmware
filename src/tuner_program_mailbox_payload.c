/* SPDX-License-Identifier: MIT */
#include "tuner.h"
#include "tuner_pseq.h"

/* Replay the known complete record, replacing only the existing operand.
 * Caller must halt, select 0298 and arm transfer. No control reads here. */
int tuner_program_mailbox_write_record(uint8_t operand,uint8_t *expected){
    if(!expected || (operand!=0x0c && operand!=0x0d) ||
       !tuner_program_mailbox_original_valid())return -1;
    unsigned off=pseq_records[2].offset,count=pseq_records[2].count,parity=0;
    const uint8_t *raw=pseq_bytes+off;
    for(unsigned i=0;i<count;i++){
        for(unsigned bits=raw[2+i];bits;bits>>=1)parity^=bits&1;
    }
    if(parity!=raw[count+2])return -1;
    *expected=parity^(operand!=0x0d);
    for(unsigned pos=0;pos<count;){
        uint8_t bytes[128];unsigned chunk=count-pos;
        if(chunk>sizeof bytes)chunk=sizeof bytes;
        for(unsigned n=0;n<chunk;n++)
            bytes[n]=pos+n==0x4e9-0x298?operand:raw[2+pos+n];
        if(tuner_write_burst(0x61,0xf6,bytes,chunk))return -1;
        pos+=chunk;
    }
    return 0;
}
