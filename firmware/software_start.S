.section .text.startup
.global _start
_start:
    li sp, 0xff0
    call main
1:  j 1b
