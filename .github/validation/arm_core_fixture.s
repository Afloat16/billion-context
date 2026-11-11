.syntax unified
.text
.global _start
.type _start, %function
MODE
_start:
    movw r0, #0x1010
    movw r1, #0x1111
    movw r2, #0x1212
    movw r3, #0x1313
    movw r4, #0x1414
    movw r5, #0x1515
    movw r6, #0x1616
    movw r7, #0x1717
    movw r8, #0x1818
    movw r9, #0x1919
    movw r10, #0x1a1a
    movw r11, #0x1b1b
    movw r12, #0x1c1c
    movw lr, #0x1e1e
.global fault_site
fault_site:
    udf #0
.size _start, .-_start
