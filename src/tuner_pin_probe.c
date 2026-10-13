/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "tuner.h"
#include "time_counts.h"

/* Passive, finite GPIO observation. No clock or chip-select is driven.
 * GPIO timestamps include software overhead and IRQ/scheduler gaps; this
 * is neither a uniform-rate sampler nor a logic-analyzer replacement. */
#define SAMPLES 512U
#define PDCR1 R16(0xfffe386cUL)
#define PDIOR0 R16(0xfffe3872UL)
#define PDPR0 R16(0xfffe387aUL)
static uint32_t counts[2][SAMPLES];
static uint8_t pins[2][SAMPLES];
static void field(const char *name,unsigned v){uart_puts(name);uart_hex(v);}
void tuner_pin_capture_probe(void){
    uint8_t e8,f8,actual,check_f8;
    unsigned captured=0,failed=0,restored=0;
    uart_puts("PIN capture start PD4..7 input-only\n");
    /* Commands stop streaming first; refuse any remaining DMA or RSPI use.
     * Reject unknown mux state rather than changing unrelated pin functions. */
    if((R32(0xfffe100cUL)&1U) || (R32(0xfffe101cUL)&1U) ||
       (R8(0xffff8800UL)&0x40U) || PDCR1!=0x2222U){
        uart_puts("PIN capture end status=refused-mcu-state\n");return;
    }
    if(tuner_read_register(0x62,0xe8,&e8) || tuner_read_register(0x62,0xf8,&f8)){
        uart_puts("PIN capture end status=i2c-failed-before-change\n");return;
    }
    if((e8&15U)!=2U || (f8&15U)!=1U){
        uart_puts("PIN capture end status=unexpected-tuner-state\n");return;
    }
    uint16_t ior=PDIOR0;
    PDIOR0&=(uint16_t)~0xf0U; /* Set input BEFORE selecting GPIO. */
    PDCR1=0;
    for(unsigned mode=0;mode<2;mode++){
        if(mode && (tuner_write_register(0x62,0xe8,e8&0xf0U) ||
                    tuner_read_register(0x62,0xe8,&actual) || actual!=(e8&0xf0U))){
            failed=1;break;
        }
        for(unsigned n=0;n<SAMPLES;n++){
            counts[mode][n]=board_time_counts();
            pins[mode][n]=(uint8_t)((PDPR0>>4)&15U);
        }
        captured++;
    }
    /* Confirm the chip's normal interface before reconnecting MCU outputs.
     * A failed restoration deliberately leaves all four pins as inputs. */
    if(!tuner_write_register(0x62,0xe8,e8) &&
       !tuner_read_register(0x62,0xe8,&actual) && actual==e8 &&
       !tuner_read_register(0x62,0xf8,&check_f8) && check_f8==f8){
        PDCR1=0x2222U;
        PDIOR0=(uint16_t)((PDIOR0&~0xf0U)|(ior&0xf0U));
        restored=1;
    }
    field("PIN capture original_e8=",e8);field(" original_f8=",f8);
    field(" restored=",restored);uart_puts("\n");
    uart_puts("PIN capture counts=CMT nominal_hz=0044aa20 timestamp-before-gpio; nonuniform; bit0=PD4 bit3=PD7\n");
    /* Print only after restoration, never while sampling. */
    for(unsigned mode=0;mode<captured;mode++){
        unsigned transitions=0,changed=0;
        for(unsigned n=0;n<SAMPLES;n++){
            if(n){unsigned diff=pins[mode][n]^pins[mode][n-1];changed|=diff;if(diff)transitions++;}
            field("PIN sample mode=",mode?0:2);field(" index=",n);
            field(" counts=",counts[mode][n]);field(" value=",pins[mode][n]);uart_puts("\n");
        }
        field("PIN summary mode=",mode?0:2);field(" transitions=",transitions);
        field(" changed_bits=",changed);uart_puts("\n");
    }
    if(!restored)uart_puts("PIN capture end status=restore-failed-inputs-retained\n");
    else if(failed)uart_puts("PIN capture end status=capture-failed-restored\n");
    else uart_puts("PIN capture end status=captured-restored-unclassified\n");
}

/* Register portion of same-family tunerx_chkpin cases 1/2. The library
 * also conditionally calls tuning(0,13): bandToken[0]="UF" and
 * opeStatMap[0]=0x1321. This diagnostic retains the caller's full-seg
 * tuning; channel 13 can be selected through the existing profile command.
 * These recipes do not identify an IQ source or an electrical pin map. */
static const struct {uint8_t bank,reg,mask,value;} pin_test_fields[]={
    {0x62,0xe8,0x0f,0x00},{0x62,0xf8,0x0f,0x00},{0x60,0xac,0x04,0x04},
    {0x61,0xd7,0x70,0x70},{0x61,0xda,0x38,0x08},{0x61,0xdb,0xff,0x00},
    {0x61,0xdc,0xff,0x00},{0x61,0xdd,0x0f,0x00},{0x61,0xe7,0x71,0x31}
};
#define TEST_FIELDS 9U
static int pin_test_update(unsigned index,uint8_t value,uint8_t *readback){
    uint8_t current;
    unsigned bank=pin_test_fields[index].bank,reg=pin_test_fields[index].reg;
    unsigned mask=pin_test_fields[index].mask;
    if(tuner_read_register(bank,reg,&current))return -1;
    uint8_t desired=(uint8_t)((current&~mask)|(value&mask));
    if(tuner_write_register(bank,reg,desired) || tuner_read_register(bank,reg,readback))return -1;
    return ((*readback^desired)&mask)?-1:0;
}
void tuner_pin_test_probe(void){
    uint8_t original[TEST_FIELDS],after[TEST_FIELDS]={0},actual,system,profile;
    unsigned captured=0,failed=0,restored=1;
    uart_puts("PINTST capture start PD4..7 input-only\n");
    if((R32(0xfffe100cUL)&1U) || (R32(0xfffe101cUL)&1U) ||
       (R8(0xffff8800UL)&0x40U) || PDCR1!=0x2222U){
        uart_puts("PINTST capture end status=refused-mcu-state\n");return;
    }
    if(tuner_read_register(0x62,0xf2,&system) || tuner_read_register(0x61,0xed,&profile)){
        uart_puts("PINTST capture end status=i2c-failed-before-change\n");return;
    }
    for(unsigned n=0;n<TEST_FIELDS;n++){
        if(tuner_read_register(pin_test_fields[n].bank,pin_test_fields[n].reg,&original[n])){
            uart_puts("PINTST capture end status=i2c-failed-before-change\n");return;
        }
    }
    if(system!=4 || profile!=0x16 || (original[0]&15U)!=2 ||
       (original[1]&15U)!=1 || (original[8]&0x71U)){
        uart_puts("PINTST capture end status=unexpected-tuner-state\n");return;
    }
    uint16_t ior=PDIOR0;
    PDIOR0&=(uint16_t)~0xf0U;PDCR1=0;
    /* Verify every register precondition before enabling the output test. */
    for(unsigned n=0;n<TEST_FIELDS-1;n++){
        if(pin_test_update(n,pin_test_fields[n].value,&actual)){failed=1;goto restore;}
    }
    for(unsigned test=0;test<2;test++){
        if((test && pin_test_update(5,0xf9,&actual)) ||
           pin_test_update(8,test?0x21:0x31,&actual)){failed=1;break;}
        for(unsigned n=0;n<SAMPLES;n++){
            counts[test][n]=board_time_counts();pins[test][n]=(uint8_t)((PDPR0>>4)&15U);
        }
        captured++;
    }
restore:
    /* Stop the test first, restore interface before IRQ enables last.
     * Attempt every field even after a failed/uncertain write. Only the
     * owned masked bits are restored; current unrelated bits are retained. */
    {
        static const uint8_t order[TEST_FIELDS]={8,5,4,3,2,1,0,7,6};
        for(unsigned n=0;n<TEST_FIELDS;n++){
            unsigned index=order[n];
            if(pin_test_update(index,original[index],&after[index]))restored=0;
        }
    }
    if(restored){PDCR1=0x2222U;PDIOR0=(uint16_t)((PDIOR0&~0xf0U)|(ior&0xf0U));}
    for(unsigned n=0;n<TEST_FIELDS;n++){
        field("PINTST restore bank=",pin_test_fields[n].bank);field(" reg=",pin_test_fields[n].reg);
        field(" mask=",pin_test_fields[n].mask);field(" before=",original[n]);field(" after=",after[n]);uart_puts("\n");
    }
    uart_puts("PINTST counts=CMT nominal_hz=0044aa20 timestamp-before-gpio; nonuniform\n");
    for(unsigned test=0;test<captured;test++){
        unsigned transitions=0,changed=0;
        for(unsigned n=0;n<SAMPLES;n++){
            if(n){unsigned diff=pins[test][n]^pins[test][n-1];changed|=diff;if(diff)transitions++;}
            field("PINTST sample case=",test+1);field(" index=",n);
            field(" counts=",counts[test][n]);field(" value=",pins[test][n]);uart_puts("\n");
        }
        field("PINTST summary case=",test+1);field(" transitions=",transitions);
        field(" changed_bits=",changed);uart_puts("\n");
    }
    if(!restored)uart_puts("PINTST capture end status=restore-failed-inputs-retained\n");
    else if(failed)uart_puts("PINTST capture end status=capture-failed-restored\n");
    else uart_puts("PINTST capture end status=captured-restored-unclassified\n");
}
