#ifndef TUVL_RSN_SESSION_H
#define TUVL_RSN_SESSION_H
#include "utils/includes.h"
#include "utils/common.h"
#include "rsn_supp/wpa.h"
struct tuvl_rsn_session;
struct tuvl_rsn_driver {
    void *ctx;
    /* Buffers valid only during call; driver must copy or complete before return.
     * Return0 only for actual accepted submission, -1 on failure.
     * Key hardware application must be verified separately.
     */
    int (*send)(void *,const u8 *,size_t);
    int (*key)(void *,int,enum wpa_alg,const u8 *,int,int,
               const u8 *,size_t,const u8 *,size_t,enum key_flag);
    void (*disconnect)(void *,u16);
    /* Required. Implement/verify protection policy in the real driver;
     * failure latches this session disconnected. No success placeholder. */
    int (*protection)(void *,const u8 *,int,int);
};
struct tuvl_rsn_session *tuvl_rsn_session_open(const struct tuvl_rsn_driver *,
    const u8 own[6],const u8 ap[6],const u8 *,size_t,const u8 pmk[32],
    const u8 *ap_rsn,size_t ap_rsn_len);
int tuvl_rsn_session_assoc_ie(struct tuvl_rsn_session *,u8 *,size_t *);
int tuvl_rsn_session_associated(struct tuvl_rsn_session *);
int tuvl_rsn_session_rx(struct tuvl_rsn_session *,const u8 *,size_t,
                         enum frame_encryption);
enum wpa_states tuvl_rsn_session_state(const struct tuvl_rsn_session *);
void tuvl_rsn_session_close(struct tuvl_rsn_session *);
#endif
