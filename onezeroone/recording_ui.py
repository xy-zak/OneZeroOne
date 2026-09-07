"""Recording panel: status, frame-rate, and post-processing.

Per-binding Record checkboxes live on each binding row in the main panel.
"""

from __future__ import annotations

import bpy

from . import recording


class ONEZEROONE_PT_recording(bpy.types.Panel):
    bl_label = "Recording"
    bl_idname = "ONEZEROONE_PT_recording"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OneZeroOne"
    bl_order = 10
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.onezeroone_record_settings

        # Status + toggle.
        box = layout.box()
        row = box.row()
        if recording.is_recording:
            row.operator("onezeroone.toggle_recording", text="Stop Recording", icon="REC")
        else:
            row.operator("onezeroone.toggle_recording", text="Start Recording", icon="REC")

        # Frame rate.
        box = layout.box()
        box.label(text="Frame Rate Settings:")
        row = box.row(align=True)
        row.prop(settings, "keyframe_rate", text="Keyframe Rate")
        row.operator("onezeroone.set_scene_fps", text="Set Scene FPS", icon="TIME")
        row = box.row()
        row.label(text=f"Scene Frame Rate: {context.scene.render.fps} fps")
        row = box.row()
        row.prop(settings, "auto_stop_at_end")
        row.label(text=f"End Frame: {context.scene.frame_end}")

        # Post-processing.
        box = layout.box()
        box.label(text="Post-Recording Processing:")

        row = box.row()
        row.prop(settings, "remove_jitter", text="Remove Rogue Keyframes")
        if settings.remove_jitter:
            sub = box.box()
            sub.prop(settings, "jitter_threshold", text="Threshold")
            sub.label(text="Smaller = More Aggressive")
            sub.operator("onezeroone.remove_jitter", text="Apply Effect", icon="KEYFRAME")

        row = box.row()
        row.prop(settings, "post_smooth_keyframes", text="Apply Gaussian Smoothing")
        if settings.post_smooth_keyframes:
            sub = box.box()
            sub.prop(settings, "post_smooth_factor", text="Smoothing Factor")
            sub.label(text="Higher = Smoother")
            sub.operator("onezeroone.smooth_keyframes", text="Apply Effect", icon="SMOOTHCURVE")

        row = box.row()
        row.prop(settings, "interpolate_keyframes", text="Interpolate Missing Frames")
        if settings.interpolate_keyframes:
            sub = box.box()
            sub.prop(settings, "interpolation_gap_threshold", text="Max Frame Gap")
            sub.label(text="Maximum gap to fill")
            sub.operator("onezeroone.interpolate_keyframes", text="Apply Effect", icon="IPO_BEZIER")

        # OSC command hint.
        box = layout.box()
        box.label(text="Send /recordframes 1 to toggle recording via OSC")


CLASSES = (ONEZEROONE_PT_recording,)
