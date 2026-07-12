"""Presentation-only rendering services over immutable gameplay views."""

from .animation import AnimationBank, AnimationClip, AnimationCursor, build_default_animation_bank
from .assets import AssetCatalog, MissingAssetError
from .camera import CameraController, CameraView, Letterbox, compute_letterbox
from .effects import EffectFrame, EffectsDirector, Flash, Particle, Shake, empty_effect_frame
from .hud import HudBossVM, HudPlayerVM, HudViewModel, build_hud_view
from .renderer import StageRenderer
from .ui import contrast_ratio, draw_panel, draw_text, minimum_text_contrast, relative_luminance

__all__ = [
    "AnimationBank",
    "AnimationClip",
    "AnimationCursor",
    "AssetCatalog",
    "CameraController",
    "CameraView",
    "EffectFrame",
    "EffectsDirector",
    "Flash",
    "HudBossVM",
    "HudPlayerVM",
    "HudViewModel",
    "Letterbox",
    "MissingAssetError",
    "Particle",
    "Shake",
    "StageRenderer",
    "build_default_animation_bank",
    "build_hud_view",
    "compute_letterbox",
    "contrast_ratio",
    "draw_panel",
    "draw_text",
    "empty_effect_frame",
    "minimum_text_contrast",
    "relative_luminance",
]
