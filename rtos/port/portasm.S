/* SPDX-License-Identifier: MIT. GNU SH-2A integer context; no FPU allowed. */
.section .text
.macro save_context
    sts.l pr,@-r15
    mov.l r14,@-r15
    mov.l r13,@-r15
    mov.l r12,@-r15
    mov.l r11,@-r15
    mov.l r10,@-r15
    mov.l r9,@-r15
    mov.l r8,@-r15
    mov.l r7,@-r15
    mov.l r6,@-r15
    mov.l r5,@-r15
    mov.l r4,@-r15
    mov.l r3,@-r15
    mov.l r2,@-r15
    mov.l r1,@-r15
    mov.l r0,@-r15
    sts.l macl,@-r15
    sts.l mach,@-r15
    stc.l gbr,@-r15
    mov.l .Ltcb,r0
    mov.l @r0,r0
    mov.l r15,@r0
.endm
.macro restore_context
    mov.l .Ltcb,r0
    mov.l @r0,r0
    mov.l @r0,r15
    ldc.l @r15+,gbr
    lds.l @r15+,mach
    lds.l @r15+,macl
    mov.l @r15+,r0
    mov.l @r15+,r1
    mov.l @r15+,r2
    mov.l @r15+,r3
    mov.l @r15+,r4
    mov.l @r15+,r5
    mov.l @r15+,r6
    mov.l @r15+,r7
    mov.l @r15+,r8
    mov.l @r15+,r9
    mov.l @r15+,r10
    mov.l @r15+,r11
    mov.l @r15+,r12
    mov.l @r15+,r13
    mov.l @r15+,r14
    lds.l @r15+,pr
    rte
    nop
.endm
.global _vPortStartFirstTask
_vPortStartFirstTask:
    restore_context
.global _port_yield_entry
_port_yield_entry:
    save_context
    mov.l .Lswitch,r0
    jsr @r0
    nop
    restore_context
.global _port_tick_entry
_port_tick_entry:
    save_context
    mov.l .Ltick,r0
    jsr @r0
    nop
    restore_context
.global _port_sdio_entry
_port_sdio_entry:
    save_context
    mov.l .Lsdio,r0
    jsr @r0
    nop
    restore_context
.balign 4
.Ltcb: .long _pxCurrentTCB
.Lswitch: .long _vTaskSwitchContext
.Ltick: .long _port_tick
.Lsdio: .long _sdio_irq_handler
