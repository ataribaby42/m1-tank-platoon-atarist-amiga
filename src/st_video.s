; Native Atari ST low-resolution pixels: 160 bytes/row, 8 bytes/16 pixels.
; Sparse sprite records are produced by build_st_assets.py.
draw_art:
        movem.l d0-d7/a0-a6,-(sp)
        moveq #0,d2
        move.w (a0),d2
        mulu.w 2(a0),d2
        addq.l #5,d2
        andi.l #$fffffffe,d2
        lea (a0,d2.l),a4
        tst.w d0
        bmi.w .fallback
        tst.w d1
        bmi.w .fallback
        move.w (a4),d2
        cmp.w (a0),d2
        beq.s .width_ok
        add.w d0,d2
        cmpi.w #320,d2
        bne.w .fallback
        bra.s .height
.width_ok:
        add.w d0,d2
        cmpi.w #320,d2
        bhi.w .fallback
.height:
        move.w 2(a4),d2
        add.w d1,d2
        cmpi.w #192,d2
        bhi.w .fallback
        move.w d0,d7
        andi.w #15,d7
        lea 4(a4),a0
        mulu.w #160,d1
        lsr.w #4,d0
        lsl.w #3,d0
        add.w d0,d1
        move.w d1,d5
        move.w 8(a2),d0
        lsl.w #2,d0
        lea original+$32e06,a6
        movea.l (a6,d0.w),a6
        move.w sprite_tint,d6
        move.w (a0)+,d4
        beq.w .done
        movea.w d4,a4
.block:
        move.w (a0)+,d0
        add.w d5,d0
        lea (a6,d0.w),a1
        moveq #0,d1
        move.w (a0)+,d1
        swap d1
        lsr.l d7,d1
        not.l d1
        moveq #0,d2
        move.w (a0)+,d2
        swap d2
        lsr.l d7,d2
        not.l d2
        moveq #0,d0
.plane:
        moveq #0,d3
        move.w (a0)+,d3
        swap d3
        lsr.l d7,d3
        btst d0,d6
        bne.s .tint
        and.l d2,d3
.tint:
        ; Only touch the adjacent word when the opacity mask reaches it.
        ; This also protects the next scanline at the right screen edge.
        cmpi.w #$ffff,d1
        beq.s .first
        move.w 8(a1),d4
        and.w d1,d4
        or.w d3,d4
        move.w d4,8(a1)
.first:
        swap d1
        swap d3
        move.w (a1),d4
        and.w d1,d4
        or.w d3,d4
        move.w d4,(a1)+
        swap d1
        addq.w #1,d0
        cmpi.w #4,d0
        bne.s .plane
        subq.l #1,a4
        move.l a4,d4
        bne.w .block
.done:
        movem.l (sp)+,d0-d7/a0-a6
        rts
.fallback:
        movem.l (sp)+,d0-d7/a0-a6

draw_art_clipped:
        movem.l d0-d7/a0-a6,-(sp)
        move.w d0,d5
        move.w (a0)+,a4
        move.w (a0)+,d4
        subq.w #1,d4
        move.w 8(a2),d2
        lsl.w #2,d2
        lea original+$32e06,a6
        movea.l (a6,d2.w),a6
.row:
        move.w a4,d3
        subq.w #1,d3
        move.w d5,d0
.pixel:
        moveq #0,d2
        move.b (a0)+,d2
        cmpi.w #16,d2
        bcc.s .skip
        cmpi.w #320,d0
        bcc.s .skip
        cmpi.w #192,d1
        bcc.s .skip
        cmpi.w #15,d2
        bne.s .color
        tst.w sprite_tint
        bmi.s .color
        move.w sprite_tint,d2
.color:
        move.w d1,d7
        mulu.w #160,d7
        move.w d0,d6
        andi.w #$fff0,d6
        lsr.w #1,d6
        add.w d6,d7
        lea (a6,d7.w),a1
        move.w d0,d6
        andi.w #15,d6
        eori.w #15,d6
        move.w d3,-(sp)
        moveq #3,d3
.plane:
        move.w (a1),d7
        lsr.b #1,d2
        bcc.s .clear
        bset d6,d7
        bra.s .next
.clear:
        bclr d6,d7
.next:
        move.w d7,(a1)+
        dbra d3,.plane
        move.w (sp)+,d3
.skip:
        addq.w #1,d0
        dbra d3,.pixel
        addq.w #1,d1
        dbra d4,.row
        movem.l (sp)+,d0-d7/a0-a6
        rts

; D0 buffer 0/1 -> A0 saved cockpit, A1 physical screen address.
get_buffer:
        lea backup0,a0
        tst.w d0
        beq.s .first
        lea backup1,a0
.first:
        lsl.w #2,d0
        lea original+$32e06,a6
        movea.l (a6,d0.w),a1
        rts

wait_blit:
        rts
