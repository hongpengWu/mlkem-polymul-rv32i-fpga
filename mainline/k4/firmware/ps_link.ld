ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0, LENGTH = 128K }
__stack_top = ORIGIN(ram) + LENGTH(ram) - 16;
__stack_bottom = __stack_top - 32768;
SECTIONS
{
  .text : {
    KEEP(*(.text.startup.boot))
    *(.text.startup*) *(.text*)
  } > ram
  .rodata : ALIGN(4) { *(.rodata*) *(.srodata*) } > ram
  .data : ALIGN(4) {
    __global_pointer$ = . + 0x800;
    *(.sdata*) *(.data*)
  } > ram
  .bss (NOLOAD) : ALIGN(4) {
    __bss_start = .;
    *(.sbss*) *(.bss*) *(COMMON)
    . = ALIGN(4);
    __bss_end = .;
  } > ram
  __image_end = .;
  .ps_input 0x10000 (NOLOAD) : {
    __ps_input_start = .;
    . += 8192;
    __ps_input_end = .;
  } > ram
  .ps_output 0x12000 (NOLOAD) : {
    __ps_output_start = .;
    . += 8192;
    __ps_output_end = .;
  } > ram
  /* 0x14000..0x17fef is deliberately unused; the stack starts at 0x17ff0. */
  ASSERT(_start == ORIGIN(ram), "PS reset entry must be at address zero")
  ASSERT(__image_end <= __ps_input_start, "PS firmware overlaps input window")
  ASSERT(__ps_input_start == 0x10000 && __ps_input_end == 0x12000,
         "PS input window moved")
  ASSERT(__ps_output_start == 0x12000 && __ps_output_end == 0x14000,
         "PS output window moved")
  ASSERT(__ps_output_end <= __stack_bottom, "PS shared windows overlap 32 KiB stack")
  ASSERT(__stack_bottom == 0x17ff0 && __stack_top == 0x1fff0,
         "PS stack reservation moved")
  /DISCARD/ : { *(.comment) *(.eh_frame*) }
}
