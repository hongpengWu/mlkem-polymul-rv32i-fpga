ENTRY(_start)

/* Match RAM_ADDR_BITS=14 in the KAT testbench: 16384 words / 64 KiB.
 * All compared CPU configurations use the same memory and stack reservations.
 * The existing polynomial benchmark retains its own 16 KiB memory map. */
MEMORY
{
  ram (rwx) : ORIGIN = 0, LENGTH = 64K
}

__stack_top = ORIGIN(ram) + LENGTH(ram) - 16;
__stack_bottom = __stack_top - 16384;

SECTIONS
{
  .text : {
    KEEP(*(.text.startup.boot))
    *(.text.startup*)
    *(.text*)
  } > ram

  .rodata : ALIGN(4) {
    *(.rodata*)
    *(.srodata*)
  } > ram

  .data : ALIGN(4) {
    __global_pointer$ = . + 0x800;
    *(.sdata*)
    *(.data*)
  } > ram

  .bss (NOLOAD) : ALIGN(4) {
    __bss_start = .;
    *(.sbss*)
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    __bss_end = .;
  } > ram

  __image_end = .;
  ASSERT(_start == ORIGIN(ram), "KAT reset entry must be at address zero")
  ASSERT(__image_end <= __stack_bottom,
         "KAT image overlaps its reserved 16 KiB stack")

  /DISCARD/ : { *(.comment) *(.eh_frame*) }
}
