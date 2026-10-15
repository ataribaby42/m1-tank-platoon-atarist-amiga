; Accept the enemy attack helicopter without impersonating friendly support.
; The ordinary call-in state machine retains its original delay and behavior.
        section mi24_patch,code
        dc.l attack_helicopter_call
attack_helicopter_call:
        cmpi.w #18,$6a(a3,d4.w)   ; Mi-24D
        beq.s .enemy
        cmpi.w #21,$6a(a3,d4.w)   ; original AH-64 check
        bne.s .reject
        jmp old0+$4140-$9c       ; original friendly status messages
.reject:
        jmp old0+$418e-$9c       ; original command rejection
.enemy:
        rts                     ; retain command, skip friendly radio text

        section original_code,bss
old0:   ds.l 1
