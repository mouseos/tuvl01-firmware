/* SPDX-License-Identifier: MIT
 * TUVL01 Wi-Fi protocol, I/O-free part (docs/protocol.md). Portable C99: usable
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
enum {TUVL01_OP_HELLO=1,TUVL01_OP_START=2,TUVL01_OP_STOP=3,TUVL01_OP_STATUS=4,TUVL01_OP_KEEPALIVE=5};
enum {TUVL01_STATUS_OK=0,TUVL01_STATUS_BAD=1,TUVL01_STATUS_UNSUPPORTED=2};
enum {TUVL01_STATE_IDLE=0,TUVL01_STATE_STREAMING=1,TUVL01_STATE_STARTING=2};
enum {TUVL01_CAP_STREAM=1};

typedef struct {
    uint8_t op,status,state;       /* op without the 0x80 reply bit */
    uint16_t id;
    uint8_t version;               /* HELLO only */
    uint16_t revision,stream_port; /* HELLO only */
    uint32_t caps;                 /* HELLO only */
    uint16_t channel;              /* STATUS only; 0 = unspecified */
} tuvl01_reply;

/* Writes the 8-byte request; returns its length. */
size_t tuvl01_build_request(uint8_t *out,uint8_t op,uint16_t id);
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
