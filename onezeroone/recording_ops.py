"""Recording operators: toggle, set scene FPS, and post-processing.

Post-processing (jitter removal, interpolation, smoothing) iterates the
existing address->binding model, resolving each binding's id_block and fcurve
via :func:`onezeroone.datapath.parse_full_data_path`.
"""

from __future__ import annotations

import bpy

from . import datapath, recording


# ---------------------------------------------------------------------------
# Toggle recording
# ---------------------------------------------------------------------------


class ONEZEROONE_OT_toggle_recording(bpy.types.Operator):
    """Start or stop OSC recording"""

    bl_idname = "onezeroone.toggle_recording"
    bl_label = "Toggle Recording"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        if recording.is_recording:
            recording.stop_recording()
            self.report({"INFO"}, "Stopped recording")
        else:
            recording.start_recording()
            self.report({"INFO"}, "Started recording")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Set scene FPS
# ---------------------------------------------------------------------------


class ONEZEROONE_OT_set_scene_fps(bpy.types.Operator):
    """Set Blender's scene frame rate to match the selected keyframe rate"""

    bl_idname = "onezeroone.set_scene_fps"
    bl_label = "Set Scene FPS Now"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        settings = context.window_manager.onezeroone_record_settings
        fps = int(settings.keyframe_rate)
        context.scene.render.fps = fps
        context.scene.frame_step = 1
        self.report({"INFO"}, f"Scene frame rate set to {fps} fps")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Helpers shared by post-processing operators
# ---------------------------------------------------------------------------


def _iter_recorded_fcurves():
    """Yield (fcurve, data_path, index) for every record-enabled binding."""
    wm = bpy.context.window_manager
    for entry in wm.onezeroone_addresses:
        for binding in entry.bindings:
            if not binding.record or not binding.data_path:
                continue
            id_block, data_path, index = datapath.parse_full_data_path(binding.data_path)
            if id_block is None or id_block.animation_data is None:
                continue
            action = id_block.animation_data.action
            if action is None:
                continue
            fcurve = action.fcurves.find(
                data_path, index=0 if index is None else index
            )
            if fcurve is not None:
                yield fcurve


# ---------------------------------------------------------------------------
# Smooth keyframes (Gaussian-like triangular kernel)
# ---------------------------------------------------------------------------


class ONEZEROONE_OT_smooth_keyframes(bpy.types.Operator):
    """Apply Gaussian-like smoothing to recorded keyframes"""

    bl_idname = "onezeroone.smooth_keyframes"
    bl_label = "Smooth Keyframes"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return len(context.window_manager.onezeroone_addresses) > 0

    def execute(self, context):
        settings = context.window_manager.onezeroone_record_settings
        smoothed = 0
        for fcurve in _iter_recorded_fcurves():
            if len(fcurve.keyframe_points) > 2:
                if self._apply_smooth(fcurve, settings.post_smooth_factor):
                    smoothed += 1
        if smoothed > 0:
            self.report({"INFO"}, f"Smoothed {smoothed} fcurves")
        else:
            self.report({"WARNING"}, "No keyframes found to smooth (need 3+ per curve)")
        return {"FINISHED"}

    def _apply_smooth(self, fcurve, smooth_factor) -> bool:
        original = [(p.co.x, p.co.y) for p in fcurve.keyframe_points]
        if len(original) < 3:
            return False
        kernel_size = max(3, int(3 + (smooth_factor * 2)))
        if kernel_size % 2 == 0:
            kernel_size += 1
        half = kernel_size // 2
        kernel = [1.0 - (abs(i - half) / (half + 0.5)) for i in range(kernel_size)]
        total = sum(kernel)
        kernel = [k / total for k in kernel]
        new_values = []
        for i in range(len(original)):
            weighted_sum = 0.0
            weights_used = 0.0
            for j in range(-half, half + 1):
                if 0 <= (i + j) < len(original):
                    w = kernel[j + half]
                    weighted_sum += original[i + j][1] * w
                    weights_used += w
            new_values.append(weighted_sum / weights_used if weights_used else original[i][1])
        for i, kf in enumerate(fcurve.keyframe_points):
            if i < len(new_values):
                kf.co.y = new_values[i]
        fcurve.update()
        return True


# ---------------------------------------------------------------------------
# Remove jitter (5-neighbour outlier test)
# ---------------------------------------------------------------------------


class ONEZEROONE_OT_remove_jitter(bpy.types.Operator):
    """Remove rogue keyframes that appear to be jitter outliers"""

    bl_idname = "onezeroone.remove_jitter"
    bl_label = "Remove Jitter"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return len(context.window_manager.onezeroone_addresses) > 0

    def execute(self, context):
        settings = context.window_manager.onezeroone_record_settings
        threshold = settings.jitter_threshold
        total_removed = 0
        for fcurve in _iter_recorded_fcurves():
            total_removed += self._remove_jitter_from_curve(fcurve, threshold)
        if total_removed > 0:
            self.report({"INFO"}, f"Removed {total_removed} jitter keyframes")
        else:
            self.report({"INFO"}, "No jitter keyframes found to remove")
        return {"FINISHED"}

    def _remove_jitter_from_curve(self, fcurve, threshold) -> int:
        if len(fcurve.keyframe_points) < 5:
            return 0
        keyframes = [(kf.co.x, kf.co.y, i) for i, kf in enumerate(fcurve.keyframe_points)]
        keyframes.sort(key=lambda k: k[0])
        to_remove = []
        for i in range(2, len(keyframes) - 2):
            p0 = keyframes[i - 2][1]
            p1 = keyframes[i - 1][1]
            p2 = keyframes[i][1]
            p3 = keyframes[i + 1][1]
            p4 = keyframes[i + 2][1]
            expected = (p0 + p1 + p3 + p4) / 4.0
            diff = abs(p2 - expected)
            local_range = max(p0, p1, p2, p3, p4) - min(p0, p1, p2, p3, p4)
            if local_range == 0:
                local_range = 0.0001
            if (diff / local_range) > threshold:
                to_remove.append(keyframes[i][2])
        for idx in sorted(to_remove, reverse=True):
            fcurve.keyframe_points.remove(fcurve.keyframe_points[idx])
        if to_remove:
            fcurve.update()
        return len(to_remove)


# ---------------------------------------------------------------------------
# Interpolate missing frames (bezier)
# ---------------------------------------------------------------------------


def _bezier_interpolate(start_value: float, end_value: float, t: float) -> float:
    """Smoothstep (cubic) interpolation between two values."""
    return start_value + (end_value - start_value) * (3 * t * t - 2 * t * t * t)


class ONEZEROONE_OT_interpolate_keyframes(bpy.types.Operator):
    """Fill in missing frames using bezier interpolation"""

    bl_idname = "onezeroone.interpolate_keyframes"
    bl_label = "Interpolate Missing Frames"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return len(context.window_manager.onezeroone_addresses) > 0

    def execute(self, context):
        settings = context.window_manager.onezeroone_record_settings
        gap_threshold = settings.interpolation_gap_threshold
        total_changes = 0
        for fcurve in _iter_recorded_fcurves():
            total_changes += self._interpolate_missing_frames(fcurve, gap_threshold)
        if total_changes > 0:
            self.report({"INFO"}, f"Processed {total_changes} keyframe changes")
        else:
            self.report({"INFO"}, "No gaps or identical keyframes found that need processing")
        return {"FINISHED"}

    def _interpolate_missing_frames(self, fcurve, gap_threshold) -> int:
        if len(fcurve.keyframe_points) < 2:
            return 0
        keyframes = [(kf.co.x, kf.co.y, i) for i, kf in enumerate(fcurve.keyframe_points)]
        keyframes.sort(key=lambda k: k[0])

        # Remove sequences of identical keyframes (keep first and last of each run).
        identical_sequences = []
        current_sequence = []
        for i in range(len(keyframes) - 1):
            if abs(keyframes[i][1] - keyframes[i + 1][1]) < 0.0001:
                if not current_sequence:
                    current_sequence = [i]
                current_sequence.append(i + 1)
            else:
                if current_sequence and len(current_sequence) > 1:
                    identical_sequences.append(current_sequence)
                current_sequence = []
        if current_sequence and len(current_sequence) > 1:
            identical_sequences.append(current_sequence)

        indices_to_remove = []
        for sequence in identical_sequences:
            indices_to_remove.extend(keyframes[idx][2] for idx in sequence[1:-1])
        removed_count = 0
        for idx in sorted(indices_to_remove, reverse=True):
            fcurve.keyframe_points.remove(fcurve.keyframe_points[idx - removed_count])
            removed_count += 1

        if removed_count > 0:
            fcurve.update()
            keyframes = [(kf.co.x, kf.co.y, i) for i, kf in enumerate(fcurve.keyframe_points)]
            keyframes.sort(key=lambda k: k[0])

        # Interpolate gaps.
        new_keyframes = []
        for i in range(len(keyframes) - 1):
            current_frame = int(keyframes[i][0])
            next_frame = int(keyframes[i + 1][0])
            frame_gap = next_frame - current_frame
            if frame_gap > gap_threshold:
                frames_to_add = frame_gap - 1
                p0 = keyframes[i][1]
                p3 = keyframes[i + 1][1]
                for j in range(1, frames_to_add + 1):
                    t = j / (frames_to_add + 1)
                    frame = current_frame + j
                    value = _bezier_interpolate(p0, p3, t)
                    new_keyframes.append((frame, value))

        for frame, value in new_keyframes:
            kf = fcurve.keyframe_points.insert(frame, value)
            kf.interpolation = "BEZIER"

        if new_keyframes or removed_count > 0:
            fcurve.update()
        return len(new_keyframes) + removed_count


CLASSES = (
    ONEZEROONE_OT_toggle_recording,
    ONEZEROONE_OT_set_scene_fps,
    ONEZEROONE_OT_smooth_keyframes,
    ONEZEROONE_OT_remove_jitter,
    ONEZEROONE_OT_interpolate_keyframes,
)
