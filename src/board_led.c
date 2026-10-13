/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "board_led.h"
static int strap=-1;
static unsigned manual,state_now,applied=~0U;
static uint32_t dr_address;
static unsigned dr_shift;
static void bits(uint32_t address,unsigned clear,unsigned set){
    R8(address)=(uint8_t)((R8(address)&~clear)|set);
}
int board_led_init(void){
    /* (PBDR0>>7)&7 with PBDR0 big endian at 0xfffe3836: bits 9,8 are the low bits of the first byte. */
    unsigned type=(((unsigned)R8(0xfffe3836UL)&3U)<<1)|((unsigned)R8(0xfffe3837UL)>>7);
    if(type&1U){            /* PB12/PB13 */
        bits(0xfffe3829UL,0x33,0);bits(0xfffe3832UL,0,0x30);bits(0xfffe3836UL,0,0x30);
        dr_address=0xfffe3836UL;dr_shift=4;
    }else if(type==0){      /* PC3/PC4 */
        bits(0xfffe384eUL,0x30,0);R8(0xfffe384cUL)=0;R8(0xfffe384dUL)=0;bits(0xfffe3853UL,0,0x18);bits(0xfffe3857UL,0,0x18);
        dr_address=0xfffe3857UL;dr_shift=3;
    }else if(type==2){      /* PE0/PE1 */
        bits(0xfffe388fUL,0x33,0);bits(0xfffe3893UL,0,3);bits(0xfffe3897UL,0,3);
        dr_address=0xfffe3897UL;dr_shift=0;
    }else{strap=-1;return -1;}
    strap=(int)type;applied=~0U;return strap;
}
static void drive(unsigned led,unsigned on){
    if(strap<0 || led>1)return;
    unsigned bit=1U<<(dr_shift+led);
    bits(dr_address,bit,on?0:bit);   /* low = lit */
}
static void apply(unsigned pattern){
    if(pattern==applied)return;
    applied=pattern;drive(0,pattern&1U);drive(1,(pattern>>1)&1U);
}
void board_led_set(unsigned led,unsigned on){
    manual=1;if(strap<0)return;
    drive(led,on);
}
void board_led_auto(void){manual=0;applied=~0U;}
void board_led_state(unsigned state){state_now=state;}
void board_led_service(unsigned now,int connected){
    if(manual || strap<0)return;
    unsigned slow=(now/500U)&1U,fast=(now/100U)&1U,pattern=0;
    switch(state_now){
    case BOARD_LED_BUSY:pattern=2;break;
    /* Ready and connected (including while receiving): green steady. Ready but nobody is
     * connected: green blinks slowly, so a blinking LED means "up, waiting for a client". */
    case BOARD_LED_READY:pattern=(connected || slow)?1U:0U;break;
    case BOARD_LED_FAILED:pattern=fast?3U:0U;break;
    default:pattern=0;
    }
    apply(pattern);
}
