/* SPDX-License-Identifier: MIT */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "tuner.h"
#include "tuner_ts.h"
#include "image.h"
#include "sdio.h"
#include "ts_check.h"
#include "ts_pattern.h"

#define S(n) R8(0xffff8800UL+(n))
#define DMA(n,o) R32(0xfffe1000UL+16UL*(n)+(o))
#define DMAOR R16(0xfffe1200UL)
#define DMARS0 R16(0xfffe1300UL)
static unsigned ready;
static unsigned dma_verified;
static unsigned dma_long_verified;
static uint8_t spi_divider=2;
static const char *phase;
static uint8_t packets[TUNER_TS_PACKET*TUNER_TS_MAX_PACKETS];
static uint8_t capture[TUNER_TS_PACKET*128U];
static unsigned streaming,pending,position,sequence,packet_index,stream_flags,stream_over,stream_under,stream_busy;
static unsigned stream_read_ticks,stream_tx_ticks,stream_poll_ticks;
static unsigned stream_burst;
static unsigned stream_aggregate;
static unsigned stream_test_source;
static unsigned stream_frame_packets=7;
int tuner_ts_stream_active(void){return streaming!=0;}
void tuner_ts_stream_wifi_ticks(unsigned ticks){if(streaming)stream_poll_ticks+=ticks;}
static void field(const char *name,unsigned number);
void tuner_ts_stream_interrupt(void){if(streaming)tuner_ts_stream_stop();}
void tuner_ts_stream_stop(void){
    sdio_wifi_ts_timing_stop();
    streaming=0;pending=position=0;
    field("TS stream datagrams=",sequence);field(" packets=",packet_index);
    field(" overrun=",stream_over);field(" underrun=",stream_under);field(" busy=",stream_busy);uart_puts("\n");
    field("TS timing read_ticks=",stream_read_ticks);field(" tx_ticks=",stream_tx_ticks);
    field(" poll_ticks=",stream_poll_ticks);uart_puts("\nTS stream end status=stopped\n");
}
static void field(const char *name,unsigned number){uart_puts(name);uart_hex(number);}
static void registers(void){
    field("TS RSPI1 STBCR5=",R8(0xfffe0410UL));field(" PDCR1=",R16(0xfffe386cUL));
    field(" SPCR=",S(0));field(" SPSR=",S(3));field(" SPBR=",S(10));
    field(" SPPCR=",S(2));
    field(" SPDCR=",S(11));field(" SPCMD0=",R16(0xffff8810UL));
    field(" SPBFCR=",S(32));field(" SPBFDR=",R16(0xffff8822UL));uart_puts("\n");
}
static int wait_status(unsigned mask,const char *name){
    /* Fast byte transfers should not enter the RTOS tick critical section
     * twice per byte. Fall back to the original bounded wait if still busy. */
    for(unsigned n=0;n<64;n++){
        unsigned status=S(3);
        if(status&5){phase="overrun-or-mode-fault";return -1;}
        if((status&mask)==mask)return 0;
    }
    TickType_t begin=xTaskGetTickCount();
    for(;;){
        unsigned status=S(3);
        if(status&5){phase="overrun-or-mode-fault";return -1;}
        if((status&mask)==mask)return 0;
        if((TickType_t)(xTaskGetTickCount()-begin)>=pdMS_TO_TICKS(20)){
            phase=name;return -1;
        }
    }
}
static int failure(void){
    uart_puts("TS RSPI1 failure phase=");uart_puts(phase?phase:"unknown");uart_puts("\n");
    registers();S(0)=8;S(32)=0xc0;S(32)=0;S(3)=0;ready=0;return -1;
}
static void initialize(void){
    /* SH726A manual32.2.5: RSPI1 is MSTP50. The stock bit2 targets CAN1. */
    R8(0xfffe0410UL)&=(uint8_t)~1;(void)R8(0xfffe0410UL);
    S(0)=0;S(2)=0x20;S(10)=spi_divider;S(11)=0x20;
    S(12)=0;S(13)=0;S(14)=0;S(8)=0;
    R16(0xffff8810UL)=0xe780;S(32)=0xc0;S(32)=0;
    S(1)=0;S(3)=0;S(0)=8;ready=1;
    R16(0xfffe386cUL)=0x2222;
}
static int begin(void){
    if(!ready)initialize();
    phase=0;S(32)=0xc0;S(32)=0;S(0)=0x48;return 0;
}
static int exchange(uint8_t tx,uint8_t *rx){
    if(wait_status(0x20,"tx-space"))return -1;
    S(4)=tx;
    if(wait_status(0x80,"rx-data"))return -1;
    *rx=S(4);return 0;
}
static int end(void){
    if(wait_status(0x40,"transfer-end"))return failure();
    S(0)=8;return 0;
}
/* SH726A manual11.3/17.3: CH0 TX, CH1 RX, byte transfers. Requests
 * 55/56 use the extension selector. CPU interrupts remain disabled (IE=0);
 * RSPI SPTIE/SPRIE route peripheral requests to the selected DMA channels.
 * The UART task exclusively owns RSPI1; never borrow active DMA channels. */
static int dma_exchange(const uint8_t *tx,uint8_t *rx,unsigned size,unsigned increment,unsigned wide){
    uintptr_t source=(uintptr_t)tx,destination=(uintptr_t)rx;
    unsigned unit=wide?4:1;
    if(!size || size>6016 || source<0x1c000000UL || destination<0x1c000000UL ||
       source>0x1c100000UL-(increment?size:unit) || destination>0x1c100000UL-size ||
       (wide && ((source|destination|size)&3U))){
        phase="dma-buffer";return -1;
    }
    unsigned old_spdcr=S(11),old_bfcr=S(32),old_command=R16(0xffff8810UL);
    if(wide){
        if(wait_status(0x40,"dma-width-boundary"))return -1;
        if(R16(0xffff8822UL)){phase="dma-width-not-empty";return -1;}
        S(11)=0x60;S(32)=0x22;R16(0xffff8810UL)=0xe280;
    }
    uint8_t clock=R8(0xfffe0018UL);
    R8(0xfffe0018UL)=clock&~0x20U;(void)R8(0xfffe0018UL);
    unsigned old_or=DMAOR,old_select=DMARS0;
    if(old_or&6){phase="dma-existing-error";goto unavailable;}
    for(unsigned n=0;n<16;n++)if(DMA(n,12)&1){phase="dma-in-use";goto unavailable;}
    /* Reading before clearing acknowledges any prior TE/HE flag. */
    (void)DMA(0,12);(void)DMA(1,12);DMA(0,12)=0;DMA(1,12)=0;
    DMA(0,0)=source;DMA(0,4)=0xffff8804UL;DMA(0,8)=size/unit;
    DMA(1,0)=0xffff8804UL;DMA(1,4)=destination;DMA(1,8)=size/unit;
    DMARS0=0x5655;(void)DMARS0;
    DMAOR=old_or|1;(void)DMAOR;
    /* Arm the receiver first. Fixed zero source for TS; increment for test. */
    DMA(1,12)=0x4801|(wide?0x10:0);
    DMA(0,12)=(increment?0x1801:0x0801)|(wide?0x10:0);
    __asm__ volatile("" ::: "memory");
    S(0)|=0xa0;(void)S(0);
    TickType_t start=xTaskGetTickCount();int result=-1;
    for(;;){
        unsigned tx_control=DMA(0,12),rx_control=DMA(1,12);
        if(DMAOR&6){phase="dma-address-or-nmi";break;}
        if(S(3)&5){phase="dma-rspi-error";break;}
        if((tx_control&2) && (rx_control&2)){
            if(DMA(0,8) || DMA(1,8)){phase="dma-count";break;}
            result=0;break;
        }
        if((TickType_t)(xTaskGetTickCount()-start)>=pdMS_TO_TICKS(100)){
            phase="dma-timeout";break;
        }
    }
    /* Disable request generation before disabling channels, so cleanup cannot
     * leave a peripheral request routed to the CPU. Preserve other DMAOR bits
     * and any error flags for the diagnostic rather than silently clearing. */
    S(0)&=(uint8_t)~0xa0U;(void)S(0);
    DMA(0,12)&=~1U;DMA(1,12)&=~1U;
    if(result){
        field("TS DMA failure DMAOR=",DMAOR);field(" TX_CHCR=",DMA(0,12));
        field(" RX_CHCR=",DMA(1,12));field(" TX_remaining=",DMA(0,8));
        field(" RX_remaining=",DMA(1,8));uart_puts("\n");
    }
    (void)DMA(0,12);(void)DMA(1,12);
    DMA(0,12)=0;DMA(1,12)=0;
    DMARS0=old_select;(void)DMARS0;
    DMAOR=(DMAOR&~1U)|(old_or&1U);(void)DMAOR;
    __asm__ volatile("" ::: "memory");
    R8(0xfffe0018UL)=clock;(void)R8(0xfffe0018UL);
    if(wide){
        if(!result && wait_status(0x40,"dma-width-end"))result=-1;
        if(result){S(0)=8;S(32)=0xc0;S(32)=0;}
        S(11)=old_spdcr;S(32)=old_bfcr;R16(0xffff8810UL)=old_command;
    }
    return result;
unavailable:
    R8(0xfffe0018UL)=clock;(void)R8(0xfffe0018UL);
    if(wide){S(11)=old_spdcr;S(32)=old_bfcr;R16(0xffff8810UL)=old_command;}
    return -1;
}
void tuner_ts_dma_probe(void){
    static uint8_t tx[128],rx[128];static const uint8_t zero;
    uart_puts("TS DMA probe start\n");dma_verified=dma_long_verified=0;initialize();S(2)=0x21;
    for(unsigned n=0;n<sizeof tx;n++)tx[n]=(uint8_t)(n*37+11);
    begin();
    if(dma_exchange(tx,rx,sizeof rx,1,0) || end())goto failed;
    for(unsigned n=0;n<sizeof rx;n++)if(rx[n]!=(uint8_t)(tx[n]^0xffU)){
        phase="dma-pattern-mismatch";goto failed;
    }
    begin();
    if(dma_exchange(&zero,rx,sizeof rx,0,0) || end())goto failed;
    for(unsigned n=0;n<sizeof rx;n++)if(rx[n]!=0xff){phase="dma-dummy-mismatch";goto failed;}
    if(R16(0xffff8822UL)&0x3f){phase="dma-rx-not-empty";goto failed;}
    S(2)=0x20;dma_verified=1;registers();
    uart_puts("TS DMA probe end status=verified\n");return;
failed:
    S(2)=0x20;failure();uart_puts("TS DMA probe end status=failed\n");
}
void tuner_ts_dma_long_probe(void){
    static uint8_t tx[128] __attribute__((aligned(4))),rx[128] __attribute__((aligned(4)));
    static const uint32_t zero;
    uart_puts("TS DMA long start\n");
    if(dma_long_verified){dma_long_verified=0;uart_puts("TS DMA long selected=00000000\nTS DMA long end status=verified\n");return;}
    tuner_ts_dma_probe();
    if(!dma_verified)goto failed;
    S(2)=0x21;
    for(unsigned n=0;n<sizeof tx;n++)tx[n]=(uint8_t)(n*37+11);
    begin();
    if(dma_exchange(tx,rx,sizeof rx,1,1) || end())goto failed;
    for(unsigned n=0;n<sizeof rx;n++)if(rx[n]!=(uint8_t)(tx[n]^0xffU)){
        phase="dma-long-pattern";goto failed;
    }
    begin();
    if(dma_exchange((const uint8_t *)&zero,rx,sizeof rx,0,1) || end())goto failed;
    for(unsigned n=0;n<sizeof rx;n++)if(rx[n]!=0xff){phase="dma-long-dummy";goto failed;}
    if(R16(0xffff8822UL)){phase="dma-long-not-empty";goto failed;}
    S(2)=0x20;dma_long_verified=1;
    uart_puts("TS DMA long selected=00000001\nTS DMA long end status=verified\n");return;
failed:
    S(2)=0x20;failure();tuner_ts_dma_probe();
    uart_puts("TS DMA long end status=failed\n");
}
static void clock_select(uint8_t selected){
    uart_puts("TS clock start\n");
    uint8_t previous=spi_divider;
    spi_divider=selected;
    tuner_ts_dma_probe();
    if(dma_verified && S(10)==spi_divider){
        field("TS clock SPBR=",S(10));field(" Bphi_divisor=",2U*(spi_divider+1));uart_puts("\n");
        uart_puts("TS clock end status=verified-loopback\n");return;
    }
    spi_divider=previous;tuner_ts_dma_probe();
    field("TS clock restored_SPBR=",S(10));field(" restored_dma=",dma_verified);uart_puts("\n");
    uart_puts("TS clock end status=failed\n");
}
void tuner_ts_clock(void){clock_select(spi_divider==2?1:2);}
void tuner_ts_clock_max(void){
    static uint8_t previous=2;
    /* SH726A supports SPBR=0, BRDV=0 => Bphi/2. This opt-in diagnostic
     * does not establish the external tuner's supported input frequency. */
    if(spi_divider==0)clock_select(previous);
    else{previous=spi_divider;clock_select(0);}
}
static int status(uint8_t response[5]){
    static const uint8_t command[5]={3,0x10,0,0,0};
    begin();
    for(unsigned n=0;n<5;n++)if(exchange(command[n],response+n))return failure();
    return end();
}
static void response_log(const char *name,const uint8_t *bytes,unsigned count){
    uart_puts(name);
    for(unsigned n=0;n<count;n++)field(" byte=",bytes[n]);
    uart_puts("\n");
}
static int spi_config(void){
    uint8_t response[2];
    begin();
    if(exchange(1,response) || exchange(0xb1,response+1))return failure();
    if(end())return -1;
    response_log("TS SPI command=01B1 response",response,2);return 0;
}
static int synchronize_quiet(unsigned quiet){
    static const uint8_t command[4]={0xd8,0,0,0};
    uint8_t response[4];
    begin();
    for(unsigned n=0;n<4;n++)if(exchange(command[n],response+n))return failure();
    if(end())return -1;
    if(!quiet)response_log("TS SPI command=D8000000 response",response,4);
    return 0;
}
static int read_packets(uint8_t *buffer,unsigned max_packets,unsigned quiet){
    if(!buffer || !max_packets || max_packets>TUNER_TS_MAX_PACKETS)return -1;
    uint8_t response[5],discard;
    if(status(response))return -1;
    if(!quiet)response_log("TS FIFO response",response,5);
    int result=tuner_ts_classify(response[4]);
    if(result!=1)return result;
    uint8_t command[5]={0x0b,0,0,(uint8_t)(max_packets-1),0};
    begin();
    for(unsigned n=0;n<5;n++)if(exchange(command[n],&discard))return failure();
    /* Keep SSL asserted across command and payload; explicit dummy bytes,
     * drain RX per byte, no TXDMY or unbounded peripheral wait. */
    if(dma_verified){
        static const uint32_t zero;
        if(dma_exchange((const uint8_t *)&zero,buffer,max_packets*TUNER_TS_PACKET,0,dma_long_verified))return failure();
    }else for(unsigned n=0;n<max_packets*TUNER_TS_PACKET;n++)
        if(exchange(0,buffer+n))return failure();
    if(end())return -1;
    return (int)max_packets;
}
int tuner_ts_read(uint8_t *buffer,unsigned max_packets){return read_packets(buffer,max_packets,0);}
void tuner_ts_stream_start(void){
    uint8_t v;uart_puts("TS stream start\n");
    if(streaming){uart_puts("TS stream begin status=refused-active\n");return;}
    if(stream_test_source){
        if(ts_pattern_fill(packets,sizeof packets)!=32){uart_puts("TS stream begin status=failed\n");return;}
    }else if(tuner_read_register(0x61,0x97,&v) || (v&0x18)!=0x10 || synchronize_quiet(1)){
        uart_puts("TS stream begin status=failed\n");return;
    }
    pending=position=sequence=packet_index=stream_over=stream_under=stream_busy=stream_flags=0;
    stream_read_ticks=stream_tx_ticks=stream_poll_ticks=0;
    field("TS stream test_source=",stream_test_source);uart_puts("\n");
    field("TS stream packets_per_datagram=",stream_frame_packets);uart_puts("\n");
    streaming=1;uart_puts("TS stream begin status=active\n");
    sdio_wifi_io_start();
}
void tuner_ts_stream_test_source(void){
    if(streaming){uart_puts("TS test source end status=refused-active\n");return;}
    stream_test_source^=1;
    field("TS test source selected=",stream_test_source);uart_puts("\n");
    uart_puts("TS test source end status=selected\n");
}
void tuner_ts_stream_burst(void){
    if(streaming){uart_puts("TS burst end status=refused-active\n");return;}
    stream_burst^=1;
    field("TS burst selected=",stream_burst);uart_puts("\n");
    uart_puts("TS burst end status=selected\n");
}
void tuner_ts_stream_frame_size(void){
    if(streaming || stream_aggregate){uart_puts("TS frame size end status=refused-active\n");return;}
    stream_frame_packets=stream_frame_packets==7?1:stream_frame_packets==1?3:7;
    field("TS frame size selected=",stream_frame_packets);uart_puts("\nTS frame size end status=selected\n");
}
int tuner_ts_stream_aggregate_active(void){return stream_aggregate!=0;}
void tuner_ts_stream_aggregate(void){
    if(!stream_aggregate && sdio_wifi_raw_tx_selected()){uart_puts("TS aggregate end status=refused-raw-tx\n");return;}
    if(streaming){uart_puts("TS aggregate end status=refused-active\n");return;}
    if(stream_frame_packets!=7){uart_puts("TS aggregate end status=refused-frame-size\n");return;}
    stream_aggregate^=1;
    field("TS aggregate selected=",stream_aggregate);uart_puts("\n");
    uart_puts("TS aggregate end status=selected\n");
}
void tuner_ts_stream_poll(void){
    if(!streaming)return;
    if(!pending){
        TickType_t before=xTaskGetTickCount();
        int n=stream_test_source?32:read_packets(packets,32,1);
        stream_read_ticks+=(TickType_t)(xTaskGetTickCount()-before);
        if(!n)return;
        if(n<0){
            if(n==-3)stream_over++;else if(n==-2)stream_under++;
            else {tuner_ts_stream_stop();uart_puts("TS stream failure=bus-or-reserved\n");return;}
            stream_flags|=1;
            if(synchronize_quiet(1)){tuner_ts_stream_stop();return;}return;
        }
        pending=(unsigned)n;position=0;
    }
    /* Only drain this already-read batch; never read another batch here.
     * Five sends cover at most 32 TS packets. Credit stall/error returns
     * immediately, preserving the next unsent position on a stall. */
    unsigned limit=stream_burst?5:1;
    for(unsigned attempt=0;attempt<limit;attempt++){
        unsigned n=pending-position,maximum=stream_aggregate?14:stream_frame_packets;
        if(n>maximum)n=maximum;
        TickType_t before=xTaskGetTickCount();
        int sent=stream_aggregate?
            sdio_wifi_ts_pair(packets+position*188,n,sequence,packet_index,stream_flags):
            sdio_wifi_ts(packets+position*188,n,sequence,packet_index,stream_flags);
        stream_tx_ticks+=(TickType_t)(xTaskGetTickCount()-before);
        if(sent<0){tuner_ts_stream_stop();uart_puts("TS stream failure=wifi-tx\n");return;}
        if(!sent){stream_busy++;return;}
        unsigned accepted=stream_aggregate?(unsigned)sent:n;
        sequence+=(accepted+6)/7;packet_index+=accepted;position+=accepted;stream_flags=0;
        if(position==pending){pending=position=0;return;}
    }
}
void tuner_ts_benchmark(void){
    static struct ts_check check;
    unsigned empty=0,over=0,under=0,reserved=0,read_ticks=0;
    uint8_t byte;int result=-1;
    uart_puts("TS benchmark start\n");
    ts_check_reset(&check);
    if(tuner_read_register(0x61,0x97,&byte)){
        uart_puts("TS benchmark guard=frame-read-failed\n");goto failed;
    }
    if((byte&0x18)!=0x10){
        field("TS benchmark guard_raw97=",byte);uart_puts("\n");goto failed;
    }
    if(synchronize_quiet(1)){
        uart_puts("TS benchmark guard=fifo-sync-failed\n");goto failed;
    }
    TickType_t start=xTaskGetTickCount();
    while((TickType_t)(xTaskGetTickCount()-start)<pdMS_TO_TICKS(10000)){
        TickType_t before=xTaskGetTickCount();
        int n=read_packets(packets,32,1);
        read_ticks+=(TickType_t)(xTaskGetTickCount()-before);
        if(n>0){
            for(unsigned p=0;p<(unsigned)n;p++)ts_check_packet(&check,packets+p*188);
        }else if(!n){empty++;vTaskDelay(1);}
        else{
            if(n==-3)over++;else if(n==-2)under++;
            else if(n==-4){reserved++;goto failed;}else goto failed;
            if(synchronize_quiet(1))goto failed;
        }
    }
    result=0;
    field("TS benchmark ticks=",(TickType_t)(xTaskGetTickCount()-start));
    field(" read_ticks=",read_ticks);field(" dma=",dma_verified);field(" spbr=",S(10));
    field(" ccr1=",R32(0xfffc1000UL));uart_puts("\n");
    field("TS benchmark dma_long=",dma_long_verified);uart_puts("\n");
failed:
    field("TS benchmark packets=",check.packets);field(" empty=",empty);
    field(" overrun=",over);field(" underrun=",under);field(" reserved=",reserved);uart_puts("\n");
    field("TS benchmark sync=",check.sync);field(" tei=",check.tei);field(" adaptation=",check.adaptation);
    field(" comparisons=",check.comparisons);field(" cc_jumps=",check.cc_jumps);
    field(" cc_repeats=",check.cc_repeats);uart_puts("\n");
    uart_puts(result?"TS benchmark end status=failed\n":"TS benchmark end status=measured\n");
}
void tuner_ts_capture(void){
    uart_puts("TS capture start\n");
    unsigned count=0,empty=0,over=0,under=0,reserved=0;
    uint8_t byte;
    if(tuner_read_register(0x61,0x97,&byte) || !(byte&0x10) || (byte&8))goto failed;
    if(synchronize_quiet(1))goto failed;
    TickType_t start=xTaskGetTickCount();
    while(count<128 && (TickType_t)(xTaskGetTickCount()-start)<pdMS_TO_TICKS(2000)){
        int n=read_packets(capture+count*TUNER_TS_PACKET,32,1);
        if(n>0){count+=(unsigned)n;continue;}
        if(n==0){empty++;vTaskDelay(1);continue;}
        if(n==-3)over++;else if(n==-2)under++;else if(n==-4)reserved++;else goto failed;
        if(over+under+reserved>=8 || reserved)break;
        if(synchronize_quiet(1))goto failed;
    }
    /* No UART output while filling: printing per FIFO query can overrun it.
     * Hex transport happens only after this finite RAM capture has stopped. */
    static const char hex[]="0123456789abcdef";
    for(unsigned n=0;n<count;n++){
        uart_puts("TS DATA ");
        for(unsigned i=0;i<TUNER_TS_PACKET;i++){
            unsigned b=capture[n*TUNER_TS_PACKET+i];
            char text[3]={hex[b>>4],hex[b&15],0};uart_puts(text);
        }
        uart_puts("\n");
    }
    field("TS capture packets=",count);
    field(" crc=",~crc32_update(UINT32_MAX,capture,count*TUNER_TS_PACKET));
    field(" empty=",empty);field(" overrun=",over);field(" underrun=",under);field(" reserved=",reserved);uart_puts("\n");
    uart_puts(count?"TS capture end status=data-unverified\n":"TS capture end status=no-data\n");return;
failed:uart_puts("TS capture end status=failed\n");
}
void tuner_ts_probe(void){
    uart_puts("TS probe start\n");initialize();registers();
    uint8_t response[5];
    S(2)=0x21;
    if(status(response)){S(2)=0x20;goto failed;}
    response_log("TS loopback response",response,5);
    S(2)=0x20;
    static const uint8_t expected[5]={3,0x10,0,0,0};
    /* Manual17.3.3: SPLP connects the INVERTED output to the input. */
    for(unsigned n=0;n<5;n++)if(response[n]!=(uint8_t)(expected[n]^0xffU)){
        uart_puts("TS internal loopback mismatch\n");goto failed;
    }
    uart_puts("TS internal loopback status=verified\n");
    /* PD4 RSPCK1, PD5 SSL10, PD6 MOSI1, PD7 MISO1; PD1 untouched. */
    R16(0xfffe386cUL)=0x2222;
    if(status(response))goto failed;
    response_log("TS FIFO response",response,5);
    if(spi_config())goto failed;
    registers();uart_puts("TS probe end status=read\n");return;
failed:
    uart_puts("TS probe end status=failed\n");
}
void tuner_ts_enable(void){
    uart_puts("TS output start\n");
    uint8_t byte;
    if(tuner_read_register(0x60,0xd6,&byte) || !(byte&1))goto failed;
    static const uint8_t setup[][3]={
        {0x62,0xe8,2},{0x62,0xf8,1},{0x61,0xd9,1},{0x62,2,1},
        {0x62,0xef,1},{0x62,0xee,0x71},{0x62,0xed,1},{0x61,0xe2,9},
        {0x62,0xcd,9},{0x61,0xdc,1},{0x62,0xc7,1},{0x60,0xb1,1}
    };
    initialize();
    for(unsigned n=0;n<sizeof setup/sizeof setup[0];n++){
        if(tuner_write_register(setup[n][0],setup[n][1],setup[n][2]))goto failed;
        field("TS output ACK bank=",setup[n][0]);field(" reg=",setup[n][1]);field(" value=",setup[n][2]);uart_puts("\n");
        /* Stock TS begin: two I2C writes, SPI internal configuration,
         * remaining I2C writes, FIFO synchronize, then status/read. */
        if(n==1 && spi_config())goto failed;
    }
    if(synchronize_quiet(0))goto failed;
    int result=tuner_ts_read(packets,1);
    if(result<0){field("TS output read error=",(unsigned)-result);uart_puts("\n");goto failed;}
    field("TS packet count=",result);uart_puts("\n");
    if(result){
        field("TS first byte=",packets[0]);field(" header=",((unsigned)packets[1]<<16)|((unsigned)packets[2]<<8)|packets[3]);uart_puts("\n");
        /* One packet header is diagnostic, never proof of a received stream. */
        uart_puts("TS output end status=data-unverified\n");
    }else uart_puts("TS output end status=no-data\n");
    return;
failed:
    uart_puts("TS output end status=failed\n");
}
