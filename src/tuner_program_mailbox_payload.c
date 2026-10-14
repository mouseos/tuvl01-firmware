/* SPDX-License-Identifier: MIT */
#include "tuner.h"
#include "tuner_pseq.h"

/* Replay the known complete record, replacing the existing operand and its
 * trailing byte-XOR correction. All 30 stock records have byte XOR zero.
 * Caller must halt, select 0298 and arm transfer. No control reads here. */
uint16_t tuner_program_mailbox_known_operand(unsigned index){
    /* Observed C0/C4/C5 operand motifs, not an established RAM map.
     * The final three are store-only candidates; C5 read semantics at
     * those targets require physical validation. Keep prior indices. */
    static const uint16_t known[]={0x0f05,0x0f06,0x0f07,0x0f08,0x0f09,
        0x0f0a,0x0f0b,0x0f0c,0x0f0d,0x0fff,0x1ff0,0x1ff1,0x1ff2,
        0x0f0e,0x0ffe,0x1ff3};
    return index<sizeof known/sizeof known[0]?known[index]:0;
}
static int write_slot(const uint8_t slot[6],uint8_t *expected){
    if(!expected || !tuner_program_mailbox_original_valid())return -1;
    unsigned off=pseq_records[2].offset,count=pseq_records[2].count,byte_xor=0;
    const uint8_t *raw=pseq_bytes+off;
    for(unsigned i=0;i<count;i++)byte_xor^=raw[2+i];
    if(byte_xor || raw[count+2] || raw[count]!=1 || raw[count+1]!=0x2b)return -1;
    unsigned delta=0x4e7-0x298;uint8_t correction=0;
    for(unsigned n=0;n<6;n++)correction^=raw[2+delta+n]^slot[n];
    *expected=0; /* Match the stock zero-XOR record's F8 bit4, not popcount. */
    for(unsigned pos=0;pos<count;){
        uint8_t bytes[128];unsigned chunk=count-pos;
        if(chunk>sizeof bytes)chunk=sizeof bytes;
        for(unsigned n=0;n<chunk;n++)
            bytes[n]=pos+n==count-1?(raw[2+pos+n]^correction):
                     pos+n>=delta && pos+n<delta+6?slot[pos+n-delta]:raw[2+pos+n];
        if(tuner_write_burst(0x61,0xf6,bytes,chunk))return -1;
        pos+=chunk;
    }
    return 0;
}
int tuner_program_mailbox_write_record(uint16_t operand,uint8_t *expected){
    unsigned allowed=0;
    for(unsigned n=0;tuner_program_mailbox_known_operand(n);n++)
        if(operand==tuner_program_mailbox_known_operand(n))allowed=1;
    if(!allowed)return -1;
    const uint8_t slot[]={0xc5,operand>>8,operand,0x21,0x6d,1};
    return write_slot(slot,expected);
}
int tuner_program_mailbox_write_d5_record(uint8_t *expected,unsigned write20){
    /* Observed 30 D5 read candidate followed by 20/21 6D output candidates.
     * 20 follows native register write motifs; 21 is the existing mailbox.
     * Their internal output sources are not established. Final 01 pads the slot;
     * adjacent initialization at 04ED remains byte-for-byte unchanged. */
    if(write20>1)return -1;
    const uint8_t slot[]={0x30,0xd5,write20?0x20:0x21,0x6d,1,1};
    return write_slot(slot,expected);
}

int tuner_program_mailbox_write_reference_record(unsigned index,uint8_t *expected){
    static const uint8_t regs[]={0xd4,0x28,0x95};
    if(index>=sizeof regs)return -1;
    const uint8_t slot[]={0x30,regs[index],0x20,0x6d,1,1};
    return write_slot(slot,expected);
}
