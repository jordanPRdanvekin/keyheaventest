from ._imports import *
class KeyHeaven_Properties(bpy.types.PropertyGroup):
    master_intensity: bpy.props.FloatProperty(
        name="Master Intensity", default=1.0, min=0.0, max=2.0, subtype="PERCENTAGE",
        description="Global intensity multiplier (0% - 200%) applied across procedural tools",
    )

    boundary_lock_enabled: bpy.props.BoolProperty(
        name="Boundary Protection", default=True,
        description="Keep first and last keyframes protected (immutable value and time)",
    )

    randomizer_iterations: bpy.props.IntProperty(
        name="Interactions / Passes", default=10, min=1, max=100,
        description="Number of temporal slack redistribution passes",
    )
    min_gap: bpy.props.FloatProperty(
        name="Min Gap (Magnitude)", default=0.10, min=0.0, max=50.0,
        description="Minimum frame spacing magnitude applied according to the Min Gap mode",
    )
    min_gap_mode: bpy.props.EnumProperty(
        name="Min Gap Mode",
        description="How the temporal minimum gap is enforced",
        items=[
            ("SAFE", "Safe", "Enforce the temporal minimum gap"),
            ("OFF", "Off", "Do not apply the gap restriction"),
            ("RELAXED", "Relaxed", "Allow deliberate proximity while keeping F-Curves valid"),
        ],
        default="SAFE",
    )

    rhythm_mode: bpy.props.EnumProperty(
        name="Pattern",
        description="Procedural timing distribution algorithm",
        items=[
            ("ORGANIC", "Organic (Default)", "Smooth, irregular, temporally coherent variation"),
            ("ROBOTIC", "Robotic", "Rigid, discrete, mechanical and predictable variation"),
            ("RANDOM", "Random", "Unstructured variation using a local RNG"),
        ],
        default="ORGANIC",
    )
    random_seed: bpy.props.IntProperty(
        name="Random Seed", default=-1, min=-1, max=2147483647,
        description="Deterministic seed for Random mode (-1 uses system entropy)",
    )

    var_x_min: bpy.props.FloatProperty(
        name="Time Offset Min", default=0.0, min=0.0, max=10.0,
        description="Minimum temporal Slack Redistribution range",
    )
    var_x_max: bpy.props.FloatProperty(
        name="Time Offset Max", default=2.0, min=0.0, max=10.0,
        description="Maximum temporal Slack Redistribution range",
    )

    rand_time: bpy.props.BoolProperty(name="Randomize Time", default=True, description="Redistribute keyframe timing")
    rand_pos_x: bpy.props.BoolProperty(name="Position X", default=False, description="Randomize position X values")
    rand_pos_y: bpy.props.BoolProperty(name="Position Y", default=False, description="Randomize position Y values")
    rand_pos_z: bpy.props.BoolProperty(name="Position Z", default=False, description="Randomize position Z values")
    rand_rot: bpy.props.BoolProperty(name="Rotation", default=False, description="Randomize rotation values")
    rand_scale: bpy.props.BoolProperty(name="Scale", default=False, description="Randomize scale values")

    quick_anim_keys: bpy.props.IntProperty(
        name="Keyframe Count", default=4, min=4, max=100,
        description="Number of keyframe poses to generate",
    )

    select_target_pct: bpy.props.FloatProperty(
        name="Target Selection Ratio (%)", default=50.0, min=1.0, max=100.0,
        description="Percentage of targets to randomly select",
    )
    select_key_pct: bpy.props.FloatProperty(
        name="Keyframe Selection Ratio (%)", default=50.0, min=1.0, max=100.0,
        description="Percentage of keyframes to randomly select",
    )
    selection_pool_mode: bpy.props.EnumProperty(
        name="Selection Pool",
        description="Pool used by Random Selection",
        items=[
            ("ALL", "All Eligible", "Reselect from all eligible targets/keyframes"),
            ("CURRENT", "Current Selection", "Restrict the pool to the current selection"),
        ],
        default="ALL",
    )

    breathing_rate_min: bpy.props.FloatProperty(name="Cycle Frequency Min", default=0.03, min=0.001, max=2.0, description="Minimum breathing cycle frequency")
    breathing_rate_max: bpy.props.FloatProperty(name="Cycle Frequency Max", default=0.08, min=0.001, max=2.0, description="Maximum breathing cycle frequency")
    breathing_amp_min: bpy.props.FloatProperty(name="Scale Amplitude Min", default=0.005, min=0.0, max=1.0, description="Minimum subtle breathing scale amplitude")
    breathing_amp_max: bpy.props.FloatProperty(name="Scale Amplitude Max", default=0.02, min=0.0, max=1.0, description="Maximum subtle breathing scale amplitude")

    squash_factor_min: bpy.props.FloatProperty(name="Velocity Factor Min", default=0.01, min=0.001, max=2.0, description="Minimum velocity squash sensitivity")
    squash_factor_max: bpy.props.FloatProperty(name="Velocity Factor Max", default=0.05, min=0.001, max=2.0, description="Maximum velocity squash sensitivity")

    secondary_intensity: bpy.props.FloatProperty(
        name="Secondary Intensity", default=1.0, min=0.0, max=2.0,
        description="Coherent adaptive intensity for secondary motion (0% - 200%)",
    )

    jiggle_stiffness_min: bpy.props.FloatProperty(name="Spring Stiffness Min", default=1.2, min=0.1, max=10.0, description="Minimum spring elasticity stiffness")
    jiggle_stiffness_max: bpy.props.FloatProperty(name="Spring Stiffness Max", default=2.5, min=0.1, max=10.0, description="Maximum spring elasticity stiffness")
    jiggle_damping_min: bpy.props.FloatProperty(name="Damping Ratio Min", default=0.25, min=0.01, max=1.0, description="Minimum spring damping ratio")
    jiggle_damping_max: bpy.props.FloatProperty(name="Damping Ratio Max", default=0.5, min=0.01, max=1.0, description="Maximum spring damping ratio")

    delay_frames_min: bpy.props.FloatProperty(name="Offset Frames Min", default=1.0, min=-100.0, max=100.0, description="Minimum frame delay per chain depth")
    delay_frames_max: bpy.props.FloatProperty(name="Offset Frames Max", default=3.0, min=-100.0, max=100.0, description="Maximum frame delay per chain depth")

    anti_factor_min: bpy.props.FloatProperty(name="Anticipation Ratio Min", default=0.05, min=0.0, max=1.0, description="Minimum anticipation keyframe ratio")
    anti_factor_max: bpy.props.FloatProperty(name="Anticipation Ratio Max", default=0.15, min=0.0, max=1.0, description="Maximum anticipation keyframe ratio")
    over_factor_min: bpy.props.FloatProperty(name="Overshoot Ratio Min", default=0.05, min=0.0, max=1.0, description="Minimum overshoot keyframe ratio")
    over_factor_max: bpy.props.FloatProperty(name="Overshoot Ratio Max", default=0.15, min=0.0, max=1.0, description="Maximum overshoot keyframe ratio")

    drag_factor_min: bpy.props.FloatProperty(name="Lag Factor Min", default=0.01, min=0.0, max=2.0, description="Minimum rotational drag intensity")
    drag_factor_max: bpy.props.FloatProperty(name="Lag Factor Max", default=0.05, min=0.0, max=2.0, description="Maximum rotational drag intensity")

    tremor_amp_min: bpy.props.FloatProperty(name="Jitter Amplitude Min", default=0.0005, min=0.0001, max=0.1, description="Minimum idle micro-jitter noise")
    tremor_amp_max: bpy.props.FloatProperty(name="Jitter Amplitude Max", default=0.003, min=0.0001, max=0.1, description="Maximum idle micro-jitter noise")

    noise_scale_min: bpy.props.FloatProperty(name="Noise Scale Min", default=0.1, min=0.01, max=2.0, description="Minimum noise frequency scale")
    noise_scale_max: bpy.props.FloatProperty(name="Noise Scale Max", default=0.5, min=0.01, max=2.0, description="Maximum noise frequency scale")
    noise_strength_min: bpy.props.FloatProperty(name="Noise Strength Min", default=0.005, min=0.0, max=1.0, description="Minimum subtle noise amplitude")
    noise_strength_max: bpy.props.FloatProperty(name="Noise Strength Max", default=0.02, min=0.0, max=1.0, description="Maximum subtle noise amplitude")

    wave_frequency_min: bpy.props.FloatProperty(name="Wave Frequency Min", default=0.1, min=0.01, max=2.0, description="Minimum wave frequency")
    wave_frequency_max: bpy.props.FloatProperty(name="Wave Frequency Max", default=0.5, min=0.01, max=2.0, description="Maximum wave frequency")
    wave_amplitude_min: bpy.props.FloatProperty(name="Wave Amplitude Min", default=0.01, min=0.0, max=1.0, description="Minimum subtle wave amplitude")
    wave_amplitude_max: bpy.props.FloatProperty(name="Wave Amplitude Max", default=0.05, min=0.0, max=1.0, description="Maximum subtle wave amplitude")

    propagation_wave_speed: bpy.props.FloatProperty(
        name="Wave Speed (frames/unit)", default=1.0, min=0.01, max=100.0,
        description="Delay per unit of distance from the origin target",
    )
    propagation_max_delay: bpy.props.FloatProperty(
        name="Max Wave Delay", default=6.0, min=0.0, max=100.0,
        description="Maximum delay applied by the propagation wave",
    )

    deoverlap_min_dist: bpy.props.FloatProperty(name="Clearance Floor", default=0.10, min=0.01, max=10.0, description="Minimum clearance between clearance volumes")
    deoverlap_margin: bpy.props.FloatProperty(name="Safety Margin", default=0.20, min=0.0, max=5.0, description="Additional safety separation margin")
    deoverlap_max_dist: bpy.props.FloatProperty(name="Max Target Distance", default=0.0, min=0.0, max=20.0, description="Maximum distance the solver targets between two targets. Zero means no limit")
    deoverlap_iterations: bpy.props.IntProperty(name="Correction Passes", default=20, min=1, max=100, description="Maximum bounded correction passes")
    clearance_edit_radius: bpy.props.FloatProperty(
        name="Clearance Radius", default=0.5, min=0.0, max=50.0,
        description="Editable clearance radius for the contextual viewport gizmo",
    )
    deoverlap_return_to_path: bpy.props.BoolProperty(
        name="Return To Original Trajectory", default=True,
        description="Drive corrected targets back to their original trajectory after clearing",
    )
    deoverlap_orbit: bpy.props.BoolProperty(
        name="Orbit Behavior", default=True,
        description="Allow tangential orbit motion while resolving clearance",
    )

    custom_easing_type: bpy.props.EnumProperty(
        name="Easing Function",
        description="Mathematical curve type",
        items=[
            ("BEZIER", "Bezier (Cubic)", "Smoothstep cubic Bezier curve"),
            ("SINE", "Sine", "Sinusoidal transition"),
            ("QUAD", "Quad", "Quadratic transition"),
            ("CUBIC", "Cubic", "Cubic transition"),
            ("QUART", "Quart", "Quartic transition"),
            ("QUINT", "Quint", "Quintic transition"),
            ("EXPO", "Expo", "Exponential transition"),
            ("CIRC", "Circ", "Circular transition"),
            ("BACK", "Back", "Overshooting back curve"),
            ("BOUNCE", "Bounce", "Elastic bounce transition"),
            ("ELASTIC", "Elastic", "Damped spring elastic curve"),
        ],
        default="BEZIER",
    )
    custom_easing_ease: bpy.props.EnumProperty(
        name="Easing Phase",
        description="Easing curve direction phase",
        items=[
            ("EASE_IN_OUT", "Ease In-Out", "Accelerate from start and decelerate to end"),
            ("EASE_IN", "Ease In", "Accelerate from start"),
            ("EASE_OUT", "Ease Out", "Decelerate to end"),
        ],
        default="EASE_IN_OUT",
    )
    ease_multiplier: bpy.props.FloatProperty(
        name="Ease In/Out Multiplier", default=1.0, min=0.1, max=10.0,
        description="Multiplier/divider scaling the easing curve weight",
    )
    time_scale_min: bpy.props.FloatProperty(name="Time Scale Min", default=1.5, min=0.1, max=10.0, description="Minimum timing expansion/compression factor")
    time_scale_max: bpy.props.FloatProperty(name="Time Scale Max", default=2.5, min=0.1, max=10.0, description="Maximum timing expansion/compression factor")

    cleanup_error_tolerance: bpy.props.FloatProperty(
        name="Allowed Error Margin", default=0.05, min=0.0001, max=10.0,
        description="Maximum allowed deviation from the original curve during decimation",
    )
    cleanup_rdp_epsilon: bpy.props.FloatProperty(
        name="RDP Tolerance (Epsilon)", default=1.0, min=0.0001, max=100.0,
        description="Ramer-Douglas-Peucker curve simplification tolerance",
    )

    autobake_tolerance: bpy.props.FloatProperty(
        name="Bake Tolerance", default=0.05, min=0.0001, max=10.0,
        description="Adaptive reconstruction tolerance for autobake",
    )
    autobake_adaptive: bpy.props.BoolProperty(
        name="Adaptive Tolerance", default=True,
        description="Scale tolerance with local motion amplitude",
    )
    autobake_simplify: bpy.props.BoolProperty(
        name="Simplify Result", default=True,
        description="Run curve decimation after baking",
    )
    autobake_keep_original: bpy.props.BoolProperty(
        name="Keep Original Keys Visible", default=False,
        description="Keep unreconstructed keyframes outside the bake tolerance",
    )

    loop_mode: bpy.props.EnumProperty(
        name="Loop Mode",
        description="Sequence synthesis strategy",
        items=[
            ("CYCLE", "Cycle", "Repeat the animation across the loop range"),
            ("PING_PONG", "Ping-Pong", "Mirror the animation back and forth"),
        ],
        default="CYCLE",
    )

    random_scope: bpy.props.EnumProperty(
        name="Randomization",
        description="Chooses whether timing, values or both are randomised",
        items=[
            ("TIME", "Time", "Randomises the timing of the existing keyframes"),
            ("VALUES", "Values", "Randomises the values of the existing keyframes"),
            ("BOTH", "Both", "Randomises timing and values"),
        ],
        default="TIME",
    )

    secondary_effect: bpy.props.EnumProperty(
        name="Effect",
        description="Secondary motion response generated from the existing animation",
        items=[
            ("NONE", "None", "Disables the secondary motion generator"),
            ("SQUASH_STRETCH", "Squash & Stretch", "Stretches and compresses the target following its motion"),
            ("DYNAMIC_FOLLOW", "Dynamic Follow", "Adds an inertial follow offset derived from the motion"),
            ("INERTIAL_JIGGLE", "Inertial Jiggle", "Adds a damped oscillation derived from the motion"),
            ("MICRO_TREMOR", "Micro Tremor", "Adds a low amplitude oscillation derived from the motion"),
            ("BREATHING", "Breathing", "Adds a subtle volume preserving breathing cycle"),
        ],
        default="SQUASH_STRETCH",
    )

    clearance_edit_mode: bpy.props.BoolProperty(
        name="Edit Clearance",
        description="Shows the contextual clearance gizmo in the 3D viewport",
        default=False,
    )

    motion_report: bpy.props.StringProperty(
        name="Motion Report",
        description="Result of the last motion analysis of the selected targets",
        default="",
    )