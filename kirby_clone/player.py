from __future__ import annotations

from dataclasses import dataclass, field

from .combat import HitEvent, Hitbox, Hurtbox
from .input import InputState
from .math2d import Rect, Vec2, move_towards
from .physics import PhysicsBody, TileCollisionWorld, move_body
from .settings import GameConfig


@dataclass
class Player:
    config: GameConfig
    spawn: tuple[float, float]
    entity_id: int = 1
    team: str = "player"
    max_hp: int = field(init=False)
    hp: int = field(init=False)
    dead: bool = field(default=False, init=False)
    state: str = field(default="idle", init=False)
    facing: int = field(default=1, init=False)
    body: PhysicsBody = field(init=False)
    _input_state: InputState = field(default_factory=InputState.neutral, init=False)
    _coyote_ms: int = field(default=0, init=False)
    _jump_buffer_ms: int = field(default=0, init=False)
    _attack_ms: int = field(default=0, init=False)
    _hurt_ms: int = field(default=0, init=False)
    _invulnerable_ms: int = field(default=0, init=False)

    ATTACK_STARTUP_MS = 80
    ATTACK_ACTIVE_MS = 120
    ATTACK_RECOVERY_MS = 140
    ATTACK_TOTAL_MS = ATTACK_STARTUP_MS + ATTACK_ACTIVE_MS + ATTACK_RECOVERY_MS

    def __post_init__(self) -> None:
        self.max_hp = self.config.player_max_hp
        self.hp = self.max_hp
        self.body = PhysicsBody(rect=Rect(self.spawn[0], self.spawn[1], 28, 28), velocity=Vec2(0.0, 0.0))

    def set_input(self, input_state: InputState) -> None:
        self._input_state = input_state

    def update(self, dt_ms: int, world: "WorldStateLike") -> None:
        if self.dead:
            return

        dt_s = dt_ms / 1000.0
        self._tick_timers(dt_ms)
        inp = self._input_state

        target_speed = inp.move_x * self.config.move_speed
        accel = 2400.0 if self.body.on_ground else 1700.0
        decel = 3000.0
        if inp.move_x != 0:
            self.body.velocity.x = move_towards(self.body.velocity.x, target_speed, accel * dt_s)
            self.facing = 1 if inp.move_x > 0 else -1
        else:
            self.body.velocity.x = move_towards(self.body.velocity.x, 0.0, decel * dt_s)

        if self.body.on_ground:
            self._coyote_ms = self.config.coyote_time_ms
        else:
            self._coyote_ms = max(0, self._coyote_ms - dt_ms)

        if inp.jump_pressed:
            self._jump_buffer_ms = self.config.jump_buffer_ms
        else:
            self._jump_buffer_ms = max(0, self._jump_buffer_ms - dt_ms)

        if self._can_jump():
            self.body.velocity.y = -self.config.jump_velocity
            self.body.on_ground = False
            self._coyote_ms = 0
            self._jump_buffer_ms = 0

        if inp.attack_pressed and self._attack_ms <= 0 and self._hurt_ms <= 0:
            self._attack_ms = self.ATTACK_TOTAL_MS

        gravity_scale = 1.0
        if self.body.velocity.y < 0 and not inp.jump_held:
            gravity_scale = 1.65
        self.body.velocity.y = min(
            self.body.velocity.y + self.config.gravity * gravity_scale * dt_s,
            1450.0,
        )

        collision = move_body(self.body, world.collision_map, dt_s)
        if collision.hit_hazard:
            self._apply_damage(1, Vec2(0.0, -230.0))

        self._update_state()

    def _can_jump(self) -> bool:
        return (self.body.on_ground or self._coyote_ms > 0) and self._jump_buffer_ms > 0 and self._hurt_ms <= 0

    def _tick_timers(self, dt_ms: int) -> None:
        self._attack_ms = max(0, self._attack_ms - dt_ms)
        self._hurt_ms = max(0, self._hurt_ms - dt_ms)
        self._invulnerable_ms = max(0, self._invulnerable_ms - dt_ms)

    def _update_state(self) -> None:
        if self.dead:
            self.state = "dead"
        elif self._hurt_ms > 0:
            self.state = "hurt"
        elif self._attack_ms > 0:
            self.state = "attack"
        elif not self.body.on_ground and self.body.velocity.y < -20.0:
            self.state = "jump"
        elif not self.body.on_ground and self.body.velocity.y >= -20.0:
            self.state = "fall"
        elif abs(self.body.velocity.x) > 20.0:
            self.state = "run"
        else:
            self.state = "idle"

    def _apply_damage(self, damage: int, knockback: Vec2) -> None:
        if self._invulnerable_ms > 0 or self.dead:
            return
        self.hp -= damage
        self._hurt_ms = 220
        self._invulnerable_ms = self.config.invulnerable_ms
        self.body.velocity.x += knockback.x
        self.body.velocity.y = min(self.body.velocity.y + knockback.y, -120.0)
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            self.state = "dead"

    def on_hit(self, hit: HitEvent) -> None:
        self._apply_damage(hit.damage, hit.knockback)

    def get_aabb(self) -> Rect:
        return self.body.rect

    def get_hurtbox(self) -> Hurtbox:
        return Hurtbox(
            owner_id=self.entity_id,
            owner_team=self.team,
            rect=Rect(self.body.rect.x + 3, self.body.rect.y + 2, self.body.rect.w - 6, self.body.rect.h - 2),
        )

    def get_hitboxes(self, frame_index: int) -> list[Hitbox]:
        if self._attack_ms <= 0:
            return []
        elapsed = self.ATTACK_TOTAL_MS - self._attack_ms
        active = self.ATTACK_STARTUP_MS <= elapsed < self.ATTACK_STARTUP_MS + self.ATTACK_ACTIVE_MS
        if not active:
            return []
        if self.facing >= 0:
            rect = Rect(self.body.rect.right - 2, self.body.rect.y + 8, 20, 14)
            knockback = Vec2(230.0, -120.0)
        else:
            rect = Rect(self.body.rect.left - 18, self.body.rect.y + 8, 20, 14)
            knockback = Vec2(-230.0, -120.0)
        return [
            Hitbox(
                owner_id=self.entity_id,
                owner_team=self.team,
                rect=rect,
                damage=1,
                knockback=knockback,
                start_frame=frame_index,
                end_frame=frame_index,
            )
        ]

    def respawn(self, spawn: tuple[float, float]) -> None:
        self.spawn = spawn
        self.body.rect = Rect(spawn[0], spawn[1], self.body.rect.w, self.body.rect.h)
        self.body.velocity = Vec2(0.0, 0.0)
        self.dead = False
        self.hp = self.max_hp
        self.state = "idle"
        self._coyote_ms = 0
        self._jump_buffer_ms = 0
        self._attack_ms = 0
        self._hurt_ms = 0
        self._invulnerable_ms = 500


class WorldStateLike:
    collision_map: TileCollisionWorld
