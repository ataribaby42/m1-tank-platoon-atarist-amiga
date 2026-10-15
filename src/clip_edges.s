; Correct polygon closure at the left/right viewport boundaries.
; Original projected vertices outside the viewport are not border crossings.
; Keep the original line clipping and rasterization; save only real crossings
; in the edge record's spare words (+4 left Y, +8 mask, +12 right Y).
        section clip_patch,code
        dc.l clip_edge,polygon_edge,border_right,border_left,reject_edge,horizon_edge

; Near-plane rejection bypasses the screen clipper. Discard old per-edge
; metadata too; the edge storage is reused across objects and frames.
reject_edge:
        move.w #$8080,(a4)
        clr.w 8(a4)
        jmp old0+$c6d4-$9c

; The horizon intentionally closes an open line down to the viewport bottom,
; rather than describing a closed polygon. Keep its original accumulation.
horizon_edge:
        move.w (a4),d0
        or.w d0,$11a(a2)
        jmp old0+$b256-$9c

clip_edge:
        jsr old0+$d102-$9c
        bne.s .clipped
        jmp old0+$cf0a-$9c
.clipped:
        ; MOVEM and JSR preserve the classification flags, including N.
        movem.l d2-d5/a0-a1/a5-a6,-(sp)
        jsr old0+$cf1c-$9c
        movem.l d0-d7/a0-a6,-(sp)
        ; MOVE from SR is privileged on 68010+, even though it is legal on
        ; 68000. Save the returned condition codes with user-mode instructions
        ; valid on every supported CPU. Scc/MOVEM leave all flags untouched;
        ; ADDX captures X after the other four flags have been recorded.
        seq d0
        smi d1
        scs d6
        svs d7
        moveq #0,d2
        addx.b d2,d2
        lsl.w #4,d2
        andi.w #4,d0
        andi.w #8,d1
        andi.w #1,d6
        andi.w #2,d7
        or.w d1,d0
        or.w d6,d0
        or.w d7,d0
        or.w d2,d0
        move.w d0,-(sp)
        movem.l 62(sp),d2-d5/a0-a1/a5-a6
        clr.w 8(a4)
        cmp.l d4,d2
        ble.s .sorted
        exg d2,d4
        exg d3,d5
.sorted:
        move.l a0,d1
        bsr.w intersection
        bcs.s .right
        move.w d0,4(a4)
        ori.w #2,8(a4)
.right:
        move.l a5,d1
        bsr.w intersection
        bcs.s .done
        move.w d0,12(a4)
        ori.w #1,8(a4)
.done:
        move.w (sp)+,ccr
        movem.l (sp)+,d0-d7/a0-a6
        lea 32(sp),sp
        rts

; D1 = boundary X, D2/D3 and D4/D5 = original endpoints sorted by X.
; Return D0 = crossing Y, C = no crossing. Preserve the endpoint registers.
intersection:
        cmp.l d2,d1
        blt.w .miss
        cmp.l d4,d1
        bgt.w .miss
        cmp.l d4,d2
        beq.w .miss
        move.l d5,d6
        sub.l d3,d6
        bvs.s .large
        move.l d6,d0
        bpl.s .abs
        neg.l d0
.abs:
        cmpi.l #$7fff,d0
        bhi.s .large
        move.l d4,d7
        sub.l d2,d7
        cmpi.l #$7fff,d7
        bhi.s .large
        move.l d1,d0
        sub.l d2,d0
        muls.w d6,d0
        divs.w d7,d0
        ext.l d0
        add.l d3,d0
        bra.s .limit
.large:
        ; Wide projected coordinates use bisection, like the original
        ; clipper. Overflow-safe midpoints also handle opposite signs.
        movem.l d2-d5,-(sp)
.bisect:
        move.l d3,d0
        cmp.l d2,d1
        beq.s .found
        move.l d5,d0
        cmp.l d4,d1
        beq.s .found
        move.l d2,d0
        eor.l d4,d0
        asr.l #1,d0
        move.l d2,d7
        and.l d4,d7
        add.l d7,d0
        move.l d3,d6
        eor.l d5,d6
        asr.l #1,d6
        move.l d3,d7
        and.l d5,d7
        add.l d7,d6
        cmp.l d1,d0
        bge.s .upper
        move.l d0,d2
        move.l d6,d3
        bra.s .bisect
.upper:
        move.l d0,d4
        move.l d6,d5
        bra.s .bisect
.found:
        movem.l (sp)+,d2-d5
.limit:
        ; For visible clipped endpoints, retain the original clipper's
        ; exact rounding so the closure meets its rasterized edge.
        tst.b 1(a4)
        bmi.s .vertical
        cmp.w 2(a4),d1
        bne.s .second
        move.w 6(a4),d0
        ext.l d0
        bra.s .vertical
.second:
        cmp.w 10(a4),d1
        bne.s .vertical
        move.w 14(a4),d0
        ext.l d0
.vertical:
        ; Retain one-pixel outside sentinels until the complete polygon
        ; is known. Clamping both ends now would paint a spurious top or
        ; bottom row for polygons lying wholly outside the viewport.
        cmp.l a1,d0
        bge.s .bottom
        move.l a1,d0
        subq.l #1,d0
.bottom:
        cmp.l a6,d0
        ble.s .hit
        move.l a6,d0
        addq.l #1,d0
.hit:
        andi #$fe,ccr
        rts
.miss:
        ori #1,ccr
        rts

polygon_edge:
        move.w (a4),d0
        bne.s .clipped
        ; Entirely inside: original path, including original register use.
        bra.w horizon_edge
.clipped:
        movem.l d0-d7/a0-a6,-(sp)
        tst.b d0
        bmi.s .boundary
        ori.w #4,$118(a2)
        move.w 2(a4),0(a2)
        move.w 6(a4),2(a2)
        move.w 10(a4),4(a2)
        move.w 14(a4),6(a2)
        jsr old0+$1ea0-$9c
.boundary:
        move.w 8(a4),d0
        or.w d0,$11a(a2)
        btst #1,d0
        beq.s .right
        move.w 4(a4),d1
        move.w d1,d2
        jsr old0+$b2bc-$9c
.right:
        btst #0,9(a4)
        beq.s .done
        move.w 12(a4),d1
        move.w d1,d2
        jsr old0+$b2d8-$9c
.done:
        movem.l (sp)+,d0-d7/a0-a6
        rts

border_right:
        move.w $116(a2),d1
        move.w $114(a2),d3
        move.w $200(a2),d0
        bra.s border
border_left:
        move.w $112(a2),d1
        move.w $110(a2),d3
        move.w $1fc(a2),d0
border:
        cmp.w $204(a2),d3
        blt.s .done
        cmp.w $208(a2),d1
        bgt.s .done
        cmp.w $204(a2),d1
        bge.s .bottom
        move.w $204(a2),d1
.bottom:
        cmp.w $208(a2),d3
        ble.s .draw
        move.w $208(a2),d3
.draw:
        move.w d0,0(a2)
        move.w d1,2(a2)
        move.w d0,4(a2)
        move.w d3,6(a2)
        jmp old0+$1ea0-$9c
.done:
        rts

        section original_code,bss
old0:   ds.b $d200
