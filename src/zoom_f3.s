; Magnify the cockpit/HUD, but rasterize 3D directly at native screen resolution.
; Dummy BSS sections describe existing executable hunks to the assembler.
; The builder remaps their relocations and does not install these sections.
        section zoom_patch,code
        include "analysis/build/zoom_art.i"
        include "analysis/build/original_hunks.i"
exports:
        dc.l frame_begin,frame_end,key_handler,click_handler,sliders,reset_view
        dc.l zoom_enabled,saved_flags,backup0,backup1
        dc.l render_begin,render_hud,project_axis,project_horizon,scale_long
        dc.l native_scene,viewport_save
        dc.l draw_sight,draw_range,draw_art,unpack_art,art_raw,hud_active
        dc.l panel_begin,laser_acquire

; The original HUD rejects distances below 200 or at least 7999 metres,
; but acquisition checked only the object ID. Such a false lock bypasses
; the normal traverse limit on the next frame and snaps to the object.
; Use the same range limits before entering the original lock handler.
; 4000..7998 is still valid (the HUD blinks the actual distance there).
laser_acquire:
        move.w $23c(a2),d0
        bmi.s .invalid
        cmpi.w #200,$b8(a2)
        bcs.s .invalid
        cmpi.w #7999,$b8(a2)
        bcc.s .invalid
        jmp old0+$3248-$9c
.invalid:
        jmp old0+$3240-$9c

frame_begin:
        movem.l d0-d7/a0-a6,-(sp)
        move.w 8(a2),d0
        andi.w #1,d0
        lea saved_flags,a4
        tst.b (a4,d0.w)
        beq.w .done
        tst.w zoom_enabled
        beq.s .restore
        cmpi.w #3,$be(a2)
        bne.s .restore
        ; Keep the native cockpit in this buffer until a view/base redraw.
        cmpi.w #3,$c2(a2)
        bne.s .restore
        tst.w $c4(a2)
        bmi.w .done
.restore:
        clr.b (a4,d0.w)
        ; Refresh original instruments after they were hidden in zoom.
        tst.w zoom_enabled
        beq.s .refresh
        cmpi.w #3,$be(a2)
        beq.s .copy_buffer
.refresh:
        move.w #1,$c4(a2)
.copy_buffer:
        bsr.w get_buffer
        bsr.w wait_blit
        moveq #3,d7
.plane:
        movea.l (a6)+,a1
        move.w #1919,d6
.copy:
        move.l (a0)+,(a1)+
        dbra d6,.copy
        dbra d7,.plane
.done:
        movem.l (sp)+,d0-d7/a0-a6
        move.l old27+$3675a-$1b2f4,d0
        jmp old0+$828e-$9c

frame_end:
        jmp old0+$5de4-$9c

; Skip only the old cockpit painting. The common status-line list at $8354
; still runs, and the normal camera, simulation and HUD paths are untouched.
panel_begin:
        tst.w zoom_enabled
        beq.s .original
        cmpi.w #3,$be(a2)
        bne.s .original
        tst.w $c4(a2)
        bmi.s .status
        subq.w #1,$c4(a2)
.status:
        jsr old0+$9f0e-$9c
        move.w $a6(a2),d1
        move.l (a3,d1.w),old27+$3608e-$1b2f4
        moveq #0,d0
        tst.w $c4(a2)
        bne.s .continue
        moveq #1,d0
.continue:
        jmp old0+$8354-$9c
.original:
        move.w $c4(a2),d0
        bmi.s .no_refresh
        subq.w #1,$c4(a2)
        jmp old0+$8314-$9c
.no_refresh:
        jmp old0+$8322-$9c

scale_cockpit:
        movem.l d0-d7/a0-a6,-(sp)
        tst.w zoom_enabled
        beq.w .done
        cmpi.w #3,$be(a2)
        bne.w .done
        move.w 8(a2),d0
        andi.w #1,d0
        lea saved_flags,a4
        tst.b (a4,d0.w)
        bne.w .smoke
        move.w d0,d6
        add.w d6,d6
        lea smoke_state,a1
        move.w #-1,(a1,d6.w)
        move.b #1,(a4,d0.w)
        bsr.w get_buffer
        bsr.w wait_blit
        movea.l a0,a5
        movea.l a6,a4
        moveq #3,d7
.save_plane:
        movea.l (a6)+,a1
        move.w #1919,d6
.save:
        move.l (a1)+,(a0)+
        dbra d6,.save
        dbra d7,.save_plane
        tst.w art_ready
        bne.s .loaded
        bsr.w unpack_art
        move.w #1,art_ready
.loaded:
        move.w 8(a2),d0
        bsr.w get_buffer
        lea art_raw,a0
        moveq #3,d7
.art_plane:
        movea.l (a6)+,a1
        move.w #1919,d6
.art_copy:
        move.l (a0)+,(a1)+
        dbra d6,.art_copy
        dbra d7,.art_plane
.smoke:
        move.w $a6(a2),d0
        movea.l (a3,d0.w),a0
        moveq #0,d7
        tst.w $48(a0)
        beq.s .state
        moveq #1,d7
.state:
        move.w 8(a2),d0
        add.w d0,d0
        lea smoke_state,a1
        cmp.w (a1,d0.w),d7
        beq.w .done
        move.w d7,(a1,d0.w)
        ; Erase the small Smoke area from the PNG before drawing its current
        ; state (the two atlas cells may have different transparency masks).
        move.w 8(a2),d0
        bsr.w get_buffer
        bsr.w wait_blit
        lea art_raw+13*40+38,a0
        moveq #3,d7
.smoke_plane:
        movea.l (a6)+,a1
        lea 13*40+38(a1),a1
        moveq #40,d6
.smoke_row:
        move.w (a0),(a1)
        lea 40(a0),a0
        lea 40(a1),a1
        dbra d6,.smoke_row
        lea 7680-41*40(a0),a0
        dbra d7,.smoke_plane
        move.w #0,sprite_tint
        subq.w #1,sprite_tint
        move.w $a6(a2),d0
        movea.l (a3,d0.w),a0
        move.w $48(a0),d7
        lea art_raw+ART_SMOKE1_PREPINAC_0,a0
        tst.w d7
        beq.s .switch
        lea art_raw+ART_SMOKE1_PREPINAC_1,a0
.switch:
        move.w #309,d0
        moveq #34,d1
        bsr.w draw_art
        lea art_raw+ART_SMOKE1_SVETLO_0,a0
        tst.w d7
        beq.s .lamp
        lea art_raw+ART_SMOKE1_SVETLO_1,a0
.lamp:
        move.w #312,d0
        moveq #13,d1
        bsr.w draw_art
.done:
        movem.l (sp)+,d0-d7/a0-a6
        rts

; Install the cached cockpit before any native 3D is drawn.
render_begin:
        jsr old0+$867e-$9c
        bsr.w scale_cockpit
        movem.l d0-d7/a0-a6,-(sp)
        clr.w native_scene
        tst.w zoom_enabled
        beq.w .done
        cmpi.w #3,$be(a2)
        bne.w .done
        lea $1fc(a2),a0
        lea viewport_save,a1
        moveq #8,d0
.save:
        move.w (a0)+,(a1)+
        dbra d0,.save
        ; Exact nearest-neighbour footprint of the original (96,6)-(216,116).
        move.w #64,$1fc(a2)
        move.w #257,$200(a2)
        move.w #10,$204(a2)
        move.w #187,$208(a2)
        move.w #160,$20a(a2)
        move.w #98,$20c(a2)
        move.w #64,old27+$1d0c0-$1b2f4
        move.w #257,old27+$1d0c2-$1b2f4
        move.w #10,old27+$1d0bc-$1b2f4
        move.w #187,old27+$1d0be-$1b2f4
        move.w #1,native_scene
.done:
        movem.l (sp)+,d0-d7/a0-a6
        jsr old0+$bf10-$9c
        jmp old0+$8392-$9c

; Preserve the original HUD logic; its drawing calls use the new PNG sprites.
render_hud:
        jsr old0+$9f0e-$9c
        tst.w native_scene
        bne.s .native
        jsr old0+$9a82-$9c
        jmp old0+$83aa-$9c
.native:
        clr.w native_scene
        movem.l d0-d7/a0-a6,-(sp)
        lea viewport_save,a0
        lea $1fc(a2),a1
        moveq #8,d0
.restore_view:
        move.w (a0)+,(a1)+
        dbra d0,.restore_view
        move.w #1,hud_active
        jsr old0+$9a82-$9c
        clr.w hud_active
        movem.l (sp)+,d0-d7/a0-a6
        jmp old0+$83aa-$9c

draw_sight:
        tst.w hud_active
        bne.s .art
        jmp old0+$1eda-$9c
.art:
        movem.l d0-d7/a0-a6,-(sp)
        lea art_raw+ART_ZAMEROVAC_NORMAL,a0
        tst.w d2
        beq.s .selected
        lea art_raw+ART_ZAMEROVAC_THERMAL,a0
.selected:
        move.w #-1,sprite_tint
        bsr.w art_coordinates
        bsr.w draw_art
        movem.l (sp)+,d0-d7/a0-a6
        rts

draw_range:
        tst.w hud_active
        bne.s .art
        jmp old0+$20f2-$9c
.art:
        movem.l d0-d7/a0-a6,-(sp)
        move.w $14(a2),d0
        move.w $12(a2),d1
        bsr.w art_coordinates
        move.w $16(a2),sprite_tint
        lea old27+$1d02c-$1b2f4,a5
        lea font_offsets,a4
.char:
        moveq #0,d2
        move.b (a5)+,d2
        beq.s .done
        cmpi.b #32,d2
        beq.s .space
        cmpi.b #42,d2
        bne.s .digit
        moveq #10,d2
        bra.s .glyph
.digit:
        subi.w #48,d2
        cmpi.w #9,d2
        bhi.s .space
.glyph:
        move.w d2,d3
        lsl.w #2,d2
        lea art_raw,a0
        adda.l (a4,d2.w),a0
        bsr.w draw_art
        cmpi.w #1,d3
        beq.s .narrow
        addi.w #11,d0
        bra.s .char
.narrow:
        addq.w #6,d0
        bra.s .char
.space:
        addi.w #13,d0
        bra.s .char
.done:
        movem.l (sp)+,d0-d7/a0-a6
        rts

art_coordinates:
        subi.w #56,d0
        mulu.w #8,d0
        addq.l #4,d0
        divu.w #5,d0
        mulu.w #8,d1
        addq.l #4,d1
        divu.w #5,d1
        rts

; Sparse planar words: sixteen pixels share a single masked write.
; Keep the indexed renderer for clipping and unexpected caller coordinates.
draw_art:
        movem.l d0-d7/a0-a6,-(sp)
        movea.l a0,a5
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
        ; Cropped tables are exclusively the right-edge Smoke graphics.
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
        mulu.w #40,d1
        lsr.w #4,d0
        add.w d0,d0
        add.w d0,d1
        move.w d1,d5
        move.w 8(a2),d0
        lsl.w #2,d0
        lea old4+$14,a6
        movea.l (a6,d0.w),a6
        movea.l 8(a6),a1
        movea.l 12(a6),a3
        movea.l 16(a6),a4
        movea.l 20(a6),a5
        move.w sprite_tint,d6
        bsr.w wait_blit
        move.w (a0)+,d4
        beq.w .done
        movea.w d4,a6
.block:
        move.w (a0)+,d0
        add.w d5,d0
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
        moveq #0,d3
        move.w (a0)+,d3
        swap d3
        lsr.l d7,d3
        btst #0,d6
        bne.s .plane0
        and.l d2,d3
.plane0:
        move.l (a1,d0.w),d4
        and.l d1,d4
        or.l d3,d4
        move.l d4,(a1,d0.w)
        moveq #0,d3
        move.w (a0)+,d3
        swap d3
        lsr.l d7,d3
        btst #1,d6
        bne.s .plane1
        and.l d2,d3
.plane1:
        move.l (a3,d0.w),d4
        and.l d1,d4
        or.l d3,d4
        move.l d4,(a3,d0.w)
        moveq #0,d3
        move.w (a0)+,d3
        swap d3
        lsr.l d7,d3
        btst #2,d6
        bne.s .plane2
        and.l d2,d3
.plane2:
        move.l (a4,d0.w),d4
        and.l d1,d4
        or.l d3,d4
        move.l d4,(a4,d0.w)
        moveq #0,d3
        move.w (a0)+,d3
        swap d3
        lsr.l d7,d3
        btst #3,d6
        bne.s .plane3
        and.l d2,d3
.plane3:
        move.l (a5,d0.w),d4
        and.l d1,d4
        or.l d3,d4
        move.l d4,(a5,d0.w)
        subq.l #1,a6
        move.l a6,d4
        bne.w .block
.done:
        movem.l (sp)+,d0-d7/a0-a6
        rts
.fallback:
        movem.l (sp)+,d0-d7/a0-a6

; a0: width/height words followed by palette indices (16 = transparent).
draw_art_clipped:
        movem.l d0-d7/a0-a6,-(sp)
        move.w d0,d5
        move.w (a0)+,a4
        move.w (a0)+,d4
        subq.w #1,d4
        move.w d1,-(sp)
        move.w 8(a2),d0
        lsl.w #2,d0
        lea old4+$14,a6
        movea.l (a6,d0.w),a6
        addq.l #8,a6
        move.w (sp)+,d1
        bsr.w wait_blit
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
        mulu.w #40,d7
        move.w d0,d6
        lsr.w #3,d6
        add.w d6,d7
        move.w d0,d6
        andi.w #7,d6
        eori.w #7,d6
        movea.l a6,a3
        move.w d3,-(sp)
        moveq #3,d3
.plane:
        movea.l (a3)+,a1
        lsr.b #1,d2
        bcc.s .clear
        bset d6,(a1,d7.w)
        bra.s .next_plane
.clear:
        bclr d6,(a1,d7.w)
.next_plane:
        dbra d3,.plane
        move.w (sp)+,d3
.skip:
        addq.w #1,d0
        dbra d3,.pixel
        addq.w #1,d1
        dbra d4,.row
        movem.l (sp)+,d0-d7/a0-a6
        rts

unpack_art:
        movem.l d0-d7/a0-a6,-(sp)
        lea art_packed,a0
        lea art_raw,a1
        lea art_raw+ART_SIZE,a4
.token:
        moveq #0,d0
        move.b (a0)+,d0
        bmi.s .reference
.literal:
        move.b (a0)+,(a1)+
        dbra d0,.literal
        bra.s .next
.reference:
        andi.w #127,d0
        addq.w #2,d0
        moveq #0,d1
        move.b (a0)+,d1
        lsl.w #8,d1
        move.b (a0)+,d1
        movea.l a1,a3
        suba.l d1,a3
.repeat:
        move.b (a3)+,(a1)+
        dbra d0,.repeat
.next:
        cmpa.l a4,a1
        bcs.s .token
        movem.l (sp)+,d0-d7/a0-a6
        rts

; Scale the perspective numerator BEFORE division, retaining subpixel detail.
; The final DIVS supplies the overflow flag consumed by the original fallback.
project_axis:
        ext.l d0
        asl.l d3,d0
        tst.w native_scene
        beq.s .normal
        bsr.w scale_long
.normal:
        divs.w d2,d0
        rts

project_horizon:
        tst.w native_scene
        beq.s .normal
        bsr.w scale_long
.normal:
        divs.w d2,d0
        add.w $20c(a2),d0
        rts

; Signed 32-bit x*8/5 using two unsigned 32/16 divisions (68000 compatible).
scale_long:
        movem.l d1/d4-d5,-(sp)
        move.l d0,d5
        bpl.s .positive
        neg.l d0
.positive:
        lsl.l #3,d0
        move.l d0,d4
        swap d0
        andi.l #$ffff,d0
        divu.w #5,d0
        moveq #0,d1
        move.w d0,d1
        swap d1
        move.w d4,d0
        divu.w #5,d0
        andi.l #$ffff,d0
        or.l d1,d0
        tst.l d5
        bpl.s .done
        neg.l d0
.done:
        movem.l (sp)+,d1/d4-d5
        rts

; d0=bitmap index (0/1), return a0=backup, a6=plane pointer array.
get_buffer:
        lea backup0,a0
        tst.w d0
        beq.s .first
        lea backup1,a0
.first:
        lsl.w #2,d0
        lea old4+$14,a6
        movea.l (a6,d0.w),a6
        addq.l #8,a6
        rts

wait_blit:
        btst #6,$dff002
        bne.s wait_blit
        rts

key_handler:
        cmpi.b #$fd,d0
        bne.s .normal
        move.w #1,zoom_enabled
        cmpi.w #3,$be(a2)
        bne.s .enter
        ; Already in F3: do not call the normal view/AI target selection path.
        ori #1,ccr
        rts
.enter:
        move.w #$f3,d0
        jmp old0+$9024-$9c
.normal:
        cmpi.b #$f3,d0
        bne.s .continue
        tst.w zoom_enabled
        beq.s .continue
        clr.w zoom_enabled
        cmpi.w #3,$be(a2)
        bne.s .continue
        ; Leaving zoom is only a presentation change, just like entering it
        ; from F3. Consume the key before the original AI target selection.
        ori #1,ccr
        rts
.continue:
        cmpi.w #8,old27+$35eb4-$1b2f4
        jmp old0+$8ff0-$9c

; Preserve the original right-click action; only filter panel left clicks.
; This hook is reached after the original right-click handling at $85e4.
click_handler:
        tst.w zoom_enabled
        beq.s .original
        cmpi.w #3,$be(a2)
        bne.s .original
        ; Smoke 1 switch, transformed with the same crop and scale as its image.
        cmpi.w #304,$26(a2)
        bcs.s .done
        cmpi.w #320,$26(a2)
        bcc.s .done
        cmpi.w #29,$28(a2)
        bcs.s .done
        cmpi.w #57,$28(a2)
        bcc.s .done
        btst #1,$2b(a2)
        beq.s .done
        move.w $16e(a2),d1
        or.w old27+$39bcc-$1b2f4,d1
        or.w old27+$35eac-$1b2f4,d1
        or.w old27+$35eae-$1b2f4,d1
        bne.s .done
        move.w #8,$16e(a2)
        move.w #8,old27+$39bcc-$1b2f4
.done:
        rts
.original:
        move.w $be(a2),d0
        cmpi.w #6,d0
        jmp old0+$8610-$9c

sliders:
        tst.w zoom_enabled
        beq.s .original
        cmpi.w #3,$be(a2)
        beq.s .done
.original:
        tst.w old27+$39bcc-$1b2f4
        jmp old0+$848c-$9c
.done:
        rts

reset_view:
        clr.w zoom_enabled
        clr.w saved_flags
        clr.w native_scene
        clr.w hud_active
        move.w #4,$be(a2)
        jmp old0+$824a-$9c

font_offsets:
        dc.l ART_FONT_0,ART_FONT_1,ART_FONT_2,ART_FONT_3,ART_FONT_4
        dc.l ART_FONT_5,ART_FONT_6,ART_FONT_7,ART_FONT_8,ART_FONT_9
        dc.l ART_FONT_HVEZDICKA
art_packed:
        incbin "analysis/build/zoom_art.bin"
        even

        section original_code,bss
old0:   ds.b ORIGINAL_HUNK_0_SIZE
        section original_data,bss
old27:  ds.b ORIGINAL_HUNK_27_SIZE
        section original_bitmaps,bss
old4:   ds.b ORIGINAL_HUNK_4_SIZE
        section zoom_state,bss
zoom_enabled: ds.w 1
saved_flags:  ds.w 1
        ds.b 12
backup0: ds.b 30720
backup1: ds.b 30720
native_scene: ds.w 1
viewport_save: ds.w 9
hud_active: ds.w 1
sprite_tint: ds.w 1
smoke_state: ds.w 2
art_ready: ds.w 1
art_raw: ds.b ART_SIZE
