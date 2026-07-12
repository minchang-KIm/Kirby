"""Contrast-enforced pygame UI primitives with redundant status patterns."""

from __future__ import annotations

from typing import Final

import pygame

type Color = tuple[int, int, int] | tuple[int, int, int, int]
type Point = tuple[int, int]

_PATTERNS: Final = frozenset({"hatch", "dots", "stripes"})


def _color(name: str, value: object) -> tuple[int, int, int, int]:
    if type(value) is not tuple or len(value) not in {3, 4}:
        raise ValueError(f"{name} must contain three or four channels")
    channels: list[int] = []
    for channel in value:
        if type(channel) is not int:
            raise TypeError(f"{name} channel must be an integer")
        if not 0 <= channel <= 255:
            raise ValueError(f"{name} channel must be in [0, 255]")
        channels.append(channel)
    if len(channels) == 3:
        channels.append(255)
    return channels[0], channels[1], channels[2], channels[3]


def _composite(foreground: tuple[int, int, int, int], background: tuple[int, int, int]) -> tuple[float, float, float]:
    alpha = foreground[3] / 255.0
    return tuple(foreground[index] * alpha + background[index] * (1.0 - alpha) for index in range(3))  # type: ignore[return-value]


def _opaque_rgb(color: tuple[int, int, int, int]) -> tuple[float, float, float]:
    return _composite(color, (0, 0, 0))


def _linear_channel(channel: float) -> float:
    value = channel / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: Color) -> float:
    """Return WCAG relative luminance after compositing alpha over black."""

    red, green, blue = _opaque_rgb(_color("color", color))
    return 0.2126 * _linear_channel(red) + 0.7152 * _linear_channel(green) + 0.0722 * _linear_channel(blue)


def contrast_ratio(foreground: Color, background: Color) -> float:
    """Return WCAG contrast after compositing both colors as actually painted."""

    background_rgba = _color("background", background)
    effective_background = _opaque_rgb(background_rgba)
    foreground_rgba = _color("foreground", foreground)
    effective_foreground = _composite(
        foreground_rgba,
        tuple(round(channel) for channel in effective_background),  # type: ignore[arg-type]
    )
    foreground_luminance = (
        0.2126 * _linear_channel(effective_foreground[0])
        + 0.7152 * _linear_channel(effective_foreground[1])
        + 0.0722 * _linear_channel(effective_foreground[2])
    )
    background_luminance = (
        0.2126 * _linear_channel(effective_background[0])
        + 0.7152 * _linear_channel(effective_background[1])
        + 0.0722 * _linear_channel(effective_background[2])
    )
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def minimum_text_contrast(size_px: int) -> float:
    """Return the exact body/large threshold used by the product UI."""

    if type(size_px) is not int:
        raise TypeError("text size must be an integer")
    if size_px <= 0:
        raise ValueError("text size must be positive")
    return 3.0 if size_px >= 24 else 4.5


def _surface(value: object) -> pygame.Surface:
    if not isinstance(value, pygame.Surface):
        raise TypeError("target must be a pygame.Surface")
    return value


def _position(value: object) -> Point:
    if type(value) is not tuple or len(value) != 2:
        raise ValueError("text position must be a two-item tuple")
    if any(type(item) is not int for item in value):
        raise TypeError("text position values must be integers")
    return value


def draw_text(
    target: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    position: Point,
    *,
    foreground: Color,
    background: Color,
    size_px: int,
) -> pygame.Rect:
    """Draw validated readable text or reject a contrast failure."""

    surface = _surface(target)
    if not isinstance(font, pygame.font.Font):
        raise TypeError("font must be a pygame Font")
    if type(text) is not str:
        raise TypeError("text must be a string")
    if not text:
        raise ValueError("text must be non-empty")
    point = _position(position)
    required = minimum_text_contrast(size_px)
    ratio = contrast_ratio(foreground, background)
    if ratio < required:
        raise ValueError(f"text contrast {ratio:.3f} is below required {required:.1f}")
    foreground_rgba = _color("foreground", foreground)
    rendered = font.render(text, True, foreground_rgba[:3])
    return surface.blit(rendered, point)


def _pattern_overlay(size: tuple[int, int], pattern_token: str, color: Color) -> pygame.Surface:
    overlay = pygame.Surface(size, pygame.SRCALPHA)
    rgba = _color("pattern color", color)
    pattern_color = (*rgba[:3], min(58, rgba[3]))
    width, height = size
    if pattern_token == "hatch":
        for x in range(-height, width, 12):
            pygame.draw.line(overlay, pattern_color, (x, height), (x + height, 0), 2)
    elif pattern_token == "dots":
        for y in range(7, height, 14):
            for x in range(7, width, 14):
                pygame.draw.circle(overlay, pattern_color, (x, y), 2)
    else:
        for y in range(5, height, 10):
            pygame.draw.line(overlay, pattern_color, (0, y), (width, y), 2)
    return overlay


def draw_panel(
    target: pygame.Surface,
    rect: pygame.Rect,
    *,
    fill: Color,
    outline: Color,
    pattern_token: str,
    icon: pygame.Surface,
    label: str,
    font: pygame.font.Font,
    foreground: Color,
    font_size_px: int,
    label_anchor: str = "center",
) -> pygame.Rect:
    """Draw a panel whose state always has color, outline, icon, text, and pattern."""

    surface = _surface(target)
    if not isinstance(rect, pygame.Rect):
        raise TypeError("panel rect must be a pygame.Rect")
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("panel rect dimensions must be positive")
    if type(pattern_token) is not str or pattern_token not in _PATTERNS:
        raise ValueError("panel pattern must be hatch, dots, or stripes")
    if type(label_anchor) is not str or label_anchor not in {"center", "top"}:
        raise ValueError("panel label anchor must be center or top")
    icon_surface = _surface(icon)
    fill_rgba = _color("panel fill", fill)
    outline_rgba = _color("panel outline", outline)
    pygame.draw.rect(surface, fill_rgba, rect, border_radius=8)
    overlay = _pattern_overlay(rect.size, pattern_token, outline_rgba)
    surface.blit(overlay, rect.topleft)
    pygame.draw.rect(surface, outline_rgba, rect, width=2, border_radius=8)
    icon_limit = max(1, min(32, rect.height - 12))
    scaled_icon = pygame.transform.smoothscale(icon_surface, (icon_limit, icon_limit))
    icon_position = (rect.left + 8, rect.centery - icon_limit // 2)
    surface.blit(scaled_icon, icon_position)
    text_x = icon_position[0] + icon_limit + 8
    text_y = rect.top + 8 if label_anchor == "top" else rect.centery - font.get_height() // 2
    rendered_rect = draw_text(
        surface,
        font,
        label,
        (text_x, text_y),
        foreground=foreground,
        background=fill,
        size_px=font_size_px,
    )
    return rect.union(rendered_rect)


__all__ = [
    "Color",
    "contrast_ratio",
    "draw_panel",
    "draw_text",
    "minimum_text_contrast",
    "relative_luminance",
]
