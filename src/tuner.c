/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "tuner.h"
#include "tuner_tables.h"
#include "tuner_pseq.h"

/* SH726A RIIC3, byte accesses. PE7=SDA3, PE6=SCL3.
 * Polling follows hardware manual 19.4.2/19.4.3; no stock RTOS code. */
#define I(n) R8(0xfffeec00UL+(n))
static const char *failure_phase;
static unsigned started,controller_ready;
static void value(const char *name,unsigned v){uart_puts(name);uart_hex(v);}
static void board_registers(void){
    value("TUNER GPIO PBCR3=",R16(0xfffe3828UL));
    value(" PBCR4=",R16(0xfffe3826UL));
    value(" PBIOR0=",R16(0xfffe3832UL));value(" PBDR0=",R16(0xfffe3836UL));
    value(" PBIOR1=",R16(0xfffe3830UL));value(" PBDR1=",R16(0xfffe3834UL));uart_puts("\n");
    value("TUNER GPIO PDCR0=",R16(0xfffe386eUL));
    value(" PDIOR0=",R16(0xfffe3872UL));value(" PDDR0=",R16(0xfffe3876UL));uart_puts("\n");
}
static void registers(void){
    value("TUNER RIIC3 STBCR8=",R8(0xfffe041cUL));uart_puts("\n");
    value("TUNER RIIC3 ICCR1=",I(0));value(" ICCR2=",I(1));
    value(" ICMR=",I(2));value(" ICIER=",I(3));
    value(" ICSR=",I(4));value(" NF2CYC=",I(8));uart_puts("\n");
}
static int wait_bits(unsigned reg,unsigned mask,unsigned expected,const char *phase){
    TickType_t begin=xTaskGetTickCount();
    for(;;){
        unsigned status=I(4);
        if(status&4){failure_phase="arbitration-lost";return -1;}
        if((I(reg)&mask)==expected)return 0;
        if((TickType_t)(xTaskGetTickCount()-begin)>=pdMS_TO_TICKS(100)){
            failure_phase=phase;return -1;
        }
        vTaskDelay(1);
    }
}
static int start(void){
    if(wait_bits(1,0x80,0,"bus-busy"))return -1;
    I(0)|=0x30;I(1)=(I(1)&~0x40)|0x80;started=1;
    return 0;
}
static int send_byte(uint8_t byte,const char *phase){
    if(wait_bits(4,0x80,0x80,"tx-empty"))return -1;
    I(6)=byte;
    if(wait_bits(4,0x40,0x40,"tx-end"))return -1;
    if(I(3)&2){failure_phase=phase;return -1;}
    return 0;
}
static int stop(void){
    I(4)&=(uint8_t)~0x48;
    I(1)&=0x3f;
    int result=wait_bits(4,8,8,"stop");
    I(0)&=(uint8_t)~0x70;I(4)&=(uint8_t)~0x80;
    started=0;return result;
}
static void controller_init(void){
    failure_phase=0;started=0;
    /* Manual 32.2.8: channel3 uses STBCR8/MSTP81, not the channel1 gate. */
    R8(0xfffe041cUL)&=(uint8_t)~2;
    (void)R8(0xfffe041cUL);
    R16(0xfffe388cUL)=(R16(0xfffe388cUL)&~0x3300)|0x1100;
    /* Reset only RIIC3, never the tuner/reset GPIO or unrelated pin functions. */
    I(0)=0;I(1)|=2;vTaskDelay(1);I(1)&=(uint8_t)~2;
    I(3)=0;I(4)=0;I(5)=0;I(8)=0;I(2)=0x30;I(0)=0xb5;
    controller_ready=1;
}
static int transaction_failure(unsigned address,unsigned reg){
    value("TUNER I2C failure address=",address);value(" register=",reg);
    uart_puts(" phase=");uart_puts(failure_phase?failure_phase:"unknown");uart_puts("\n");
    registers();if(started)(void)stop();controller_ready=0;return -1;
}
int tuner_read_register(unsigned address,unsigned reg,uint8_t *byte){
    if(address<0x60 || address>0x62 || reg>255 || !byte)return -1;
    if(!controller_ready)controller_init();
    failure_phase=0;
    /* Pointer write and STOP before read match the board's known protocol. */
    if(start() || send_byte(address<<1,"write-address-NACK") ||
       send_byte(reg,"register-pointer-NACK") || stop())goto failed;
    if(start() || send_byte((address<<1)|1,"read-address-NACK"))goto failed;
    I(4)&=(uint8_t)~0x40;I(0)&=(uint8_t)~0x10;
    I(4)&=(uint8_t)~0x80;
    I(0)|=0x40;I(3)|=1; /* single-byte RCVD and final NACK before dummy read */
    (void)I(7);
    if(wait_bits(4,0x20,0x20,"rx-full"))goto failed;
    I(4)&=(uint8_t)~8;I(1)&=0x3f;
    if(wait_bits(4,8,8,"rx-stop"))goto failed;
    *byte=I(7);
    I(0)&=(uint8_t)~0x70;started=0;
    return 0;
failed:
    return transaction_failure(address,reg);
}
static int write_chunk(unsigned address,unsigned reg,const uint8_t *bytes,unsigned count){
    if(address<0x60 || address>0x62 || reg>255 || !bytes || !count || count>128)return -1;
    if(!controller_ready)controller_init();
    failure_phase=0;
    if(start() || send_byte(address<<1,"write-address-NACK") ||
       send_byte(reg,"register-pointer-NACK"))
        return transaction_failure(address,reg);
    for(unsigned n=0;n<count;n++)
        if(send_byte(bytes[n],"data-NACK"))return transaction_failure(address,reg);
    if(stop())return transaction_failure(address,reg);
    return 0;
}
int tuner_write_register(unsigned address,unsigned reg,uint8_t byte){
    return write_chunk(address,reg,&byte,1);
}
void tuner_probe(void){
    uint8_t byte;
    uart_puts("TUNER probe start\n");controller_init();registers();
    if(tuner_read_register(0x61,0x8b,&byte)){
        uart_puts("TUNER probe end status=failed\n");return;
    }
    value("TUNER address=",0x61);value(" register=",0x8b);value(" value=",byte);
    uart_puts("\nTUNER probe end status=read\n");
}
static int read_log(unsigned address,unsigned reg,uint8_t *byte){
    if(tuner_read_register(address,reg,byte))return -1;
    value("TUNER read address=",address);value(" register=",reg);value(" value=",*byte);uart_puts("\n");
    return 0;
}
static int write_log(unsigned address,unsigned reg,uint8_t byte){
    if(tuner_write_register(address,reg,byte))return -1;
    value("TUNER write ACK address=",address);value(" register=",reg);value(" value=",byte);uart_puts("\n");
    return 0;
}
static int analog_prepare(void){
    uint8_t byte;
    if(read_log(0x60,0xd6,&byte))goto failed;
    if(read_log(0x60,0x95,&byte))goto failed;
    if(!byte){
        static const uint8_t setup[][2]={{0x32,7},{0x6d,7},{0x6e,0x39},{0x4c,0x10},{0x94,0x12},{0x95,0x14}};
        for(unsigned n=0;n<sizeof setup/sizeof setup[0];n++)
            if(write_log(0x60,setup[n][0],setup[n][1]))goto failed;
    }
    if(write_log(0x60,0x30,0x21) || read_log(0x60,0x30,&byte))goto failed;
    if(byte!=0x21){uart_puts("TUNER analog 30 readback mismatch\n");goto failed;}
    if(read_log(0x60,0x97,&byte) || write_log(0x60,0x97,2) ||
       read_log(0x60,0x97,&byte) || write_log(0x60,0x97,3) ||
       read_log(0x60,0x97,&byte))goto failed;
    return 0;
failed:
    return -1;
}
void tuner_analog(void){
    uart_puts("TUNER analog start\n");controller_init();
    uint8_t byte;
    if(analog_prepare())goto failed;
    /* This is the common PLL/ADC stage. Register tables and calibration
     * activation from the complete initialization sequence are still pending. */
    vTaskDelay(pdMS_TO_TICKS(250));
    for(unsigned attempt=0;attempt<5;attempt++){
        if(read_log(0x60,0xd6,&byte))goto failed;
        if(byte&1){uart_puts("TUNER analog end status=calibrated\n");return;}
        if(attempt<4)vTaskDelay(pdMS_TO_TICKS(100));
    }
    uart_puts("TUNER analog end status=configured-unready\n");return;
failed:
    uart_puts("TUNER analog end status=failed\n");
}
void tuner_board_probe(void){
    uart_puts("TUNER board preparation start\n");board_registers();
    /* Board setup observed before stock tuner command registration, checked
     * against instruction bytes and manual GPIO fields. Roles of individual
     * nets remain unmeasured. Preload output latches before enabling outputs. */
    R16(0xfffe3836UL)=(R16(0xfffe3836UL)&~0x8000)|0x4000;
    R16(0xfffe3828UL)&=(uint16_t)~0x3300;
    R16(0xfffe3832UL)|=0xc000;
    R16(0xfffe3834UL)|=1;R16(0xfffe3826UL)&=(uint16_t)~3;
    R16(0xfffe3830UL)|=1;
    R16(0xfffe3876UL)|=2;R16(0xfffe386eUL)&=(uint16_t)~0x70;
    R16(0xfffe3872UL)|=2;
    vTaskDelay(pdMS_TO_TICKS(100));
    R16(0xfffe3876UL)&=(uint16_t)~2;
    vTaskDelay(pdMS_TO_TICKS(100));
    R16(0xfffe3876UL)|=2;
    vTaskDelay(pdMS_TO_TICKS(100));
    board_registers();uart_puts("TUNER board preparation end status=configured\n");
    tuner_probe();
}
/* Read-only dump of the SH726A port/PFC register block 0xfffe3800..0xfffe38ff, 16 bit words.
 * No register is written. Used to see pin functions and levels before any pin is driven. */
void tuner_gpio_dump(void){
    uart_puts("GPIO dump start\n");
    for(unsigned line=0;line<16;line++){
        value("GPIO ",0xfffe3800UL+line*16);
        for(unsigned w=0;w<8;w++){uart_puts(" ");uart_hex(R16(0xfffe3800UL+line*16+w*2)&0xffffU);}
        uart_puts("\n");
    }
    uart_puts("GPIO dump end status=read\n");
}
/* Temporarily drive one SH726A GPIO pin to look for an unknown control line (for example the
 * RF switch). Per port: IOR1=base+0, IOR0=+2, DR1=+4, DR0=+6, PR1=+8, PR0=+0xa (pins 16..31 and
 * 0..15). Safeguards: the output first takes the level the pin already has, so enabling it cannot
 * cause a glitch; a pin whose IOR bit does not stick does not exist; after the change the pin is
 * read back and any mismatch (another driver fights it) restores the original state at once; the
 * four tuner pins PB14/PB15/PB16/PD1 are refused; only one pin can be active until released. */
static const uint32_t gpio_port_base[8]={0xfffe3810UL,0xfffe3830UL,0xfffe3850UL,0xfffe3870UL,
                                         0xfffe3890UL,0xfffe38b0UL,0xfffe38d0UL,0xfffe38f0UL};
static struct{int active;unsigned port,pin,orig_dr,orig_ior;}gpio_drv;
static void gpio_regs(unsigned port,unsigned pin,uint32_t *ior,uint32_t *dr,uint32_t *pr){
    uint32_t b=gpio_port_base[port];unsigned hi=pin<16;
    *ior=b+(hi?2U:0U);*dr=b+(hi?6U:4U);*pr=b+(hi?0xaU:8U);
}
static void gpio_restore(void){
    uint32_t ior,dr,pr;unsigned bit=1U<<(gpio_drv.pin&15);
    gpio_regs(gpio_drv.port,gpio_drv.pin,&ior,&dr,&pr);
    R16(dr)=(uint16_t)((R16(dr)&~bit)|(gpio_drv.orig_dr?bit:0U));
    R16(ior)=(uint16_t)((R16(ior)&~bit)|(gpio_drv.orig_ior?bit:0U));
    gpio_drv.active=0;
}
void tuner_gpio_drive(void){
    uint8_t arg[3];unsigned got=0;TickType_t begin=xTaskGetTickCount();
    uart_puts("GPIO drive start\n");
    while(got<sizeof arg){
        int c=uart_getc();
        if(c>=0)arg[got++]=(uint8_t)c;
        else{
            if((TickType_t)(xTaskGetTickCount()-begin)>=pdMS_TO_TICKS(2000)){
                uart_puts("GPIO drive end status=transport-timeout\n");return;
            }
            vTaskDelay(1);
        }
    }
    unsigned port=arg[0],pin=arg[1],level=arg[2];
    if(port>7 || pin>31 || level>2){uart_puts("GPIO drive end status=rejected\n");return;}
    if((port==1 && (pin==14 || pin==15 || pin==16)) || (port==3 && pin==1)){
        uart_puts("GPIO drive end status=refused-tuner-pin\n");return;
    }
    if(gpio_drv.active){uart_puts("GPIO drive end status=refused-active\n");return;}
    uint32_t ior,dr,pr;unsigned bit=1U<<(pin&15);
    gpio_regs(port,pin,&ior,&dr,&pr);
    unsigned l0=(R16(pr)&bit)?1U:0U;
    gpio_drv.port=port;gpio_drv.pin=pin;
    gpio_drv.orig_dr=(R16(dr)&bit)?1U:0U;gpio_drv.orig_ior=(R16(ior)&bit)?1U:0U;
    if(gpio_drv.orig_ior){uart_puts("GPIO drive end status=refused-already-output\n");return;}
    unsigned want=level==2?(l0^1U):level;
    /* Same level first, then enable the output: no glitch on the pin. */
    R16(dr)=(uint16_t)((R16(dr)&~bit)|(l0?bit:0U));
    R16(ior)=(uint16_t)(R16(ior)|bit);
    if(!(R16(ior)&bit)){
        R16(dr)=(uint16_t)((R16(dr)&~bit)|(gpio_drv.orig_dr?bit:0U));
        uart_puts("GPIO drive end status=absent-pin\n");return;
    }
    gpio_drv.active=1;
    R16(dr)=(uint16_t)((R16(dr)&~bit)|(want?bit:0U));
    for(volatile unsigned n=0;n<400;n++)__asm__ volatile("nop");
    unsigned seen=(R16(pr)&bit)?1U:0U;
    value("GPIO drive port=",port);value(" pin=",pin);value(" before=",l0);value(" want=",want);value(" seen=",seen);
    uart_puts("\n");
    if(seen!=want){gpio_restore();uart_puts("GPIO drive end status=contention-restored\n");return;}
    uart_puts("GPIO drive end status=driven\n");
}
void tuner_gpio_release(void){
    if(!gpio_drv.active){uart_puts("GPIO release end status=none-active\n");return;}
    gpio_restore();uart_puts("GPIO release end status=restored\n");
}
/* Single-register diagnostic for the three MN885521 I2C banks. Four bytes
 * follow the command: op ('r' or 'w'), bank (0x60..0x62), register, value.
 * Registers 0xf0 and above (patch memory, reset, bank control) are refused. */
void tuner_reg_access(void){
    uint8_t arg[4];unsigned got=0;
    TickType_t begin=xTaskGetTickCount();
    uart_puts("REG access start\n");
    while(got<sizeof arg){
        int c=uart_getc();
        if(c>=0)arg[got++]=(uint8_t)c;
        else{
            if((TickType_t)(xTaskGetTickCount()-begin)>=pdMS_TO_TICKS(2000)){
                uart_puts("REG access end status=transport-timeout\n");return;
            }
            vTaskDelay(1);
        }
    }
    unsigned bank=arg[1],reg=arg[2];uint8_t before,after;
    if((arg[0]!='r' && arg[0]!='w') || bank<0x60 || bank>0x62 || (arg[0]=='w' && reg>=0xf0)){
        uart_puts("REG access end status=rejected\n");return;
    }
    if(tuner_read_register(bank,reg,&before)){uart_puts("REG access end status=i2c-failed\n");return;}
    value("REG bank=",bank);value(" reg=",reg);value(" before=",before);
    if(arg[0]=='w'){
        if(tuner_write_register(bank,reg,arg[3]) || tuner_read_register(bank,reg,&after)){
            uart_puts("\nREG access end status=i2c-failed\n");return;
        }
        value(" wrote=",arg[3]);value(" after=",after);
    }
    uart_puts("\nREG access end status=done\n");
}
/* Diagnostic for the stock board's PB14/PB15 complementary pair.
 * The pair is driven 1/0 by the stock tuner setup and 0/1 on its sleep path.
 * Which net reaches which control pin of the RF switch (U5) is unmeasured, so
 * only these two states are accepted. Pin function and direction must already
 * be configured by tuner_board_probe(); no other bit or register is changed. */
#define RFSW_PBDR0 0xfffe3836UL
#define RFSW_PBIOR0 0xfffe3832UL
#define RFSW_PBCR3 0xfffe3828UL
#define RFSW_BITS 0xc000U
void tuner_rf_switch(void){
    int mode=-1;
    TickType_t begin=xTaskGetTickCount();
    uart_puts("RF switch start\n");
    while(mode<0){
        mode=uart_getc();
        if(mode<0){
            if((TickType_t)(xTaskGetTickCount()-begin)>=pdMS_TO_TICKS(2000)){
                uart_puts("RF switch end status=no-argument\n");return;
            }
            vTaskDelay(1);
        }
    }
    unsigned dr=R16(RFSW_PBDR0),ior=R16(RFSW_PBIOR0),cr=R16(RFSW_PBCR3);
    value("RF switch before PBDR0=",dr);value(" PBIOR0=",ior);value(" PBCR3=",cr);
    uart_puts("\n");
    if(mode=='r'){uart_puts("RF switch end status=read\n");return;}
    if(mode=='l' || mode=='h'){
        /* PB16 only (PBDR1 bit 0): High in the stock tuner setup, Low on the
         * stock sleep path. Only an already configured output is changed. */
        unsigned d1=R16(0xfffe3834UL),i1=R16(0xfffe3830UL),c4=R16(0xfffe3826UL);
        value("RF switch PB16 before PBDR1=",d1);value(" PBIOR1=",i1);value(" PBCR4=",c4);uart_puts("\n");
        if(!(i1&1) || (c4&3)){uart_puts("RF switch end status=refused-not-configured\n");return;}
        R16(0xfffe3834UL)=(uint16_t)((R16(0xfffe3834UL)&~1U)|(mode=='h'?1U:0U));
        unsigned a1=R16(0xfffe3834UL);
        value("RF switch PB16 after PBDR1=",a1);uart_puts("\n");
        if((a1&1U)!=(mode=='h'?1U:0U)){uart_puts("RF switch end status=verify-failed\n");return;}
        uart_puts(mode=='h'?"RF switch end status=pb16-high\n":"RF switch end status=pb16-low\n");
        return;
    }
    if(mode!='s' && mode!='i' && mode!='a' && mode!='z'){uart_puts("RF switch end status=rejected\n");return;}
    if((ior&RFSW_BITS)!=RFSW_BITS || (cr&0x3300)){
        uart_puts("RF switch end status=refused-not-configured\n");return;
    }
    /* 's' = stock 1/0 (PB14=1, PB15=0); 'i' = inverse 0/1 (the stock sleep
     * state: the tuner stops answering on I2C); 'a' = 1/1 (only PB15 raised). */
    unsigned want=mode=='s'?0x4000U:mode=='i'?0x8000U:mode=='z'?0U:0xc000U;
    R16(RFSW_PBDR0)=(uint16_t)((R16(RFSW_PBDR0)&~RFSW_BITS)|want);
    unsigned after=R16(RFSW_PBDR0);
    value("RF switch after PBDR0=",after);uart_puts("\n");
    if((after&RFSW_BITS)!=want){
        uart_puts("RF switch end status=verify-failed\n");return;
    }
    uart_puts(mode=='s'?"RF switch end status=stock\n":
              mode=='i'?"RF switch end status=inverse\n":
              mode=='z'?"RF switch end status=zero\n":"RF switch end status=alt\n");
}

static int prepare_bank(unsigned bank){
    uint8_t byte;
    if(read_log(bank,0xf4,&byte) || write_log(bank,0xf4,0) ||
       write_log(bank,0xf5,0) || read_log(bank,0xf3,&byte) ||
       write_log(bank,0xf3,0x23) || write_log(0x62,0xd2,0) ||
       read_log(bank,0xf2,&byte) || write_log(bank,0xf2,0) ||
       read_log(bank,0xf2,&byte) || write_log(bank,0xf2,2) ||
       read_log(bank,0xf2,&byte) || write_log(bank,0xf2,3))return -1;
    return 0;
}
static int patch(unsigned index){
    unsigned offset=pseq_records[index].offset,count=pseq_records[index].count;
    unsigned bank=pseq_records[index].bank;
    const uint8_t *raw=pseq_bytes+offset;
    uint8_t byte;
    if(write_log(bank,0xf4,raw[0]) || write_log(bank,0xf5,raw[1]) ||
       read_log(bank,0xf3,&byte) || write_log(bank,0xf3,0xe3))return -1;
    for(unsigned pos=0;pos<count;){
        unsigned chunk=count-pos;if(chunk>128)chunk=128;
        /* F6 is a stream port: repeat the same register in each transaction. */
        if(write_chunk(bank,0xf6,raw+2+pos,chunk))return -1;
        pos+=chunk;
    }
    if(read_log(bank,0xf8,&byte))return -1;
    value("TUNER patch index=",index);value(" count=",count);
    value(" expected_parity=",raw[count+2]);value(" actual_parity=",(byte>>4)&1);
    if(((byte>>4)&1)!=raw[count+2]){uart_puts(" status=mismatch\n");return -1;}
    uart_puts(" status=verified\n");return 0;
}
void tuner_initialize(void){
    uart_puts("TUNER initialize start\n");
    /* Validate every record before changing the board or patch memory. */
    for(unsigned n=0;n<sizeof pseq_records/sizeof pseq_records[0];n++){
        unsigned off=pseq_records[n].offset,count=pseq_records[n].count,parity=0;
        if(off>sizeof pseq_bytes-3 || count>sizeof pseq_bytes-off-3 || !count ||
           (pseq_records[n].bank!=0x60 && pseq_records[n].bank!=0x61))goto failed;
        for(unsigned j=0;j<count;j++){
            unsigned bits=pseq_bytes[off+2+j];
            while(bits){parity^=bits&1;bits>>=1;}
        }
        if(parity!=pseq_bytes[off+count+2])goto failed;
    }
    tuner_board_probe();
    uint8_t byte;
    if(read_log(0x61,0x8b,&byte) || read_log(0x61,0x91,&byte) ||
       read_log(0x61,0x80,&byte) || read_log(0x61,0x82,&byte) || analog_prepare())goto failed;
    if(prepare_bank(0x61) || prepare_bank(0x60))goto failed;
    for(unsigned n=0;n<sizeof tuner_setup/sizeof tuner_setup[0];n++)
        if(write_log(tuner_setup[n][0],tuner_setup[n][1],tuner_setup[n][2]))goto failed;
    if(read_log(0x61,0xf8,&byte) || read_log(0x60,0xf8,&byte))goto failed;
    for(unsigned n=0;n<sizeof pseq_records/sizeof pseq_records[0];n++)
        if(patch(n))goto failed;
    if(read_log(0x61,0xf3,&byte) || write_log(0x61,0xf3,0xe3) ||
       read_log(0x61,0xf3,&byte) || write_log(0x61,0xf3,0xe0) ||
       write_log(0x60,0xf5,0) || read_log(0x60,0xf4,&byte) ||
       write_log(0x60,0xf4,0x27) || read_log(0x60,0xf3,&byte) ||
       write_log(0x60,0xf3,0xe3) || read_log(0x60,0xf3,&byte) ||
       write_log(0x60,0xf3,0xe0))goto failed;
    vTaskDelay(pdMS_TO_TICKS(250));
    for(unsigned attempt=0;attempt<5;attempt++){
        if(read_log(0x60,0xd6,&byte))goto failed;
        if(byte&1)break;
        if(attempt==4){uart_puts("TUNER initialize end status=calibration-timeout\n");return;}
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    if(read_log(0x60,0xcf,&byte) || read_log(0x60,0xd0,&byte) ||
       read_log(0x61,0xf1,&byte) || write_log(0x61,0xe8,2) ||
       write_log(0x62,4,4))goto failed;
    uart_puts("TUNER initialize end status=calibrated\n");return;
failed:
    uart_puts("TUNER initialize end status=failed\n");
}
