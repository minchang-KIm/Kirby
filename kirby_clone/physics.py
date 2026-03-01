from __future__ import annotations

from dataclasses import dataclass
import math

from .math2d import Rect, Vec2


@dataclass
class PhysicsBody:
    rect: Rect
    velocity: Vec2
    on_ground: bool = False


@dataclass(frozen=True)
class CollisionResult:
    hit_left: bool = False
    hit_right: bool = False
    hit_ceiling: bool = False
    hit_ground: bool = False
    hit_hazard: bool = False


class TileCollisionWorld:
    def __init__(
        self,
        tile_size: int,
        width_tiles: int,
        height_tiles: int,
        solid_tiles: set[tuple[int, int]],
        one_way_tiles: set[tuple[int, int]] | None = None,
        hazard_tiles: set[tuple[int, int]] | None = None,
    ) -> None:
        self.tile_size = tile_size
        self.width_tiles = width_tiles
        self.height_tiles = height_tiles
        self.solid_tiles = solid_tiles
        self.one_way_tiles = one_way_tiles or set()
        self.hazard_tiles = hazard_tiles or set()

    @property
    def pixel_width(self) -> int:
        return self.width_tiles * self.tile_size

    @property
    def pixel_height(self) -> int:
        return self.height_tiles * self.tile_size

    def _tile_rect(self, tx: int, ty: int) -> Rect:
        return Rect(tx * self.tile_size, ty * self.tile_size, self.tile_size, self.tile_size)

    def tile_range_for_rect(self, rect: Rect) -> tuple[range, range]:
        min_x = max(0, int(math.floor(rect.left / self.tile_size)))
        max_x = min(self.width_tiles - 1, int(math.floor((rect.right - 0.001) / self.tile_size)))
        min_y = max(0, int(math.floor(rect.top / self.tile_size)))
        max_y = min(self.height_tiles - 1, int(math.floor((rect.bottom - 0.001) / self.tile_size)))
        return range(min_x, max_x + 1), range(min_y, max_y + 1)

    def touches_hazard(self, rect: Rect) -> bool:
        xs, ys = self.tile_range_for_rect(rect)
        for tx in xs:
            for ty in ys:
                if (tx, ty) in self.hazard_tiles and self._tile_rect(tx, ty).intersects(rect):
                    return True
        return False

    def touches_solid(self, rect: Rect) -> bool:
        xs, ys = self.tile_range_for_rect(rect)
        for tx in xs:
            for ty in ys:
                if (tx, ty) in self.solid_tiles and self._tile_rect(tx, ty).intersects(rect):
                    return True
        return False

    def touching_tile_coords(self, rect: Rect, tiles: set[tuple[int, int]]) -> list[tuple[int, int]]:
        hits: list[tuple[int, int]] = []
        xs, ys = self.tile_range_for_rect(rect)
        for tx in xs:
            for ty in ys:
                if (tx, ty) in tiles and self._tile_rect(tx, ty).intersects(rect):
                    hits.append((tx, ty))
        return hits

    def clamp_to_world(self, rect: Rect) -> Rect:
        x = min(max(rect.x, 0.0), max(0.0, self.pixel_width - rect.w))
        y = min(max(rect.y, 0.0), max(0.0, self.pixel_height - rect.h))
        return Rect(x, y, rect.w, rect.h)


def move_body(body: PhysicsBody, world: TileCollisionWorld, dt_s: float) -> CollisionResult:
    hit_left = False
    hit_right = False
    hit_ceiling = False
    hit_ground = False

    # Horizontal sweep first.
    body.rect = body.rect.moved(body.velocity.x * dt_s, 0.0)
    if body.velocity.x != 0:
        body.rect, hit_left, hit_right = _resolve_horizontal(body.rect, body.velocity.x, world)
        if hit_left or hit_right:
            body.velocity.x = 0.0

    # Vertical sweep second.
    previous_bottom = body.rect.bottom
    body.rect = body.rect.moved(0.0, body.velocity.y * dt_s)
    if body.velocity.y != 0:
        body.rect, hit_ceiling, hit_ground = _resolve_vertical(
            body.rect,
            body.velocity.y,
            previous_bottom,
            world,
        )
        if hit_ceiling or hit_ground:
            body.velocity.y = 0.0

    body.rect = world.clamp_to_world(body.rect)
    body.on_ground = hit_ground
    return CollisionResult(
        hit_left=hit_left,
        hit_right=hit_right,
        hit_ceiling=hit_ceiling,
        hit_ground=hit_ground,
        hit_hazard=world.touches_hazard(body.rect),
    )


def _resolve_horizontal(rect: Rect, vx: float, world: TileCollisionWorld) -> tuple[Rect, bool, bool]:
    hit_left = False
    hit_right = False
    xs, ys = world.tile_range_for_rect(rect)
    for tx in xs:
        for ty in ys:
            if (tx, ty) not in world.solid_tiles:
                continue
            tile = world._tile_rect(tx, ty)
            if not rect.intersects(tile):
                continue
            if vx > 0:
                rect = Rect(tile.left - rect.w, rect.y, rect.w, rect.h)
                hit_right = True
            else:
                rect = Rect(tile.right, rect.y, rect.w, rect.h)
                hit_left = True
    return rect, hit_left, hit_right


def _resolve_vertical(
    rect: Rect,
    vy: float,
    previous_bottom: float,
    world: TileCollisionWorld,
) -> tuple[Rect, bool, bool]:
    hit_ceiling = False
    hit_ground = False
    xs, ys = world.tile_range_for_rect(rect)

    for tx in xs:
        for ty in ys:
            tile = world._tile_rect(tx, ty)
            is_solid = (tx, ty) in world.solid_tiles
            is_one_way = (tx, ty) in world.one_way_tiles

            if not (is_solid or is_one_way):
                continue
            if not rect.intersects(tile):
                continue

            if is_one_way:
                if vy < 0:
                    continue
                if previous_bottom > tile.top + 1:
                    continue
                rect = Rect(rect.x, tile.top - rect.h, rect.w, rect.h)
                hit_ground = True
                continue

            if vy > 0:
                rect = Rect(rect.x, tile.top - rect.h, rect.w, rect.h)
                hit_ground = True
            else:
                rect = Rect(rect.x, tile.bottom, rect.w, rect.h)
                hit_ceiling = True
    return rect, hit_ceiling, hit_ground
