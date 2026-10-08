OUTPUT_FORMAT("elf32-sh")
OUTPUT_ARCH(sh)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x1c000000, LENGTH = 1M }
SECTIONS {
 .entry : { KEEP(*(.entry)) } >RAM
 .text : { *(.text*) *(.rodata*) } >RAM
 .data : { *(.data*) } >RAM
 __initialized_end = .;
 /* Runtime uses descriptor symbols, so code can grow without overwriting a
  * fixed radio slot. Blob remains aligned and inside the packaged payload. */
 .radio ALIGN(16) : { KEEP(*(.radio)) } >RAM
 /* Zero-initialized buffers follow the blob. They do not enlarge the UART
  * image and startup clears them before any FreeRTOS task is started. */
 .bss (NOLOAD) : { . = ALIGN(16); __bss_start = .; *(.bss*) *(COMMON); . = ALIGN(4); __bss_end = .; } >RAM
 __stack_top = ORIGIN(RAM)+LENGTH(RAM);
 ASSERT(__bss_end < __stack_top-16384, "application exceeds RAM allocation")
 /DISCARD/ : { *(.comment) *(.note*) }
}
