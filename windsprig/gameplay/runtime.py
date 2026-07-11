"""Own the deterministic stage world and its immutable frame boundary."""

from __future__ import annotations

from collections.abc import Sequence

from windsprig.config import GameConfig
from windsprig.content.loader import StageSpec
from windsprig.core.ecs import World
from windsprig.core.events import GameEvent
from windsprig.gameplay.abilities import AbilityRegistry
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    CameraFocus,
    Collider,
    ControlIntent,
    DrawState,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    Health,
    PlayerSlot,
    Projectile,
    StageGoal,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, make_event
from windsprig.gameplay.factory import EntityFactory
from windsprig.gameplay.snapshot import (
    AttackView,
    CameraTargetView,
    CheckpointView,
    EnemyView,
    GoalGatherView,
    PlayerView,
    StageFrame,
    StageOutcome,
    StageResult,
    StageSnapshot,
)
from windsprig.gameplay.systems import (
    AbilitySystem,
    CameraSystem,
    CollisionSystem,
    CombatSystem,
    CoopRespawnSystem,
    DamageSystem,
    EnemyAISystem,
    InputCommandSystem,
    MovementSystem,
    PickupSystem,
    StageGoalSystem,
)
from windsprig.input.commands import InputFrame
from windsprig.input.roster import ActivePlayer


class StageRuntime:
    """Run one stage and expose only active-roster, event, and snapshot contracts."""

    def __init__(
        self,
        config: GameConfig,
        stage: StageSpec,
        ability_registry: AbilityRegistry,
        active_players: Sequence[ActivePlayer],
        seed: int,
    ) -> None:
        if not stage.player_spawns:
            raise ValueError("stage must define at least one player spawn")
        self.config = config
        self.stage = stage
        self.ability_registry = ability_registry
        self.seed = seed
        self.world = self._new_world()
        self.factory = EntityFactory(self.world)
        self.player_entities: dict[int, int] = {}
        self._step_events: list[GameEvent] = []
        self._capturing_step_events = False
        self._result: StageResult | None = None
        self._elapsed_ms = 0
        self._snapshot_frame_index = 0
        self.world.events.subscribe("*", self._capture_step_event)

        # Stable player IDs keep slot-to-entity traces reproducible across roster orderings.
        self.sync_active_players(active_players)
        self._spawn_stage_entities()
        self.world.scheduler.systems = [
            InputCommandSystem(),
            EnemyAISystem(),
            MovementSystem(),
            CollisionSystem(),
            AbilitySystem(),
            CombatSystem(),
            DamageSystem(),
            PickupSystem(),
            CoopRespawnSystem(),
            StageGoalSystem(),
            CameraSystem(),
        ]
        self._last_simulation = self.world.snapshot()

    def step(self, input_frame: InputFrame) -> StageFrame:
        """Advance one fixed step and return its immutable state and events."""
        if self._result is not None:
            return StageFrame(self._last_simulation, self.snapshot(), (), self._result)

        self._step_events.clear()
        # Events already waiting in the bus belong to this step's queued frame.
        self._step_events.extend(self.world.events.peek())
        self._capturing_step_events = True
        try:
            simulation = self.world.step(self.config.fixed_dt_ms, input_frame)
        finally:
            self._capturing_step_events = False
        self._last_simulation = simulation
        self._snapshot_frame_index = simulation.frame_index
        self._elapsed_ms += self.config.fixed_dt_ms
        return StageFrame(simulation, self.snapshot(), tuple(self._step_events), self._result)

    def sync_active_players(
        self,
        active_players: Sequence[ActivePlayer],
    ) -> tuple[GameEvent, ...]:
        """Synchronize pause-lobby membership and return ordered roster events."""
        requested_players = self._validate_active_players(active_players)
        requested = {player.slot: player for player in requested_players}
        emitted: list[GameEvent] = []

        for slot in sorted(set(self.player_entities) - set(requested)):
            entity_id = self.player_entities.pop(slot)
            self.world.destroy_entity(entity_id)
            emitted.append(
                make_event(
                    GameplayTopic.PLAYER_LEFT,
                    self.world.frame_index,
                    entity_id=entity_id,
                    slot=slot,
                )
            )
        for slot in sorted(set(requested) - set(self.player_entities)):
            spawn_index = min(slot - 1, len(self.stage.player_spawns) - 1)
            x, y = self.stage.player_spawns[spawn_index]
            entity_id = self.factory.spawn_player(requested[slot], x, y)
            self.player_entities[slot] = entity_id
            emitted.append(
                make_event(
                    GameplayTopic.PLAYER_JOINED,
                    self.world.frame_index,
                    entity_id=entity_id,
                    slot=slot,
                )
            )
        for slot in sorted(set(requested) & set(self.player_entities)):
            entity_id = self.player_entities[slot]
            player_slot = self.world.get_component(entity_id, PlayerSlot)
            player_slot.is_leader = requested[slot].is_leader

        self.world.resources["active_players"] = requested_players
        for event in emitted:
            self.world.events.notify(event)
        return tuple(emitted)

    def snapshot(self) -> StageSnapshot:
        """Build a deterministic immutable view from the current ECS state."""
        return self._build_snapshot()

    @property
    def result(self) -> StageResult | None:
        """Return the frozen stage result once a later outcome system creates it."""
        return self._result

    def _new_world(self) -> World:
        world = World(seed=self.seed)
        world.resources["config"] = self.config
        world.resources["stage_spec"] = self.stage
        world.resources["collision_world"] = self.stage.build_collision_world()
        world.resources["ability_registry"] = self.ability_registry
        world.resources["run_energy_spheres"] = 0
        world.resources["collected_mote_ids"] = set()
        world.resources["stage_cleared"] = False
        world.resources["camera_target"] = None
        return world

    def _spawn_stage_entities(self) -> None:
        for enemy in self.stage.enemy_spawns:
            self.factory.spawn_enemy(
                x=enemy.x,
                y=enemy.y,
                kind=enemy.kind,
                ability=enemy.ability_id or "none",
                patrol_left=enemy.patrol_left,
                patrol_right=enemy.patrol_right,
            )
        for mote in self.stage.motes:
            self.factory.spawn_energy_sphere(mote.tile_x, mote.tile_y, self.stage.tile_size)
        self.factory.spawn_stage_goal(self.stage)

    def _capture_step_event(self, event: GameEvent) -> None:
        if self._capturing_step_events:
            self._step_events.append(event)

    def _validate_active_players(
        self,
        active_players: Sequence[ActivePlayer],
    ) -> tuple[ActivePlayer, ...]:
        players = tuple(active_players)
        seen_slots: set[int] = set()
        for player in players:
            if type(player.slot) is not int or not 1 <= player.slot <= self.config.max_local_players:
                raise ValueError(
                    f"active player slot must be between 1 and {self.config.max_local_players}"
                )
            if player.slot in seen_slots:
                raise ValueError(f"duplicate active player slot: {player.slot}")
            seen_slots.add(player.slot)
        return tuple(sorted(players, key=lambda player: player.slot))

    def _build_snapshot(self) -> StageSnapshot:
        active_players = self._active_players()
        active_slots = {player.slot for player in active_players}
        players = self._player_views(active_slots)
        enemies = self._enemy_views()
        attacks = self._attack_views()
        camera_targets = self._camera_target_views(active_slots)
        checkpoints = tuple(
            sorted(
                (
                    CheckpointView(
                        checkpoint_id=checkpoint.checkpoint_id,
                        x=float(checkpoint.tile_x * self.stage.tile_size),
                        y=float(checkpoint.tile_y * self.stage.tile_size),
                        is_active=False,
                    )
                    for checkpoint in self.stage.checkpoints
                ),
                key=lambda view: view.checkpoint_id,
            )
        )
        goal_rows = self.world.query(StageGoal, Transform)
        goal_x = float(goal_rows[0][2].x) if goal_rows else 0.0
        goal_y = float(goal_rows[0][2].y) if goal_rows else 0.0
        leader_slots = sorted(
            slot.slot
            for entity_id, slot in self.world.query(PlayerSlot)
            if (
                slot.slot in active_slots
                and self.player_entities.get(slot.slot) == entity_id
                and slot.is_leader
            )
        )
        leader_slot = leader_slots[0] if leader_slots else None
        outcome = (
            StageOutcome.COMPLETED
            if self.world.resources.get("stage_cleared", False)
            else StageOutcome.RUNNING
        )
        return StageSnapshot(
            frame_index=self._snapshot_frame_index,
            elapsed_ms=self._elapsed_ms,
            stage_id=self.stage.stage_id,
            world_id=self.stage.world_id,
            node_id=self.stage.node_id,
            outcome=outcome,
            players=players,
            enemies=enemies,
            attacks=attacks,
            echo_pickups=(),
            interactions=(),
            checkpoints=checkpoints,
            goal_gather=GoalGatherView(
                goal_x=goal_x,
                goal_y=goal_y,
                at_goal_slots=(),
                required_slots=tuple(sorted(active_slots)),
                leader_slot=leader_slot,
                leader_confirmed=False,
                countdown_remaining_ms=0,
            ),
            camera_targets=camera_targets,
            collected_mote_ids=self._collected_mote_ids(),
        )

    def _active_players(self) -> tuple[ActivePlayer, ...]:
        players = self.world.resources.get("active_players", ())
        if not isinstance(players, tuple):
            return ()
        return tuple(player for player in players if isinstance(player, ActivePlayer))

    def _player_views(self, active_slots: set[int]) -> tuple[PlayerView, ...]:
        views: list[PlayerView] = []
        for entity_id, slot, transform, collider, facing, actor, health, ability, intent, draw in (
            self.world.query(
                PlayerSlot,
                Transform,
                Collider,
                Facing,
                ActorState,
                Health,
                AbilityState,
                ControlIntent,
                DrawState,
            )
        ):
            if slot.slot not in active_slots or self.player_entities.get(slot.slot) != entity_id:
                continue
            views.append(
                PlayerView(
                    entity_id=entity_id,
                    slot=slot.slot,
                    x=transform.x,
                    y=transform.y,
                    width=collider.width,
                    height=collider.height,
                    facing=facing.direction,
                    actor_state=actor.name,
                    hp=health.current,
                    maximum_hp=health.maximum,
                    lives_remaining=slot.lives,
                    ability_id=ability.current,
                    ability_meter=0,
                    ability_charge_ms=0,
                    guard_active=intent.guard_held,
                    dodge_active=False,
                    invulnerable=health.invulnerable_ms > 0,
                    hover_remaining_ms=self.config.hover_duration_ms,
                    hover_max_ms=self.config.hover_duration_ms,
                    captured_ability_id=draw.captured_echo,
                    captured_visual_id=None,
                )
            )
        return tuple(sorted(views, key=lambda view: (view.slot, view.entity_id)))

    def _enemy_views(self) -> tuple[EnemyView, ...]:
        views: list[EnemyView] = []
        for entity_id, enemy, transform, collider, facing, actor, health, drop in self.world.query(
            EnemyAI,
            Transform,
            Collider,
            Facing,
            ActorState,
            Health,
            EnemyDropAbility,
        ):
            views.append(
                EnemyView(
                    entity_id=entity_id,
                    enemy_kind=enemy.kind,
                    x=transform.x,
                    y=transform.y,
                    width=collider.width,
                    height=collider.height,
                    facing=facing.direction,
                    actor_state=actor.name,
                    hp=health.current,
                    maximum_hp=health.maximum,
                    ability_id=None if drop.ability == "none" else drop.ability,
                    captured_by=None,
                )
            )
        return tuple(sorted(views, key=lambda view: view.entity_id))

    def _attack_views(self) -> tuple[AttackView, ...]:
        views = [
            AttackView(
                entity_id=entity_id,
                owner_entity_id=projectile.owner,
                attack_kind=projectile.tag,
                visual_id=projectile.tag,
                x=transform.x,
                y=transform.y,
                width=collider.width,
                height=collider.height,
                facing=-1 if velocity.vx < 0 else 1,
                ttl_ms=projectile.ttl_ms,
            )
            for entity_id, projectile, transform, collider, velocity in self.world.query(
                Projectile,
                Transform,
                Collider,
                Velocity,
            )
        ]
        return tuple(sorted(views, key=lambda view: view.entity_id))

    def _camera_target_views(self, active_slots: set[int]) -> tuple[CameraTargetView, ...]:
        views: list[CameraTargetView] = []
        for entity_id, slot, transform, focus, health in self.world.query(
            PlayerSlot,
            Transform,
            CameraFocus,
            Health,
        ):
            if (
                slot.slot not in active_slots
                or self.player_entities.get(slot.slot) != entity_id
                or not focus.enabled
                or focus.weight <= 0
                or health.dead
            ):
                continue
            views.append(
                CameraTargetView(
                    entity_id=entity_id,
                    slot=slot.slot,
                    x=transform.x,
                    y=transform.y,
                    weight=focus.weight,
                    enabled=True,
                )
            )
        return tuple(sorted(views, key=lambda view: (view.slot, view.entity_id)))

    def _collected_mote_ids(self) -> tuple[str, ...]:
        collected = self.world.resources.get("collected_mote_ids", ())
        if isinstance(collected, (tuple, list, set, frozenset)):
            ids = {mote_id for mote_id in collected if isinstance(mote_id, str)}
        else:
            ids = set()
        run_count = self.world.resources.get("run_energy_spheres", 0)
        if type(run_count) is int and run_count > 0:
            ids.update(mote.mote_id for mote in self.stage.motes[:run_count])
        return tuple(sorted(ids))
