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
