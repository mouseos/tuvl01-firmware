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
