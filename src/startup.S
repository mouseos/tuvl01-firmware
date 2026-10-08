/* SPDX-License-Identifier: MIT */
.section .entry,"ax"
.global _start
_start:
    mov #0xf0,r0
    extu.b r0,r0
    ldc r0,sr
    mov.l .Lsp,r15
    mov #0,r0
    ldc r0,gbr
    mov.l .Lbss,r1
    mov.l .Lbss_end,r2
1:  cmp/hs r2,r1
    bt 2f
    mov.l r0,@r1
    bra 1b
    add #4,r1
2:  mov.l .Lmain,r0
    jsr @r0
    nop
3:  bra 3b
    nop
.balign 4
.Lsp: .long __stack_top
.Lbss: .long __bss_start
.Lbss_end: .long __bss_end
.Lmain: .long _firmware_main
