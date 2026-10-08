/* SPDX-License-Identifier: MIT. SH726A USB function, EP0 polling only.
 * Provisional 0xffff:0001 is for local experiments; no assigned VID/PID. */
#include "board.h"
#include "usb.h"
#include "string.h"
#define U(o) R16(0xffffc000UL+(o))
/* SH726A/B manual 27.3.1. DCFM is bit 6; bit 5 is DRPD. */
#define SYSCFG_DCFM (1U<<6)
static const uint8_t device[]={18,1,0,2,0,0,0,64,0xff,0xff,1,0,0,1,1,2,0,1};
/* Battery-powered experiment; declares 500mA maximum, draw not yet measured. */
static const uint8_t config[]={9,2,18,0,1,1,0,0xc0,250,9,4,0,0,0,0xff,0,0,0};
static uint8_t reply[256],rx[64];
static unsigned remain,pos,need_zlp,out_len,configured,attached,receiving;
static uint32_t setup_count,state_count,stall_count,fifo_timeout_count,sequence_error_count;
static int fifo(unsigned transmit) {
    unsigned sel=0x100|(transmit?0x20:0); /* MBW=8, BIGEND=1 */
    U(0x20)=sel;
    unsigned t=10000;
    while((U(0x20)&0x43f)!= (sel&0x43f) && --t) {}
    if(!t){fifo_timeout_count++;return -1;}
    t=10000;while(!(U(0x22)&0x2000) && --t) {}
    if(!t)fifo_timeout_count++;
    return t?0:-1;
}
static void stall(void) { unsigned c=U(0x60);U(0x60)=(c&~3)|((c&3)==1?3:2);receiving=0;remain=0;need_zlp=0;stall_count++; }
static void complete(void) { U(0x60)=(U(0x60)&~3)|5; }
static void send(void) {
    if(fifo(1)){stall();return;}
    unsigned n=remain>64?64:remain;
    /* Manual table27.7: MBW=8 permits only bits7..0 (BE address +1). */
    for(unsigned i=0;i<n;i++)R8(0xffffc015)=reply[pos++];
    remain-=n;
    if(n<64) {U(0x22)=0x8000;need_zlp=0;}
    U(0x60)=(U(0x60)&~3)|1;
}
static int string(unsigned which) {
    if(!which){reply[0]=4;reply[1]=3;reply[2]=9;reply[3]=4;return 4;}
    const char *s=which==1?"Independent development":which==2?"TUVL01 recovery":0;
    if(!s)return -1;
    unsigned n=2;while(*s){reply[n++]=*s++;reply[n++]=0;}
    reply[0]=n;reply[1]=3;return n;
}
static void setup(void) {
    setup_count++;
    unsigned req=U(0x54),type=req&255,r=req>>8,v=U(0x56),idx=U(0x58),len=U(0x5a);
    remain=pos=need_zlp=receiving=0;
    U(0x60)&=(uint16_t)~3;
    if(fifo(1)){stall();return;}
    U(0x22)=0x4000;
    U(0x40)=(uint16_t)~8; /* clear VALID before CCPL */
    int n=-1;
    if((type&0x60)==0) {
        if(type==0x80 && r==6){
            if((v>>8)==1 && !(v&255) && !idx){memcpy(reply,device,sizeof device);n=sizeof device;}
            else if((v>>8)==2 && !(v&255) && !idx){memcpy(reply,config,sizeof config);n=sizeof config;}
            else if((v>>8)==3 && (!idx || idx==0x409))n=string(v&255);
        } else if(type==0 && r==5 && v<128 && !idx && !len) n=0; /* hardware address */
        else if(type==0 && r==9 && v<=1 && !idx && !len){configured=v;n=0;}
        else if(type==0x80 && r==8 && !v && !idx && len==1){reply[0]=configured;n=1;}
        else if((type==0x80 || (type==0x81 && !idx)) && r==0 && !v && len==2){reply[0]=type==0x80?1:0;reply[1]=0;n=2;}
        else if(type==0x81 && configured && r==10 && !idx && !v && len==1){reply[0]=0;n=1;}
        else if(type==1 && configured && r==11 && !idx && !v && !len)n=0;
    } else if(type==0x40 || type==0xc0) n=usb_request(type,r,v,idx,len,reply);
    if(n<0 || n>256){stall();return;}
    if(type&0x80) {
        remain=(unsigned)n<len?(unsigned)n:len;
        need_zlp=(unsigned)n<len && (remain&63)==0;
        send();
    } else if(len) {
        if(len>64 || n){stall();return;}
        out_len=len;receiving=1;
        if(fifo(0)){stall();return;}
        U(0x22)=0x4000;
        U(0x60)=(U(0x60)&~3)|1;
    } else complete();
}
void usb_init(void) {
    R8(0xfffe0414)&=(uint8_t)~1;(void)R8(0xfffe0414);
    R16(0xfffe38ce)=(R16(0xfffe38ce)&~0x33)|0x11;
    R16(0xfffe38ee)=(R16(0xfffe38ee)&~3)|3; /* PH0 VBUS, route unmeasured */
    U(0)=0x400; (void)U(0);U(0)=0x401;
    U(0x30)=0;U(0x32)=0;U(0x36)=1;U(0x38)=0;U(0x3a)=1;
    U(0x5c)=0;U(0x5e)=64;U(0x60)=0x100;
    configured=attached=0;
    setup_count=state_count=stall_count=fifo_timeout_count=sequence_error_count=0;
    uart_puts("USB VBSTS=");uart_hex(U(0x40)&0x80);uart_puts("\n");
}
static void disconnect_wait(void) {
    /* At the maximum supported 216 MHz, 512 NOPs alone exceed 1 us.
     * This wait also covers the 200 ns interval in manual 27.4.1(3). */
    for(unsigned n=0;n<512;n++)__asm__ volatile("nop");
}
void usb_detach(void){
    U(0)&=(uint16_t)~0x10;(void)U(0);
    attached=configured=0;
    remain=receiving=need_zlp=0;
    /* External D+ pullup switching still needs an identified board circuit. */
}
static void vbus_disconnect(void) {
    /* SH726A/B manual 27.4.1(3): DPRPU=0, >=1 us, DCFM=1,
     * >=200 ns, DCFM=0. Only perform the host-mode pulse on VBUS loss. */
    usb_detach();disconnect_wait();
    U(0)|=SYSCFG_DCFM;(void)U(0);disconnect_wait();
    U(0)&=(uint16_t)~SYSCFG_DCFM;(void)U(0);
}
unsigned usb_configured(void){return configured;}
void usb_pin_debug(void) {
    /* Manual 31.6: PGPR reads zero in USB mode. PG0/1 are input-only
     * GPIOs. Only sample before any SETUP, with no assigned USB address. */
    if(configured || setup_count || (U(0x50)&0x7f)) {
        uart_puts("USB GPIO sample skipped: host activity\n");return;
    }
    uint16_t mux=R16(0xfffe38ce);
    R16(0xfffe38ce)=mux&~0x33;
    (void)R16(0xfffe38ce);
    for(unsigned n=0;n<32;n++)__asm__ volatile("nop");
    unsigned pins=R16(0xfffe38da)&3;
    R16(0xfffe38ce)=mux;(void)R16(0xfffe38ce);
    uart_puts("USB GPIO input PG1_DP_PG0_DM=");uart_hex(pins);
    uart_puts(" restored_PGCR=");uart_hex(R16(0xfffe38ce));uart_puts("\n");
}
void usb_debug(void) {
    uart_puts("USB diag SYSCFG=");uart_hex(U(0));uart_puts(" SYSSTS=");uart_hex(U(4));
    uart_puts(" INTSTS0=");uart_hex(U(0x40));uart_puts(" USBADDR=");uart_hex(U(0x50));
    uart_puts(" FRMNUM=");uart_hex(U(0x4c));uart_puts(" DCPCTR=");uart_hex(U(0x60));uart_puts("\n");
    uart_puts("USB events setup=");uart_hex(setup_count);uart_puts(" state=");uart_hex(state_count);
    uart_puts(" stall=");uart_hex(stall_count);uart_puts(" fifo_timeout=");uart_hex(fifo_timeout_count);
    uart_puts(" sequence_error=");uart_hex(sequence_error_count);uart_puts(" configured=");uart_hex(configured);uart_puts("\n");
    /* PA0 is MD_CLK while reset is asserted; this is the current pin level,
       not a hardware latch readback. Do not change its direction or output. */
    uart_puts("CLOCK FRQCR=");uart_hex(R16(0xfffe0010));uart_puts(" STBCR6=");uart_hex(R8(0xfffe0414));
    uart_puts(" PAIOR0=");uart_hex(R16(0xfffe3812));uart_puts(" PAPR0=");uart_hex(R16(0xfffe381a)&3);uart_puts("\n");
}
void usb_poll(void) {
    unsigned s=U(0x40);
    if(!(s&0x80)){
        if(attached){
            vbus_disconnect();
            uart_puts("USB VBUS lost SYSCFG=");uart_hex(U(0));uart_puts("\n");
        }
        return;
    }
    /* DPRPU reports resistor state; SH726A requires an external pullup.
     * Board GPIO/transistor control remains unconfigured until identified. */
    if(!attached){
        U(0)|=0x10;attached=1;
        uart_puts("USB attach SYSCFG=");uart_hex(U(0));uart_puts(" SYSSTS=");uart_hex(U(4));
        uart_puts(" PGCR=");uart_hex(R16(0xfffe38ce));uart_puts(" PHCR=");uart_hex(R16(0xfffe38ee));
        uart_puts("\nUSB external pullup control unconfigured\n");
    }
    if(s&0x1000){state_count++;U(0x40)=(uint16_t)~0x1000;if(((s>>4)&7)==1){configured=0;remain=receiving=need_zlp=0;}}
    if(s&8){setup();return;}
    if(U(0x46)&1){
        U(0x46)=0x3fe;
        if(receiving){
            if(fifo(0)){stall();return;}
            unsigned n=U(0x22)&0x1ff;
            if(n!=out_len || n>64){U(0x22)=0x4000;stall();return;}
            for(unsigned i=0;i<n;i++)rx[i]=R8(0xffffc015);
            U(0x22)=0x4000;receiving=0;
            if(usb_out(rx,n))stall();else complete();
        }
    }
    if(U(0x4a)&1){U(0x4a)=0x3fe;if(remain || need_zlp)send();}
    if(s&0x800){
        unsigned stage=s&7;
        U(0x40)=(uint16_t)~0x800;
        if(stage==2 || stage==4)complete();
        else if(stage==0)usb_idle();
        else if(stage==6){sequence_error_count++;stall();}
    }
    if(!(U(0x40)&15))usb_idle();
}
