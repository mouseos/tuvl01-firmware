OUTPUT_FORMAT("elf32-sh")
OUTPUT_ARCH(sh)
ENTRY(_start)
MEMORY { CODE (rx) : ORIGIN = 0xfff80000, LENGTH = 8K
 RAM (rw) : ORIGIN = 0xfff82000, LENGTH = 16K }
SECTIONS {
 .entry : { KEEP(*(.entry)) } >CODE
 .text : { *(.text*) *(.rodata*) } >CODE
 .data : { *(.data*) } >CODE
 ASSERT(SIZEOF(.data)==0,"boot cannot contain initialized writable data")
 .bss (NOLOAD) : { . = ALIGN(16); __bss_start = .; *(.bss*) *(COMMON); . = ALIGN(4); __bss_end = .; } >RAM
 __stack_top = 0xfff88000;
 /DISCARD/ : { *(.comment) *(.note*) }
}
