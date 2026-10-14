/* SPDX-License-Identifier: MIT */
#include "tuner.h"
#include "tuner_pseq.h"

/* Replay the known complete record, replacing only the existing operand.
 * Caller must halt, select 0298 and arm transfer. No control reads here. */
uint16_t tuner_program_mailbox_known_operand(unsigned index){
    /* Observed C4/C5 operand motifs, not an established RAM map. */
    static const uint16_t known[]={0x0f05,0x0f06,0x0f07,0x0f08,0x0f09,
        0x0f0a,0x0f0b,0x0f0c,0x0f0d,0x0fff,0x1ff0,0x1ff1,0x1ff2};
    return index<sizeof known/sizeof known[0]?known[index]:0;
}
int tuner_program_mailbox_write_record(uint16_t operand,uint8_t *expected){
    unsigned allowed=0;
    for(unsigned n=0;tuner_program_mailbox_known_operand(n);n++)
        if(operand==tuner_program_mailbox_known_operand(n))allowed=1;
    if(!expected || !allowed ||
       !tuner_program_mailbox_original_valid())return -1;
    unsigned off=pseq_records[2].offset,count=pseq_records[2].count,parity=0;
    const uint8_t *raw=pseq_bytes+off;
    for(unsigned i=0;i<count;i++){
        for(unsigned bits=raw[2+i];bits;bits>>=1)parity^=bits&1;
    }
    if(parity!=raw[count+2])return -1;
    *expected=parity;
    for(unsigned bits=operand^0x0f0d;bits;bits>>=1)*expected^=bits&1;
    for(unsigned pos=0;pos<count;){
        uint8_t bytes[128];unsigned chunk=count-pos;
        if(chunk>sizeof bytes)chunk=sizeof bytes;
        for(unsigned n=0;n<chunk;n++)
            bytes[n]=pos+n==0x4e8-0x298?(operand>>8):
                     pos+n==0x4e9-0x298?operand:raw[2+pos+n];
        if(tuner_write_burst(0x61,0xf6,bytes,chunk))return -1;
        pos+=chunk;
    }
    return 0;
}
