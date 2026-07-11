from __future__ import annotations

from dataclasses import dataclass, field
import itertools

from .combat import HitEvent, Hitbox, Hurtbox
from .math2d import Rect, Vec2, move_towards
from .physics import PhysicsBody, move_body


_id_iter = itertools.count(100)


@dataclass
class Enemy:
    kind: str
    spawn: tuple[float, float]
    patrol_left: float
    patrol_right: float
    entity_id: int | None = None
    team: str = "enemy"
    dead: bool = field(default=False, init=False)
    state: str = field(default="patrol", init=False)
    facing: int = field(default=-1, init=False)
    body: PhysicsBody = field(init=False)
    hp: int = field(init=False)
    max_hp: int = field(init=False)
    move_speed: float = field(init=False)
    contact_damage: int = field(init=False)
    _hurt_ms: int = field(default=0, init=False)
    _invulnerable_ms: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.entity_id is None:
            self.entity_id = next(_id_iter)
        if self.kind == "brute":
            w, h = 30, 30
            self.max_hp = 4
            self.move_speed = 110.0
            self.contact_damage = 2
        else:
            w, h = 26, 26
            self.max_hp = 2
            self.move_speed = 150.0
            self.contact_damage = 1
        self.hp = self.max_hp
        self.body = PhysicsBody(rect=Rect(self.spawn[0], self.spawn[1], w, h), velocity=Vec2(0.0, 0.0))

    def update(self, dt_ms: int, world: "WorldStateLike") -> None:
        if self.dead:
            return

        dt_s = dt_ms / 1000.0
        self._hurt_ms = max(0, self._hurt_ms - dt_ms)
        self._invulnerable_ms = max(0, self._invulnerable_ms - dt_ms)

        player = world.entity_index.get(world.player_id)
        target_speed = 0.0
        if player and not player.dead and self._hurt_ms == 0:
            dx = player.get_aabb().center_x - self.body.rect.center_x
            dy = abs(player.get_aabb().center_y - self.body.rect.center_y)
            if abs(dx) < 220 and dy < 90:
                self.state = "chase"
                self.facing = 1 if dx >= 0 else -1
                target_speed = self.move_speed * self.facing
            else:
                self.state = "patrol"
                target_speed = self._patrol_speed()
        elif self._hurt_ms > 0:
            self.state = "stunned"
            target_speed = 0.0
        else:
            self.state = "patrol"
            target_speed = self._patrol_speed()

        accel = 1800.0 if self.body.on_ground else 1200.0
        self.body.velocity.x = move_towards(self.body.velocity.x, target_speed, accel * dt_s)
        self.body.velocity.y = min(self.body.velocity.y + 2300.0 * dt_s, 1450.0)

        collision = move_body(self.body, world.collision_map, dt_s)
        if collision.hit_left:
            self.facing = 1
        if collision.hit_right:
            self.facing = -1
        if collision.hit_hazard:
            self.dead = True
            self.state = "dead"

        if self.hp <= 0 and not self.dead:
            self.dead = True
            self.state = "dead"

    def _patrol_speed(self) -> float:
        if self.body.rect.left <= self.patrol_left:
            self.facing = 1
        elif self.body.rect.right >= self.patrol_right:
            self.facing = -1
        return self.move_speed * self.facing * 0.75

    def get_aabb(self) -> Rect:
        return self.body.rect

    def get_hurtbox(self) -> Hurtbox:
        return Hurtbox(
            owner_id=self.entity_id,
            owner_team=self.team,
            rect=Rect(self.body.rect.x + 2, self.body.rect.y + 2, self.body.rect.w - 4, self.body.rect.h - 2),
        )

    def get_hitboxes(self, frame_index: int) -> list[Hitbox]:
        if self.dead:
            return []
        rect = Rect(self.body.rect.x + 2, self.body.rect.y + 3, self.body.rect.w - 4, self.body.rect.h - 6)
        knockback = Vec2(180.0 * self.facing, -80.0)
        return [
            Hitbox(
                owner_id=self.entity_id,
                owner_team=self.team,
                rect=rect,
                damage=self.contact_damage,
                knockback=knockback,
                start_frame=frame_index,
                end_frame=frame_index,
            )
        ]

    def on_hit(self, hit: HitEvent) -> None:
        if self._invulnerable_ms > 0 or self.dead:
            return
        self.hp -= hit.damage
        self._hurt_ms = 260
        self._invulnerable_ms = 300
        self.body.velocity.x += hit.knockback.x * 0.4
        self.body.velocity.y = min(self.body.velocity.y + hit.knockback.y * 0.5, -120.0)
        self.facing = -1 if hit.knockback.x > 0 else 1
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            self.state = "dead"


class WorldStateLike:
    player_id: int
    entity_index: dict[int, object]
    collision_map: object
