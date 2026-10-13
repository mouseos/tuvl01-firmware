/* SPDX-License-Identifier: MIT
 * TUVL01 Wi-Fi protocol, I/O-free part (README.md). Portable C99: usable
 * unchanged from a BonDriver, an Android NDK/JNI library or any other client. */
#ifndef TUVL01_PROTO_H
#define TUVL01_PROTO_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define TUVL01_DEVICE_IP "192.168.74.1"
#define TUVL01_CONTROL_PORT 4200
#define TUVL01_ECHO_PORT 4201
#define TUVL01_STREAM_PORT 4202
#define TUVL01_REQUEST_SIZE 8
#define TUVL01_STREAM_MAX_DATAGRAM 1332
enum {TUVL01_OP_HELLO=1,TUVL01_OP_START=2,TUVL01_OP_STOP=3,TUVL01_OP_STATUS=4,TUVL01_OP_KEEPALIVE=5,TUVL01_OP_TUNE=6};
enum {TUVL01_STATUS_OK=0,TUVL01_STATUS_BAD=1,TUVL01_STATUS_UNSUPPORTED=2};
enum {TUVL01_STATE_IDLE=0,TUVL01_STATE_STREAMING=1,TUVL01_STATE_STARTING=2};
enum {TUVL01_CAP_STREAM=1,TUVL01_CAP_TUNE=2};
enum {TUVL01_TUNE_NONE=0,TUVL01_TUNE_BUSY=1,TUVL01_TUNE_DONE=2,TUVL01_TUNE_FAILED=3};
#define TUVL01_LOCK_UNKNOWN 255

typedef struct {
    uint8_t op,status,state;       /* op without the 0x80 reply bit */
    uint16_t id;
    uint8_t version;               /* HELLO only */
    uint16_t revision,stream_port; /* HELLO only */
    uint32_t caps;                 /* HELLO only */
    uint8_t first_channel,last_channel; /* HELLO only (0 from older firmware) */
    uint16_t channel;              /* STATUS: tuned UHF channel, 0 = none yet */
    uint8_t partial,tune,lock;     /* STATUS: one-segment mode, TUVL01_TUNE_*, lock 0/1/255 */
} tuvl01_reply;

/* Writes the 8-byte request; returns its length. */
size_t tuvl01_build_request(uint8_t *out,uint8_t op,uint16_t id);
/* TUNE request (10 bytes): UHF channel 13..52, partial=0 full segment / 1 one segment. */
size_t tuvl01_build_tune_request(uint8_t *out,uint8_t channel,uint8_t partial,uint16_t id);
/* Returns 0 and fills *r, or a negative value when data is not a valid reply. */
int tuvl01_parse_reply(const uint8_t *data,size_t length,tuvl01_reply *r);

typedef struct {uint32_t sequence,index,flags;const uint8_t *ts;size_t packets;} tuvl01_stream;
/* Returns 0 and points ts into data, or a negative value for an invalid datagram. */
int tuvl01_parse_stream(const uint8_t *data,size_t length,tuvl01_stream *s);

/* Loss accounting from datagram sequence numbers. */
typedef struct {
    uint32_t expected;int started;
    uint64_t datagrams,missing,resyncs,reordered,invalid;
} tuvl01_loss;
void tuvl01_loss_init(tuvl01_loss *l);
/* Returns 0 for a datagram to deliver, 1 for a reordered/duplicate one to drop. */
int tuvl01_loss_update(tuvl01_loss *l,const tuvl01_stream *s);

#ifdef __cplusplus
}
#endif
#endif

