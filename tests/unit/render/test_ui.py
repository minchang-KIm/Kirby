"""WCAG-aware render primitive contracts."""

from __future__ import annotations

import pygame
import pytest

from windsprig.render.ui import (
    contrast_ratio,
    draw_panel,
    draw_text,
    minimum_text_contrast,
    relative_luminance,
)


def test_wcag_luminance_and_contrast_use_exact_linearized_srgb() -> None:
    assert relative_luminance((0, 0, 0)) == 0.0
    assert relative_luminance((255, 255, 255)) == 1.0
    assert contrast_ratio((255, 255, 255), (0, 0, 0)) == 21.0
    assert minimum_text_contrast(23) == 4.5
    assert minimum_text_contrast(24) == 3.0


def test_contrast_matches_rgba_colors_as_drawn_on_the_opaque_logical_canvas() -> None:
    # pygame's primitive draw writes RGB channels directly on the release canvas;
    # an alpha byte must not turn an effectively white panel into a black one.
    assert contrast_ratio((255, 255, 255), (255, 255, 255, 1)) == 1.0
    assert contrast_ratio((255, 255, 255, 0), (0, 0, 0)) == 21.0


def test_draw_text_rejects_false_contrast_from_nearly_transparent_white_fill() -> None:
    pygame.font.init()
    canvas = pygame.Surface((180, 60))

    with pytest.raises(ValueError, match="contrast"):
        draw_text(
            canvas,
            pygame.font.Font(None, 24),
            "Unreadable",
            (4, 4),
            foreground=(255, 255, 255),
            background=(255, 255, 255, 1),
            size_px=20,
        )


def test_draw_text_enforces_exact_body_and_large_text_thresholds() -> None:
    pygame.font.init()
    canvas = pygame.Surface((300, 100), pygame.SRCALPHA)
    font = pygame.font.Font(None, 28)

    with pytest.raises(ValueError, match="4.5"):
        draw_text(
            canvas,
            font,
            "Body",
            (4, 4),
            foreground=(119, 119, 119),
            background=(255, 255, 255),
            size_px=23,
        )
    rect = draw_text(
        canvas,
        font,
        "Large",
        (4, 36),
        foreground=(119, 119, 119),
        background=(255, 255, 255),
        size_px=24,
    )

    assert rect.width > 0 and rect.height > 0


@pytest.mark.parametrize("pattern", ["hatch", "dots", "stripes"])
def test_panel_combines_fill_outline_icon_text_and_pattern(pattern: str) -> None:
    pygame.font.init()
    canvas = pygame.Surface((240, 100), pygame.SRCALPHA)
    icon = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.circle(icon, (248, 194, 67), (12, 12), 10)

    draw_panel(
        canvas,
        pygame.Rect(4, 4, 220, 80),
        fill=(22, 32, 43),
        outline=(245, 247, 226),
        pattern_token=pattern,
        icon=icon,
        label="Readable",
        font=pygame.font.Font(None, 24),
        foreground=(245, 247, 226),
        font_size_px=20,
    )

    # Core pygame pixel access keeps the browser-compatible suite independent of NumPy.
    colors = {tuple(canvas.get_at((x, y))[:3]) for y in range(canvas.get_height()) for x in range(canvas.get_width())}
    assert (22, 32, 43) in colors
    assert (245, 247, 226) in colors
    assert (248, 194, 67) in colors
    assert len(colors) >= 4


def test_panel_top_anchor_reserves_lower_rows_for_complex_hud_content() -> None:
    pygame.font.init()
    canvas = pygame.Surface((240, 100), pygame.SRCALPHA)
    icon = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.circle(icon, (248, 194, 67), (12, 12), 10)

    draw_panel(
        canvas,
        pygame.Rect(4, 4, 220, 90),
        fill=(22, 32, 43),
        outline=(245, 247, 226),
        pattern_token="hatch",
        icon=icon,
        label="Top header",
        font=pygame.font.Font(None, 24),
        foreground=(245, 247, 226),
        font_size_px=20,
        label_anchor="top",
    )

    assert any(tuple(canvas.get_at((x, y))[:3]) == (245, 247, 226) for y in range(10, 34) for x in range(52, 180))


def test_panel_paints_rgba_fill_as_the_effective_opaque_canvas_color() -> None:
    pygame.font.init()
    canvas = pygame.Surface((240, 100), pygame.SRCALPHA)
    icon = pygame.Surface((24, 24), pygame.SRCALPHA)

    draw_panel(
        canvas,
        pygame.Rect(4, 4, 220, 80),
        fill=(255, 255, 255, 1),
        outline=(0, 0, 0),
        pattern_token="dots",
        icon=icon,
        label="Opaque",
        font=pygame.font.Font(None, 24),
        foreground=(0, 0, 0),
        font_size_px=20,
    )

    assert tuple(canvas.get_at((200, 70))) == (255, 255, 255, 255)


def test_ui_primitives_reject_invalid_colors_sizes_and_pattern_tokens() -> None:
    pygame.font.init()
    canvas = pygame.Surface((100, 60), pygame.SRCALPHA)
    font = pygame.font.Font(None, 20)
    icon = pygame.Surface((12, 12), pygame.SRCALPHA)

    with pytest.raises(TypeError, match="channel"):
        contrast_ratio((True, 0, 0), (0, 0, 0))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="size"):
        minimum_text_contrast(0)
    with pytest.raises(ValueError, match="pattern"):
        draw_panel(
            canvas,
            pygame.Rect(1, 1, 90, 50),
            fill=(22, 32, 43),
            outline=(245, 247, 226),
            pattern_token="color-only",
            icon=icon,
            label="Panel",
            font=font,
            foreground=(245, 247, 226),
            font_size_px=18,
        )
