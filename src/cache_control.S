/* SPDX-License-Identifier: MIT. Execute through the uncached RAM alias. */
.section .text.board_cache_instruction_write,"ax"
.global _board_cache_instruction_write
_board_cache_instruction_write:
    mov.l .Lccr,r1
    mov.l @r1,r0
    mov.l .Lmask,r2
    and r2,r0
    tst r4,r4
    bt .Lflush
    mov #1,r2
    shll8 r2
    or r2,r0
.Lflush:
    mov #8,r2
    shll8 r2
    or r2,r0
    mov.l r0,@r1
    mov.l @r1,r0
    rts
    nop
.balign 4
.Lccr: .long 0xfffc1000
.Lmask: .long 0xfffffeff
