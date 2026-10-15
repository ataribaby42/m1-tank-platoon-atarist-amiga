; Keep the original relative turret history for mechanical traverse sounds.
; The fire-control lead instead uses the change in WORLD sight direction.
        section lead_patch,code
        dc.l track_direction
track_direction:
        move.w $e(a5),-(sp)
        jsr old0+$3840-$9c
        movea.l (a3,d4.w),a5
        move.w $38(a3,d4.w),d0
        sub.w (sp)+,d0
        move.w d0,$66(a5)
        rts

        section original_code,bss
old0:   ds.l 1
