/* SPDX-License-Identifier: MIT
 * Socket layer for the TUVL01 protocol (Winsock or POSIX). No threads: the
 * caller drives it, so a BonDriver thread or an Android service can own timing. */
#ifndef TUVL01_SESSION_H
#define TUVL01_SESSION_H
#include "tuvl01_proto.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uintptr_t control,data;     /* UDP sockets */
    uint16_t next_id;
    uint64_t last_ping_ms,last_keepalive_ms;
    tuvl01_loss loss;
    int open;
} tuvl01_session;

/* Binds the stream port and opens the control socket. Returns 0 or a negative error. */
int tuvl01_open(tuvl01_session *s);
void tuvl01_close(tuvl01_session *s);
/* Sends one control operation and waits for its reply. Returns 0, or negative on
 * timeout/error. reply may be NULL. */
int tuvl01_command(tuvl01_session *s,uint8_t op,tuvl01_reply *reply,int timeout_ms);
/* Waits up to timeout_ms for one stream datagram. Returns the TS byte count copied
 * to out (multiple of 188), 0 on timeout or a dropped datagram, negative on error. */
int tuvl01_receive(tuvl01_session *s,uint8_t *out,size_t capacity,int timeout_ms);
/* Call regularly while streaming: sends the short 4201 packet every ping_ms and a
 * KEEPALIVE every keepalive_ms (either may be 0 to disable) and drains replies. */
void tuvl01_service(tuvl01_session *s,int ping_ms,int keepalive_ms);
/* Monotonic milliseconds. */
uint64_t tuvl01_now_ms(void);
#ifdef __cplusplus
}
#endif
#endif
