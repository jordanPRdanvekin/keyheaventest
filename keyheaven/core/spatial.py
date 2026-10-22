from .._imports import *
from .logger import *
from .constants import *
from .rng import *
from .validator import *
from .actions_compat import *
from .targets import *
from .base_backup import *
from .transaction import *
from .protection import *
from .motion_analysis import *
from .min_gap import *
from .randomizer import *
from .curves import *
from .chains import *
from .secondary import *
class SpatialSampler:
    """Samples the world state of the spatial targets.

    The transform is resolved analytically from the animated channels whenever
    the target allows it, which removes a depsgraph update per sampled frame.
    The geometry of the target is measured with its real bounding box and a
    BVH of the evaluated mesh, so the clearance respects the actual size of
    the objects and not only the user clearance sphere.
    """

    def __init__(self, targets, context):
        self.targets = list(targets)
        self.context = context
        try:
            context.view_layer.update()
        except Exception:
            pass
        self.depsgraph = context.evaluated_depsgraph_get()
        try:
            self.depsgraph.update()
        except Exception:
            pass
        self.analytic = []
        self.location_curves = []
        self.rotation_euler_curves = []
        self.rotation_quat_curves = []
        self.scale_curves = []
        self.local_extents = []
        self.trees = []
        self._position_cache = {}
        self._pair_cache = {}
        self._matrix_cache = {}
        self._index_by_target = {}
        for position, target in enumerate(self.targets):
            self._index_by_target[id(target)] = position
        self._prepare_all()
        self._needs_depsgraph = not all(self.analytic)

    def target_index(self, target):
        """Returns the position of a target inside the sampler."""
        return self._index_by_target.get(id(target), 0)

    def _location_curves(self, target):
        prefix = TargetResolver.channel_prefix(target)
        data_path = f"{prefix}location"
        curves = {}
        for fcurve in TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY"):
            if fcurve.data_path == data_path:
                curves[fcurve.array_index] = fcurve
        return curves

    def _curve_group(self, target, channel):
        prefix = TargetResolver.channel_prefix(target)
        data_path = f"{prefix}{channel}"
        curves = {}
        for fcurve in TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY"):
            if fcurve.data_path == data_path:
                curves[fcurve.array_index] = fcurve
        return curves

    def _can_be_analytic(self, target):
        if TargetResolver.is_bone(target) or TargetResolver.is_shape_key(target):
            return False
        obj = TargetResolver.get_owner(target)
        if obj is None or getattr(obj, "parent", None) is not None:
            return False
        if len(getattr(obj, "constraints", [])) > 0:
            return False
        curves = self._location_curves(target)
        return all(index in curves for index in range(3))

    def _prepare_all(self):
        for target in self.targets:
            self.analytic.append(self._can_be_analytic(target))
            self.location_curves.append(self._location_curves(target))
            self.rotation_euler_curves.append(self._curve_group(target, "rotation_euler"))
            self.rotation_quat_curves.append(self._curve_group(target, "rotation_quaternion"))
            self.scale_curves.append(self._curve_group(target, "scale"))
            self.local_extents.append(self._local_extents(target))
            self.trees.append(self._build_tree(target))

    def _local_extents(self, target):
        """Half size of the local bounding box of the target geometry."""
        obj = TargetResolver.get_owner(target)
        if obj is None:
            return None
        try:
            corners = [Vector(corner) for corner in obj.bound_box]
        except Exception:
            return None
        if not corners:
            return None
        minimum = Vector(
            (min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners))
        )
        maximum = Vector(
            (max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners))
        )
        return (maximum - minimum) * 0.5

    def _build_tree(self, target):
        if TargetResolver.is_bone(target) or TargetResolver.is_shape_key(target):
            return None
        obj = TargetResolver.get_owner(target)
        if obj is None or getattr(obj, "type", "") not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            return None
        for attempt in range(2):
            try:
                return BVHTree.FromObject(
                    obj, self.depsgraph, deform=True, cage=False, epsilon=0.0
                )
            except Exception as exc:
                if attempt == 0:
                    try:
                        self.depsgraph.update()
                    except Exception:
                        pass
                    continue
                KeyHeavenLogger.log_warning(
                    f"Spatial: BVH unavailable for '{getattr(obj, 'name', '?')}' ({exc})"
                )
                return None
        return None

    def _evaluate(self, curves, frame, default):
        values = []
        for index in range(len(default)):
            fcurve = curves.get(index)
            if fcurve is None:
                values.append(default[index])
            else:
                values.append(float(fcurve.evaluate(float(frame))))
        return values

    def matrix_at(self, index, frame):
        """Returns the world matrix of a target at the given frame."""
        cached = self._matrix_cache.get((index, frame))
        if cached is not None:
            return cached
        target = self.targets[index]
        obj = TargetResolver.get_owner(target)
        if obj is None:
            return Matrix.Identity(4)
        if self.analytic[index]:
            location = self._evaluate(
                self.location_curves[index], frame, tuple(obj.location)
            )
            quat_curves = self.rotation_quat_curves[index]
            euler_curves = self.rotation_euler_curves[index]
            if len(quat_curves) == 4:
                quaternion = self._evaluate(
                    quat_curves, frame, tuple(obj.rotation_quaternion)
                )
                rotation = Quaternion(quaternion).to_matrix().to_4x4()
            elif len(euler_curves) == 3:
                euler = self._evaluate(euler_curves, frame, tuple(obj.rotation_euler))
                mode = getattr(obj, "rotation_mode", "XYZ")
                if mode not in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"):
                    mode = "XYZ"
                rotation = Euler(euler, mode).to_matrix().to_4x4()
            else:
                rotation = obj.matrix_world.to_3x3().normalized().to_4x4()
            scale = self._evaluate(self.scale_curves[index], frame, tuple(obj.scale))
            matrix = Matrix.Translation(Vector(location)) @ rotation
            matrix = matrix @ Matrix.Diagonal(Vector(scale).to_4d())
        else:
            matrix = obj.matrix_world.copy()
        self._matrix_cache[(index, frame)] = matrix
        return matrix

    def rotation_at(self, index, frame):
        """Returns the pure rotation of a target at the given frame."""
        matrix = self.matrix_at(index, frame)
        try:
            _, quaternion, _ = matrix.decompose()
            return quaternion.to_matrix()
        except Exception:
            return matrix.to_3x3().normalized()

    def position(self, index, frame):
        """Returns the world position of a target at the given frame."""
        if self.analytic[index]:
            return self.matrix_at(index, frame).translation.copy()
        return self._depsgraph_position(index)

    def _depsgraph_position(self, index):
        target = self.targets[index]
        try:
            if TargetResolver.is_bone(target):
                owner = TargetResolver.get_owner(target)
                eval_obj = owner.evaluated_get(self.depsgraph)
                eval_bone = eval_obj.pose.bones.get(target.name)
                if eval_bone is None:
                    return None
                return eval_obj.matrix_world @ eval_bone.head
            eval_obj = target.evaluated_get(self.depsgraph)
            return eval_obj.matrix_world.translation.copy()
        except Exception:
            return None

    def positions(self, frame):
        """Returns the sampled positions, cached between solver passes."""
        cached = self._position_cache.get(frame)
        if cached is not None:
            return cached
        if self._needs_depsgraph:
            try:
                self.context.scene.frame_set(int(frame))
                self.depsgraph.update()
            except Exception:
                pass
        result = [self.position(index, frame) for index in range(len(self.targets))]
        self._position_cache[frame] = result
        return result

    def invalidate(self, frames=None):
        """Drops the cached samples.

        A correction changes the whole curve, so the samples of every frame
        are invalidated after a solver pass.
        """
        self._position_cache.clear()
        self._pair_cache.clear()
        self._matrix_cache.clear()

    def candidate_pairs(self, frame, radii, margin):
        """Returns the broad phase candidates of a frame, cached."""
        cached = self._pair_cache.get(frame)
        if cached is not None:
            return cached
        pairs = SpatialDeoverlapEngine._candidate_pairs(
            self.positions(frame), radii, margin
        )
        self._pair_cache[frame] = pairs
        return pairs

    def scaled_rotation_at(self, index, frame):
        """Returns the rotation and scale of the target at the given frame."""
        return self.matrix_at(index, frame).to_3x3()

    def bound_radius(self, index, frame=None):
        """Bounding radius of the target geometry in world units."""
        extents = self.local_extents[index]
        if extents is None:
            return 0.0
        matrix = self.scaled_rotation_at(index, frame if frame is not None else 0)
        value = 0.0
        for axis in range(3):
            column = matrix.col[axis]
            value += (column.x * column.x + column.y * column.y + column.z * column.z) ** 0.5 * extents[axis]
        return value

    def extent_along(self, index, direction, frame):
        """Extent of the target geometry along a world direction."""
        extents = self.local_extents[index]
        if extents is None:
            return 0.0
        matrix = self.scaled_rotation_at(index, frame)
        value = 0.0
        for axis in range(3):
            column = matrix.col[axis]
            value += abs(direction.dot(column)) * extents[axis]
        return value

    def surface_state(self, index, world_point, frame):
        """Returns the distance to the surface and whether the point is inside.

        The inside test uses the surface normal: a point is inside when the
        vector to the surface points against the outward normal.
        """
        tree = self.trees[index]
        if tree is None:
            return None, False
        try:
            inverse = self.matrix_at(index, frame).inverted()
        except Exception:
            return None, False
        try:
            local_point = inverse @ world_point
        except Exception:
            return None, False
        try:
            hit = tree.find_nearest(local_point)
        except Exception:
            return None, False
        if not hit or hit[0] is None:
            return None, False
        location = hit[0]
        normal = hit[1]
        distance = float(hit[3])
        inside = False
        try:
            direction = local_point - location
            if direction.length > 1e-9 and normal.length > 1e-9:
                inside = direction.normalized().dot(normal.normalized()) < 0.0
        except Exception:
            inside = False
        return distance, inside


class SpatialDeoverlapEngine:
    """Clearance-volume solver: detect intrusion, apply minimal local corrections."""

    @staticmethod
    def _props(context):
        try:
            return context.scene.keyheaven
        except Exception:
            return None

    @staticmethod
    def clearance_radius_for(target, context):
        props = SpatialDeoverlapEngine._props(context)
        radius = 0.0
        if props is not None:
            radius = float(getattr(props, "clearance_edit_radius", 0.0) or 0.0)
            floor = float(getattr(props, "deoverlap_min_dist", 0.0) or 0.0)
            radius = max(radius, floor)
        if radius <= 0.0:
            radius = TargetResolver.get_target_dimension(target) * 0.5
        return max(0.01, float(radius))

    @staticmethod
    def _margin(context):
        props = SpatialDeoverlapEngine._props(context)
        if props is None:
            return 0.2
        return max(0.0, float(getattr(props, "deoverlap_margin", 0.2)))

    @staticmethod
    def _max_target_distance(context):
        """Maximum distance the solver targets between two targets."""
        props = SpatialDeoverlapEngine._props(context)
        if props is None:
            return 0.0
        return max(0.0, float(getattr(props, "deoverlap_max_dist", 0.0) or 0.0))

    @staticmethod
    def _orbit_enabled(context):
        props = SpatialDeoverlapEngine._props(context)
        return bool(getattr(props, "deoverlap_orbit", True)) if props is not None else True

    @staticmethod
    def _return_enabled(context):
        props = SpatialDeoverlapEngine._props(context)
        if props is not None:
            return bool(getattr(props, "deoverlap_return_to_path", True))
        return True

    @staticmethod
    def _motion_target_position(target, depsgraph):
        try:
            if TargetResolver.is_shape_key(target):
                return None
            if TargetResolver.is_bone(target):
                owner = TargetResolver.get_owner(target)
                eval_obj = owner.evaluated_get(depsgraph)
                eval_bone = eval_obj.pose.bones.get(target.name)
                if eval_bone is None:
                    return None
                return eval_obj.matrix_world @ eval_bone.head
            eval_obj = target.evaluated_get(depsgraph)
            return eval_obj.matrix_world.translation.copy()
        except Exception:
            return None

    @staticmethod
    def _sample_frames(targets, context, sample_step=1):
        ranges = []
        for target in targets:
            start_f, end_f = BoundaryLockEngine.get_boundary_frames(target, context)
            ranges.append((float(start_f), float(end_f)))
        if not ranges:
            return []
        start_f = min(r[0] for r in ranges)
        end_f = max(r[1] for r in ranges)
        step = max(1, int(sample_step))
        ordered = list(range(int(start_f), int(end_f) + 1, step))
        if len(ordered) > 600:
            stride = int(math.ceil(len(ordered) / 600.0))
            ordered = ordered[::stride]
        return [frame for frame in ordered if frame >= 0]

    @staticmethod
    def _target_movable(target):
        try:
            if TargetResolver.is_shape_key(target):
                return False
            fcurves = TargetResolver.get_target_fcurves(target, scope="TRANSFORM_ONLY")
            if any(fc.data_path.endswith("location") for fc in fcurves):
                return True
            owner = TargetResolver.get_owner(target)
            anim_data = getattr(owner, "animation_data", None)
            return bool(anim_data and anim_data.action)
        except Exception:
            return False

    @staticmethod
    def _candidate_pairs(positions, radii, margin):
        """Broad phase: returns the target pairs that can share clearance.

        A uniform spatial hash keeps the solver linear in the number of nearby
        targets instead of testing every pair on every sampled frame.
        """
        cell = max(1e-3, max(radii) * 2.0 + margin) if radii else 1.0
        grid = {}
        for index, position in enumerate(positions):
            if position is None:
                continue
            radius = radii[index]
            min_x = int(math.floor((position.x - radius) / cell))
            max_x = int(math.floor((position.x + radius) / cell))
            min_y = int(math.floor((position.y - radius) / cell))
            max_y = int(math.floor((position.y + radius) / cell))
            min_z = int(math.floor((position.z - radius) / cell))
            max_z = int(math.floor((position.z + radius) / cell))
            for cell_x in range(min_x, max_x + 1):
                for cell_y in range(min_y, max_y + 1):
                    for cell_z in range(min_z, max_z + 1):
                        grid.setdefault((cell_x, cell_y, cell_z), []).append(index)
        pairs = set()
        for bucket in grid.values():
            if len(bucket) < 2:
                continue
            for first in range(len(bucket)):
                for second in range(first + 1, len(bucket)):
                    low = min(bucket[first], bucket[second])
                    high = max(bucket[first], bucket[second])
                    pairs.add((low, high))
        return pairs

    @staticmethod
    def _pair_violations(targets, context, frames, sampler=None):
        """Detects the clearance violations of every candidate pair."""
        violations = []
        radii = [SpatialDeoverlapEngine.clearance_radius_for(t, context) for t in targets]
        margin = SpatialDeoverlapEngine._margin(context)
        if sampler is None:
            sampler = SpatialSampler(targets, context)
        effective_radii = [
            max(radii[index], sampler.bound_radius(index))
            for index in range(len(targets))
        ]

        samples = {}
        for frame in frames:
            samples[frame] = sampler.positions(frame)

        velocities = {}
        frame_list = list(frames)
        for index in range(len(targets)):
            for position, frame in enumerate(frame_list):
                if position == 0 or position == len(frame_list) - 1:
                    continue
                previous = samples[frame_list[position - 1]][index]
                following = samples[frame_list[position + 1]][index]
                if previous is None or following is None:
                    continue
                delta = following - previous
                if delta.length <= 1e-8:
                    continue
                velocities[(index, frame)] = delta.normalized()

        for frame in frames:
            positions = samples[frame]
            for i, j in sampler.candidate_pairs(frame, effective_radii, margin):
                if positions[i] is None or positions[j] is None:
                    continue
                delta = positions[i] - positions[j]
                distance = delta.length
                if distance <= 1e-8:
                    direction = Vector((1.0, 0.0, 0.0))
                else:
                    direction = delta.normalized()
                sphere_required = radii[i] + radii[j] + margin
                geometry_required = (
                    sampler.extent_along(i, direction, frame)
                    + sampler.extent_along(j, direction, frame)
                    + margin
                )
                surface_ij, inside_ij = sampler.surface_state(i, positions[j], frame)
                surface_ji, inside_ji = sampler.surface_state(j, positions[i], frame)
                mesh_conflict = inside_ij or inside_ji
                geometry_conflict = distance < geometry_required - TIME_EPS
                if (
                    distance >= sphere_required - TIME_EPS
                    and not mesh_conflict
                    and not geometry_conflict
                ):
                    continue
                required = max(sphere_required, geometry_required)
                penetration = required - distance
                if mesh_conflict and penetration <= 1e-6:
                    penetration = max(1e-3, margin * 0.5)
                    required = distance + penetration
                max_distance = SpatialDeoverlapEngine._max_target_distance(context)
                if max_distance > 0.0 and distance + penetration > max_distance:
                    penetration = max(0.0, max_distance - distance)
                if penetration <= 1e-6:
                    continue
                violations.append(
                    {
                        "frame": frame,
                        "i": i,
                        "j": j,
                        "penetration": float(penetration),
                        "direction": direction,
                        "positions": (positions[i].copy(), positions[j].copy()),
                        "velocity": velocities.get((i, frame))
                        or velocities.get((j, frame)),
                    }
                )
        return violations

    @staticmethod
    def _extend_violations(violations, frames):
        """Keeps the last correction of every pair for the remaining frames."""
        last_by_pair = {}
        for item in violations:
            key = (item["i"], item["j"])
            current = last_by_pair.get(key)
            if current is None or item["frame"] > current["frame"]:
                last_by_pair[key] = item
        extended = list(violations)
        for item in last_by_pair.values():
            for frame in frames:
                if frame <= item["frame"]:
                    continue
                clone = dict(item)
                clone["frame"] = frame
                extended.append(clone)
        return extended

    @staticmethod
    def intrusion_frames(targets, context, sample_step=1):
        if not HAS_BPY or not context or not targets:
            return []
        original_frame = context.scene.frame_current
        try:
            frames = SpatialDeoverlapEngine._sample_frames(targets, context, sample_step)
            sampler = SpatialSampler(targets, context)
            violations = SpatialDeoverlapEngine._pair_violations(
                targets, context, frames, sampler
            )
            return [
                (item["frame"], item["i"], item["j"], item["penetration"])
                for item in violations
            ]
        except Exception as e:
            KeyHeavenLogger.log_error("SpatialDeoverlapEngine.intrusion_frames", e)
            return []
        finally:
            try:
                context.scene.frame_set(original_frame)
            except Exception:
                pass

    @staticmethod
    def _location_fcurves(target, create=False):
        owner = ActionAdapter.get_owner(target)
        prefix = TargetResolver.channel_prefix(target)
        data_path = f"{prefix}location"
        fcurves = [
            fc
            for fc in ActionAdapter.get_fcurves(target)
            if fc.data_path == data_path
        ]
        if len(fcurves) < 3 and create:
            created = ActionAdapter.ensure_fcurves(target, data_path, [0, 1, 2])
            fcurves = [fc for fc in created if fc is not None]
        return {fc.array_index: fc for fc in fcurves}

    @staticmethod
    def _local_delta(target, world_delta, sampler, frame):
        """Converts a world correction into the local space of the target.

        Only the rotation is used: the scale of the object must not divide the
        correction, otherwise a scaled object would be moved by a fraction of
        the requested distance.
        """
        try:
            if TargetResolver.is_bone(target):
                owner = TargetResolver.get_owner(target)
                eval_obj = owner.evaluated_get(sampler.depsgraph)
                eval_bone = eval_obj.pose.bones.get(target.name)
                if eval_bone is None:
                    return world_delta.copy()
                matrix = eval_obj.matrix_world @ eval_bone.matrix
                _, quaternion, _ = matrix.decompose()
                rotation = quaternion.to_matrix()
            else:
                rotation = sampler.rotation_at(sampler.target_index(target), frame)
            return rotation.inverted() @ world_delta
        except Exception:
            return world_delta.copy()

    @staticmethod
    def _apply_curve_corrections(fc, frame_deltas, context, result, min_gap):
        """Applies the spatial corrections of a curve in a single batch.

        The corrections are grouped per curve so the curve is only rebuilt
        once, instead of once per corrected keyframe.
        """
        if not frame_deltas:
            return
        points = list(fc.keyframe_points)
        by_frame = {}
        for kp in points:
            by_frame[round(float(kp.co[0]), TIME_ROUND)] = kp
        ordered_points = sorted(points, key=lambda kp: float(kp.co[0]))
        timeline = [float(kp.co[0]) for kp in ordered_points]
        pending = []
        for frame, delta in sorted(frame_deltas.items()):
            kp = by_frame.get(round(float(frame), TIME_ROUND))
            if kp is None:
                position = bisect.bisect_left(timeline, float(frame))
                for candidate_index in (position - 1, position):
                    if 0 <= candidate_index < len(ordered_points):
                        candidate = ordered_points[candidate_index]
                        if abs(float(candidate.co[0]) - float(frame)) <= KEY_PROXIMITY_EPS:
                            kp = candidate
                            break
            if kp is not None:
                if KeyframeProtectionEngine.is_value_locked(fc, kp):
                    result.skipped_protected += 1
                    continue
                kp.co[1] += delta
                result.modified_keyframes += 1
                continue
            neighbours = []
            position = bisect.bisect_left(timeline, float(frame))
            if position > 0:
                neighbours.append(ordered_points[position - 1])
            if position < len(ordered_points):
                neighbours.append(ordered_points[position])
            if min_gap > 0.0:
                blocked = any(
                    abs(float(value.co[0]) - float(frame)) <= min_gap
                    and abs(float(value.co[0]) - float(frame)) > 1e-4
                    for value in neighbours
                )
                if blocked:
                    continue
            if any(
                KeyframeProtectionEngine.is_timing_locked(fc, value)
                for value in neighbours
            ):
                result.skipped_protected += 1
                continue
            pending.append((float(frame), float(delta)))
            bisect.insort(timeline, float(frame))
            ordered_points.insert(position, _PendingKey(frame))
        if not pending:
            fc.update()
            return
        new_keys = []
        for frame, delta in pending:
            new_keys.append((frame, fc.evaluate(frame) + delta))
        for frame, value in sorted(new_keys):
            kp = fc.keyframe_points.insert(frame=frame, value=value, options={"FAST"})
            kp.interpolation = "BEZIER"
        fc.keyframe_points.sort()
        fc.update()
        result.modified_keyframes += len(new_keys)


    @staticmethod
    def _protected_violations(violations, targets, context):
        """Returns the violations that sit on protected boundary frames."""
        boundary_enabled = BoundaryLockEngine.is_enabled(context)
        if not boundary_enabled:
            return []
        bounds = [
            BoundaryLockEngine.get_boundary_frames(target, context) for target in targets
        ]
        protected = []
        for item in violations:
            for index in (item["i"], item["j"]):
                start_f, end_f = bounds[index]
                if BoundaryLockEngine.is_locked_boundary(
                    item["frame"], start_f, end_f, boundary_enabled
                ):
                    protected.append(item)
                    break
        return protected

    @staticmethod
    def _sample_velocity(sampler, index, frame):
        """Velocity of a target derived from the sampled positions."""
        previous = sampler.position(index, frame - 1)
        following = sampler.position(index, frame + 1)
        if previous is None or following is None:
            return None
        delta = following - previous
        if delta.length <= 1e-8:
            return None
        return delta.normalized()

    @staticmethod
    def _apply_violations(targets, context, violations, result, sampler=None):
        movable = [SpatialDeoverlapEngine._target_movable(target) for target in targets]
        orbit = SpatialDeoverlapEngine._orbit_enabled(context)
        min_gap = MinGapEngine.gap_for(context)
        boundary_enabled = BoundaryLockEngine.is_enabled(context)
        bounds = [
            BoundaryLockEngine.get_boundary_frames(target, context) for target in targets
        ]
        if sampler is None:
            sampler = SpatialSampler(targets, context)

        world_deltas = {}
        for item in violations:
            i, j = item["i"], item["j"]
            if not movable[i] and not movable[j]:
                result.add_warning("Spatial: both targets are static; intrusion left unresolved")
                continue
            direction = item["direction"].copy()
            if orbit:
                velocity = item.get("velocity")
                if velocity is None:
                    velocity = SpatialDeoverlapEngine._sample_velocity(
                        sampler, i if movable[i] else j, item["frame"]
                    )
                if velocity is not None and abs(direction.dot(velocity)) > 0.85:
                    tangent = velocity.cross(Vector((0.0, 0.0, 1.0)))
                    if tangent.length <= 1e-5:
                        tangent = velocity.cross(Vector((0.0, 1.0, 0.0)))
                    if tangent.length > 1e-5:
                        direction = tangent.normalized()
            push = item["penetration"]
            if movable[i] and movable[j]:
                share_i = share_j = push * 0.5
            elif movable[i]:
                share_i, share_j = push, 0.0
            else:
                share_i, share_j = 0.0, push

            if movable[i] and share_i > 0.0:
                key = (i, item["frame"])
                world_deltas[key] = world_deltas.get(key, Vector((0.0, 0.0, 0.0))) + (
                    direction * share_i
                )
            if movable[j] and share_j > 0.0:
                key = (j, item["frame"])
                world_deltas[key] = world_deltas.get(key, Vector((0.0, 0.0, 0.0))) - (
                    direction * share_j
                )

        curve_cache = {}
        corrections = {}
        for (target_index, frame), world_delta in world_deltas.items():
            target = targets[target_index]
            start_f, end_f = bounds[target_index]
            if boundary_enabled and BoundaryLockEngine.is_locked_boundary(
                frame, start_f, end_f, True
            ):
                result.skipped_protected += 1
                continue
            fcurves = curve_cache.get(target_index)
            if fcurves is None:
                fcurves = SpatialDeoverlapEngine._location_fcurves(target, create=True)
                curve_cache[target_index] = fcurves
            if not fcurves:
                continue
            local_delta = SpatialDeoverlapEngine._local_delta(
                target, world_delta, sampler, frame
            )
            for index in range(3):
                fc = fcurves.get(index)
                if fc is None:
                    continue
                delta = local_delta[index]
                if abs(delta) <= 1e-6:
                    continue
                key = (target_index, index)
                corrections.setdefault(key, {})[frame] = delta

        for (target_index, index), frame_deltas in corrections.items():
            fc = curve_cache[target_index].get(index)
            if fc is None:
                continue
            SpatialDeoverlapEngine._apply_curve_corrections(
                fc, frame_deltas, context, result, min_gap
            )
            result.modified_fcurves += 1

    @staticmethod
    def deoverlap_targets(targets, context):
        result = OperationResult("Spatial Clearance")
        if not HAS_BPY or not context or not targets:
            result.add_warning("No targets available for spatial clearance")
            return result

        original_frame = context.scene.frame_current
        scene_start = context.scene.frame_start
        scene_end = context.scene.frame_end
        try:
            props = SpatialDeoverlapEngine._props(context)
            max_passes = int(getattr(props, "deoverlap_iterations", 20)) if props else 20
            max_passes = max(1, min(32, max_passes))
            frames = SpatialDeoverlapEngine._sample_frames(targets, context)
            result.processed_targets = len(targets)
            sampler = SpatialSampler(targets, context)

            previous_penetration = None
            for _pass in range(max_passes):
                violations = SpatialDeoverlapEngine._pair_violations(
                    targets, context, frames, sampler
                )
                if not violations:
                    break
                protected = SpatialDeoverlapEngine._protected_violations(
                    violations, targets, context
                )
                fixable = [item for item in violations if item not in protected]
                if not fixable:
                    break
                penetration_total = sum(item["penetration"] for item in fixable)
                if previous_penetration is not None:
                    if penetration_total > previous_penetration * 0.95:
                        result.add_warning(
                            "Spatial: the solver stopped because the corrections "
                            "stopped reducing the intrusions"
                        )
                        break
                previous_penetration = penetration_total
                if not SpatialDeoverlapEngine._return_enabled(context):
                    violations = SpatialDeoverlapEngine._extend_violations(
                        violations, frames
                    )
                SpatialDeoverlapEngine._apply_violations(
                    targets, context, violations, result, sampler
                )
                context.scene.frame_set(original_frame)
                context.scene.frame_start = scene_start
                context.scene.frame_end = scene_end
                sampler.invalidate()

            remaining = SpatialDeoverlapEngine._pair_violations(
                targets, context, frames, sampler
            )
            if remaining:
                protected = SpatialDeoverlapEngine._protected_violations(
                    remaining, targets, context
                )
                result.add_warning(
                    f"Spatial: {len(remaining)} clearance intrusion(s) remain after bounded passes"
                    + (
                        f" ({len(protected)} of them on protected boundary frames)"
                        if protected
                        else ""
                    )
                )
            return result
        except Exception as e:
            KeyHeavenLogger.log_error("SpatialDeoverlapEngine.deoverlap_targets", e)
            result.add_error(str(e))
            return result
        finally:
            try:
                context.scene.frame_set(original_frame)
                context.scene.frame_start = scene_start
                context.scene.frame_end = scene_end
            except Exception:
                pass


class _PendingKey:
    """Placeholder used to keep the ordered timeline in sync with the inserts."""

    __slots__ = ("co",)

    def __init__(self, frame):
        self.co = (float(frame), 0.0)
