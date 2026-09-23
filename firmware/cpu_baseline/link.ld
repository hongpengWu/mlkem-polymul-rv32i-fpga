ENTRY(_start)

MEMORY
{
  ram (rwx) : ORIGIN = 0, LENGTH = 16K
}

__stack_top = ORIGIN(ram) + LENGTH(ram) - 16;
__stack_bottom = __stack_top - 2048;

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
  ASSERT(_start == ORIGIN(ram), "CPU reset entry must be at address zero")
  ASSERT(__image_end <= __stack_bottom,
         "CPU benchmark overlaps its reserved 2 KiB stack")

  /DISCARD/ : { *(.comment) *(.eh_frame*) }
}
