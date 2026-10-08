/* SPDX-License-Identifier: MIT */
#ifndef TUVL_KEY_LEDGER_H
#define TUVL_KEY_LEDGER_H
#include <stdint.h>
#include <stddef.h>
typedef int (*tuvl_key_submit_fn)(void *,const uint8_t *,size_t);
struct tuvl_key_slot { uint8_t pending,peer[6]; };
/* Public metadata only; no key or RSC retained. Failed I/O is never retried. */
struct tuvl_key_ledger { struct tuvl_key_slot slot[5]; unsigned failed,busy; };
int tuvl_key_ledger_submit(struct tuvl_key_ledger *,tuvl_key_submit_fn,void *,const uint8_t *,size_t);
/* Success means deletion commands transferred, NOT hardware erasure ACK. */
int tuvl_key_ledger_close(struct tuvl_key_ledger *,tuvl_key_submit_fn,void *);
#endif
