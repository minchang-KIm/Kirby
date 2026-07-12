"""Own the deterministic stage world and its immutable frame boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import astuple, dataclass, replace
from typing import cast

from windsprig.config import GameConfig
from windsprig.content.loader import BossSpec, StageSpec, load_boss_catalog
from windsprig.core.ecs import System, World
from windsprig.core.events import GameEvent
from windsprig.gameplay.abilities import AbilityRegistry
from windsprig.gameplay.bosses import (
    BossCommand,
    BossDirector,
    BossState,
    BossSystem,
    validate_boss_commands,
)
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    Attack,
    AttackRequest,
    CameraFocus,
    CapturedBy,
    CaptureState,
    Checkpoint,
    Collider,
    ControlIntent,
    DamageRecord,
    DefenseState,
    EchoPickup,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    GatherState,
    Health,
    Interaction,
    MovementState,
    PendingEnemyLaunch,
    PlayerSlot,
    Projectile,
    Respawn,
    StageGoal,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, make_event, publish
from windsprig.gameplay.factory import EntityFactory
from windsprig.gameplay.snapshot import (
    AttackView,
    BossView,
    CameraTargetView,
    CheckpointView,
    EchoPickupView,
    EnemyView,
    GoalGatherView,
    InteractionView,
    PlayerView,
    StageFrame,
    StageOutcome,
    StageResult,
    StageSnapshot,
)
from windsprig.gameplay.systems import (
    AbilitySystem,
    AttackMotionSystem,
    AttackSpawnSystem,
    CameraSystem,
    CaptureSystem,
    CheckpointSystem,
    CollisionSystem,
    CombatSystem,
    CoopRespawnSystem,
    DamageSystem,
    DefenseSystem,
    EnemyAISystem,
    InputCommandSystem,
    InteractionSystem,
    MovementSystem,
    PickupSystem,
    StageGoalSystem,
)
from windsprig.gameplay.systems.attack_spawn_system import boss_attack_request
from windsprig.gameplay.systems.stage_goal_system import goal_participation
from windsprig.gameplay.validation import (
    build_stage_result,
    validate_attack_request,
    validate_attack_requests,
    validate_checkpoint_state,
    validate_damage_queue,
    validate_deaths_by_slot,
    validate_gather_state,
    validate_pending_enemy_launches,
    validate_result_ids,
)
from windsprig.input.commands import InputFrame
from windsprig.input.roster import ActivePlayer

type _RetryRow = tuple[
    int,
    PlayerSlot,
    Health,
    Transform,
    Velocity,
    Collider,
    DefenseState,
    CaptureState,
    ActorState,
    Respawn,
    ControlIntent,
    MovementState,
    AbilityState,
]


SYSTEM_ORDER: tuple[type[System], ...] = (
    InputCommandSystem,
    DefenseSystem,
    MovementSystem,
    EnemyAISystem,
    CollisionSystem,
    CaptureSystem,
    AbilitySystem,
    AttackSpawnSystem,
    AttackMotionSystem,
    CombatSystem,
    DamageSystem,
    InteractionSystem,
    PickupSystem,
    CheckpointSystem,
    CoopRespawnSystem,
    StageGoalSystem,
    CameraSystem,
)


@dataclass(frozen=True, slots=True)
class _ValidatedGameplayResources:
    """One strict canonical resource view shared by snapshots and hashes."""

    active_players: tuple[ActivePlayer, ...]
    active_authority: tuple[tuple[int, bool], ...]
    stage_outcome: StageOutcome
    run_energy_spheres: int
    collected_mote_ids: tuple[str, ...]
    discovered_ability_ids: tuple[str, ...]
    damage_queue: tuple[DamageRecord, ...]
    attack_requests: tuple[AttackRequest, ...]
    pending_enemy_launches: tuple[PendingEnemyLaunch, ...]
    boss_commands: tuple[BossCommand, ...]
    active_checkpoint_id: str
    deaths_by_slot: tuple[tuple[int, int], ...]
    stage_result: StageResult | None


class StageRuntime:
    """Run one stage and expose only active-roster, event, and snapshot contracts."""

    SYSTEM_ORDER = SYSTEM_ORDER

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
        self._boss_specs: Mapping[str, BossSpec] | None = None
        self._boss_director: BossDirector | None = None
        if stage.boss_id is not None:
            boss_specs = load_boss_catalog(config.content_dir)
            if stage.boss_id not in boss_specs:
                raise ValueError(f"stage boss_id is absent from the boss catalog: {stage.boss_id}")
            self._boss_specs = boss_specs
            self._boss_director = BossDirector(boss_specs)
        self.world = self._new_world()
        self.factory = EntityFactory(self.world)
        self.player_entities: dict[int, int] = {}
        self._step_events: list[GameEvent] = []
        self._capturing_step_events = False
        self._result: StageResult | None = None
        self._elapsed_ms = 0
        self._snapshot_frame_index = 0
        self._step_elapsed_ms: int | None = None
        self.world.events.subscribe("*", self._capture_step_event)

        # Stable player IDs keep slot-to-entity traces reproducible across roster orderings.
        self.sync_active_players(active_players)
        self._spawn_stage_entities()
        self._install_scheduler()
        self._last_simulation = self.world.snapshot()

    def _install_scheduler(self) -> None:
        systems: list[System] = []
        for system_type in self.SYSTEM_ORDER:
            if system_type is PickupSystem and self._boss_director is not None:
                # Boss decisions resolve after interactions and feed the next spawn step.
                systems.append(BossSystem(self._boss_director))
            systems.append(system_type())
        self.world.scheduler.systems = systems

    def step(self, input_frame: InputFrame) -> StageFrame:
        """Advance one fixed step and return its immutable state and events."""
        resources = self._validate_gameplay_resources(self.world)
        if resources.stage_outcome is not StageOutcome.RUNNING:
            return StageFrame(self._last_simulation, self.snapshot(), (), self._result)

        # Validate mutable queues before input, timers, RNG, ECS, events, or frame state can change.
        self._step_events.clear()
        # Events already waiting in the bus belong to this step's queued frame.
        self._step_events.extend(self.world.events.peek())
        # WHY: World.snapshot() hashes terminal resources before World increments
        # its frame index. Reserving the next fixed-step timestamp gives both the
        # in-step hash and the post-step runtime one timing authority.
        next_elapsed_ms = self._elapsed_ms + self.config.fixed_dt_ms
        self._step_elapsed_ms = next_elapsed_ms
        try:
            self._capturing_step_events = True
            try:
                simulation = self.world.step(self.config.fixed_dt_ms, input_frame)
            finally:
                self._capturing_step_events = False
            self._last_simulation = simulation
            self._snapshot_frame_index = simulation.frame_index
            self._elapsed_ms = next_elapsed_ms
            resources = self._validate_gameplay_resources(self.world)
            if resources.stage_outcome is StageOutcome.COMPLETED:
                if resources.stage_result is None:
                    raise RuntimeError("completed stages must own one frozen StageResult")
                self._result = resources.stage_result
        finally:
            self._step_elapsed_ms = None
        return StageFrame(simulation, self.snapshot(), tuple(self._step_events), self._result)

    def sync_active_players(
        self,
        active_players: Sequence[ActivePlayer],
    ) -> tuple[GameEvent, ...]:
        """Synchronize pause-lobby membership and return ordered roster events."""
        requested_players = self._validate_active_players(active_players)
        requested = {player.slot: player for player in requested_players}
        emitted: list[GameEvent] = []
        outcome = self.world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        if outcome is not StageOutcome.RUNNING:
            raise ValueError("active players cannot change after a stage outcome")
        cancellation = self._cancel_gather_for_roster_change(requested_players)
        if cancellation is not None:
            # Pause-lobby consumers observe cancellation before the roster edge
            # that invalidated the countdown is applied.
            self.world.events.notify(cancellation)
            emitted.append(cancellation)
        raw_deaths = self.world.resources.get("deaths_by_slot")
        current_deaths = dict(validate_deaths_by_slot(raw_deaths, tuple(sorted(self.player_entities))))

        roster_events: list[GameEvent] = []
        for slot in sorted(set(self.player_entities) - set(requested)):
            entity_id = self.player_entities[slot]
            capture = self.world.try_component(entity_id, CaptureState)
            if capture is not None:
                CaptureSystem.release_player_capture(self.world, capture)
            del self.player_entities[slot]
            self.world.destroy_entity(entity_id)
            current_deaths.pop(slot)
            roster_events.append(
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
            current_deaths[slot] = 0
            roster_events.append(
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
        self.world.resources["deaths_by_slot"] = current_deaths
        for event in roster_events:
            self.world.events.notify(event)
        emitted.extend(roster_events)
        return tuple(emitted)

    def _cancel_gather_for_roster_change(
        self,
        requested_players: tuple[ActivePlayer, ...],
    ) -> GameEvent | None:
        current_authority = tuple(
            (slot, self.world.get_component(entity_id, PlayerSlot).is_leader)
            for slot, entity_id in sorted(self.player_entities.items())
        )
        requested_authority = tuple((player.slot, player.is_leader) for player in requested_players)
        if current_authority == requested_authority:
            return None
        gather_rows = self.world.query(GatherState)
        if len(gather_rows) > 1:
            raise RuntimeError("stages must retain at most one gather state")
        if not gather_rows:
            return None
        _, gather = cast(tuple[int, GatherState], gather_rows[0])
        validate_gather_state(gather)
        if gather.countdown_remaining_ms == 0:
            return None
        leader_slot = gather.cancel()
        if leader_slot is None:
            raise ValueError("an active gather countdown must retain its leader")
        return make_event(
            GameplayTopic.GATHER_CANCELLED,
            self.world.frame_index,
            leader_slot=leader_slot,
            reason="roster_changed",
        )

    def snapshot(self) -> StageSnapshot:
        """Build a deterministic immutable view from the current ECS state."""
        return self._build_snapshot()

    def reset_stage(self) -> StageSnapshot:
        """Rebuild this stage from its original seed and current sorted roster."""
        active_players = self._current_players_for_reset()
        replacement = StageRuntime(
            self.config,
            self.stage,
            self.ability_registry,
            active_players,
            self.seed,
        )
        reset_snapshot = replacement.snapshot()
        event_bus = self.world.events
        event_bus.drain()
        replacement.world.events = event_bus
        replacement.world.set_resource_hash_projection(self._gameplay_resource_hash)
        self.world = replacement.world
        self.factory = replacement.factory
        self.player_entities = replacement.player_entities
        self._boss_specs = replacement._boss_specs
        self._boss_director = replacement._boss_director
        self._step_events.clear()
        self._capturing_step_events = False
        self._result = replacement._result
        self._elapsed_ms = replacement._elapsed_ms
        self._snapshot_frame_index = replacement._snapshot_frame_index
        self._step_elapsed_ms = replacement._step_elapsed_ms
        self._last_simulation = replacement._last_simulation
        return reset_snapshot

    @property
    def can_retry_checkpoint(self) -> bool:
        """Return whether the entire failed active team can pay one life."""
        resources = self._validate_gameplay_resources(self.world)
        rows = self._validated_retry_rows(resources)
        self._validate_retry_capture_state(rows)
        return (
            resources.stage_outcome is StageOutcome.FAILED
            and bool(rows)
            and all(health.dead and type(slot.lives) is int and slot.lives >= 1 for _, slot, health, *_ in rows)
        )

    def retry_from_checkpoint(self) -> StageSnapshot:
        """Atomically restore every required player at the active checkpoint."""
        resources = self._validate_gameplay_resources(self.world)
        rows = self._validated_retry_rows(resources)
        if (
            resources.stage_outcome is not StageOutcome.FAILED
            or not rows
            or any(not health.dead or type(slot.lives) is not int or slot.lives < 1 for _, slot, health, *_ in rows)
        ):
            raise ValueError("checkpoint retry is unavailable")

        checkpoint_rows = validate_checkpoint_state(self.world, self.stage)
        _, checkpoint, _, _ = next(
            row for row in checkpoint_rows if row[1].checkpoint_id == resources.active_checkpoint_id
        )
        targets = tuple(
            (checkpoint.x, checkpoint.y - index * collider.height)
            for index, (_, _, _, _, _, collider, *_) in enumerate(rows)
        )
        if any(y < 0.0 for _, y in targets):
            raise ValueError("checkpoint player offsets must stay inside the stage")
        self._validate_retry_capture_state(rows)
        gather_rows = self.world.query(GatherState)
        if len(gather_rows) != 1:
            raise RuntimeError("stages must retain exactly one gather state")
        _, gather = cast(tuple[int, GatherState], gather_rows[0])
        deferred = self.world.resources.get("deferred_echo_pickup_ids")
        if deferred is not None and type(deferred) is not set:
            raise TypeError("deferred_echo_pickup_ids must be a set")

        # Every validation above precedes the first life charge or ECS mutation.
        self.world.events.drain()
        for entity_id in sorted(
            {row[0] for row in self.world.query(Attack)} | {row[0] for row in self.world.query(Projectile)}
        ):
            self.world.destroy_entity(entity_id)
        cast(list[DamageRecord], self.world.resources["damage_queue"]).clear()
        cast(list[AttackRequest], self.world.resources["attack_requests"]).clear()
        cast(list[PendingEnemyLaunch], self.world.resources["pending_enemy_launches"]).clear()
        self.world.resources["boss_commands"] = ()
        self.world.resources.pop("deferred_echo_pickup_ids", None)
        gather.cancel()
        gather.at_goal_slots = ()

        for index, row in enumerate(rows):
            (
                entity_id,
                slot,
                health,
                transform,
                velocity,
                collider,
                defense,
                capture,
                actor,
                respawn,
                intent,
                movement,
                ability,
            ) = row
            CaptureSystem.release_player_capture(self.world, capture)
            slot.lives -= 1
            health.current = health.maximum
            health.dead = False
            health.invulnerable_ms = self.config.respawn_invulnerable_ms
            transform.x, transform.y = targets[index]
            velocity.vx = velocity.vy = 0.0
            collider.on_ground = False
            defense.guarding = False
            defense.dodge_remaining_ms = 0
            defense.dodge_cooldown_ms = 0
            defense.dodge_direction = 1
            actor.name = "Idle"
            actor.timer_ms = 0
            respawn.x, respawn.y = targets[index]
            respawn.timer_ms = 0
            respawn.started_frame = -1
            _reset_control_intent(intent)
            movement.coyote_remaining_ms = 0
            movement.jump_buffer_remaining_ms = 0
            movement.hover_remaining_ms = self.config.hover_duration_ms
            movement.hover_ready = True
            ability.cooldown_remaining_ms = 0
            ability.charge_ms = 0
            ability.combo_step = 0
            ability.combo_window_remaining_ms = 0
            ability.armor_remaining_ms = 0

        self.world.frame_input = InputFrame.empty()
        self.world.resources["stage_result"] = None
        self.world.resources["stage_outcome"] = StageOutcome.RUNNING
        self._result = None
        self._step_events.clear()
        for entity_id, slot, *_ in rows:
            publish(
                self.world,
                GameplayTopic.PLAYER_RESPAWNED,
                entity_id=entity_id,
                slot=slot.slot,
                checkpoint_id=checkpoint.checkpoint_id,
                cost=1,
            )
        return self.snapshot()

    def _validated_retry_rows(
        self,
        resources: _ValidatedGameplayResources,
    ) -> tuple[_RetryRow, ...]:
        rows = cast(
            list[_RetryRow],
            self.world.query(
                PlayerSlot,
                Health,
                Transform,
                Velocity,
                Collider,
                DefenseState,
                CaptureState,
                ActorState,
                Respawn,
                ControlIntent,
                MovementState,
                AbilityState,
            ),
        )
        by_slot = {row[1].slot: row for row in rows}
        active_slots = tuple(player.slot for player in resources.active_players)
        if tuple(sorted(by_slot)) != active_slots:
            raise ValueError("retry participants must exactly match active player slots")
        canonical = tuple(by_slot[slot] for slot in active_slots)
        for entity_id, slot, health, *_ in canonical:
            if self.player_entities.get(slot.slot) != entity_id:
                raise ValueError("retry participants must match player_entities")
            if type(slot.lives) is not int or slot.lives < 0:
                raise ValueError("player lives must be non-negative integers")
            if (
                type(health.current) is not int
                or type(health.maximum) is not int
                or health.maximum <= 0
                or not 0 <= health.current <= health.maximum
                or type(health.dead) is not bool
            ):
                raise ValueError("player health state is invalid for checkpoint retry")
        return canonical

    def _validate_retry_capture_state(self, rows: tuple[_RetryRow, ...]) -> None:
        for entity_id, _, _, _, _, _, _, capture, *_ in rows:
            if capture.phase not in {"idle", "drawing", "holding"}:
                raise ValueError("player capture phase is invalid for checkpoint retry")
            if capture.phase != "holding":
                if any(
                    value is not None
                    for value in (
                        capture.captured_entity_id,
                        capture.captured_ability_id,
                        capture.captured_visual_id,
                    )
                ):
                    raise ValueError("non-holding capture state must not retain captured facts")
                continue
            enemy_id = capture.captured_entity_id
            if type(enemy_id) is not int or enemy_id not in self.world.alive_entities:
                raise ValueError("holding capture state must reference a live entity")
            owner = self.world.try_component(enemy_id, CapturedBy)
            if owner is None or owner.player_entity_id != entity_id:
                raise ValueError("holding capture ownership must match its player")

    @property
    def result(self) -> StageResult | None:
        """Return the exact frozen completion facts owned by this runtime."""
        resources = self._validate_gameplay_resources(self.world)
        if resources.stage_result is not self._result:
            raise ValueError("world stage_result must be the frozen StageResult authority")
        return resources.stage_result

    def _new_world(self) -> World:
        world = World(seed=self.seed)
        world.resources["config"] = self.config
        world.resources["stage_spec"] = self.stage
        world.resources["collision_world"] = self.stage.build_collision_world()
        world.resources["ability_registry"] = self.ability_registry
        world.resources["run_energy_spheres"] = 0
        world.resources["collected_mote_ids"] = set()
        world.resources["discovered_ability_ids"] = set()
        world.resources["stage_outcome"] = StageOutcome.RUNNING
        world.resources["camera_target"] = None
        world.resources["damage_queue"] = []
        world.resources["attack_requests"] = []
        world.resources["pending_enemy_launches"] = []
        world.resources["boss_commands"] = ()
        world.resources["active_players"] = ()
        world.resources["active_checkpoint_id"] = None
        world.resources["deaths_by_slot"] = {}
        world.resources["stage_result"] = None
        world.set_resource_hash_projection(self._gameplay_resource_hash)
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
            self.factory.spawn_energy_sphere(
                mote.tile_x,
                mote.tile_y,
                self.stage.tile_size,
                mote_id=mote.mote_id,
            )
        for interaction in self.stage.interactions:
            self.factory.spawn_interaction(interaction, self.stage.tile_size)
        for index, checkpoint in enumerate(self.stage.checkpoints):
            self.factory.spawn_checkpoint(
                checkpoint,
                self.stage.tile_size,
                active=index == 0,
            )
        self._spawn_boss()
        self.factory.spawn_stage_goal(self.stage)

    def _spawn_boss(self) -> None:
        if self.stage.boss_id is None:
            return
        if self._boss_specs is None or self._boss_director is None:
            raise RuntimeError("boss stage composition is incomplete")
        spec = self._boss_specs[self.stage.boss_id]
        entity_id = self.world.create_entity()
        width = height = 64
        goal_x, _ = self.stage.goal_tile
        x = float(max(0, goal_x - 4) * self.stage.tile_size)
        y = float(max(0, self.stage.ground_y_tile * self.stage.tile_size - height))
        self.world.add_component(entity_id, Transform(x, y))
        self.world.add_component(entity_id, Collider(width=width, height=height))
        self.world.add_component(entity_id, Team("enemy"))
        self.world.add_component(
            entity_id,
            Health(current=spec.max_hp, maximum=spec.max_hp),
        )
        self.world.add_component(entity_id, ActorState())
        self.world.add_component(entity_id, Facing(direction=-1))
        self.world.add_component(
            entity_id,
            self._boss_director.start(spec.boss_id, entity_id),
        )

    def _current_players_for_reset(self) -> tuple[ActivePlayer, ...]:
        resources = self._validate_gameplay_resources(self.world)
        metadata = {player.slot: player for player in resources.active_players}
        players: list[ActivePlayer] = []
        for slot in sorted(self.player_entities):
            entity_id = self.player_entities[slot]
            player_slot = self.world.get_component(entity_id, PlayerSlot)
            players.append(replace(metadata[slot], is_leader=player_slot.is_leader))
        return tuple(players)

    def _gameplay_resource_hash(self, world: World) -> dict[str, object]:
        resources = self._validate_gameplay_resources(world)
        return {
            "active_players": resources.active_authority,
            "stage_outcome": resources.stage_outcome.value,
            "run_energy_spheres": resources.run_energy_spheres,
            "collected_mote_ids": resources.collected_mote_ids,
            "discovered_ability_ids": resources.discovered_ability_ids,
            "damage_queue": tuple(astuple(item) for item in resources.damage_queue),
            "attack_requests": tuple(astuple(request) for request in resources.attack_requests),
            "pending_enemy_launches": tuple(astuple(launch) for launch in resources.pending_enemy_launches),
            "boss_commands": tuple(astuple(command) for command in resources.boss_commands),
            "active_checkpoint_id": resources.active_checkpoint_id,
            "deaths_by_slot": resources.deaths_by_slot,
            "stage_result": (astuple(resources.stage_result) if resources.stage_result is not None else None),
        }

    def _validate_gameplay_resources(
        self,
        world: World,
    ) -> _ValidatedGameplayResources:
        raw_players = world.resources.get("active_players")
        if not isinstance(raw_players, tuple):
            raise TypeError("active_players must be a sorted tuple of ActivePlayer values")
        players: list[ActivePlayer] = []
        for player in raw_players:
            if not isinstance(player, ActivePlayer):
                raise TypeError("active_players must be a sorted tuple of ActivePlayer values")
            players.append(player)
        active_players = tuple(players)
        sorted_players = self._validate_active_players(active_players)
        if active_players != sorted_players:
            raise ValueError("active_players must be sorted by slot")
        active_slots = tuple(player.slot for player in active_players)
        entity_slots = tuple(sorted(self.player_entities))
        if active_slots != entity_slots:
            raise ValueError("active_players slots must match player_entities")

        active_authority: list[tuple[int, bool]] = []
        for slot in entity_slots:
            try:
                player_slot = world.get_component(self.player_entities[slot], PlayerSlot)
            except KeyError:
                raise ValueError("player_entities must reference matching PlayerSlot components") from None
            if player_slot.slot != slot:
                raise ValueError("player_entities must reference matching PlayerSlot components")
            active_authority.append((slot, player_slot.is_leader))

        gather_rows = world.query(GatherState)
        goal_gather_rows = world.query(StageGoal, GatherState)
        if len(gather_rows) != 1 or len(goal_gather_rows) != 1:
            raise RuntimeError("stages must retain exactly one goal-owned gather state")
        validate_gather_state(cast(tuple[int, GatherState], gather_rows[0])[1])

        deaths = validate_deaths_by_slot(
            world.resources.get("deaths_by_slot"),
            active_slots,
        )
        checkpoint_rows = validate_checkpoint_state(world, self.stage)
        active_checkpoint_id = next(
            checkpoint.checkpoint_id for _, checkpoint, _, _ in checkpoint_rows if checkpoint.active
        )

        outcome = world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        run_motes = world.resources.get("run_energy_spheres")
        if type(run_motes) is not int:
            raise TypeError("run_energy_spheres must be an integer")
        if run_motes < 0:
            raise ValueError("run_energy_spheres must be non-negative")
        collected = validate_result_ids(
            world.resources.get("collected_mote_ids"),
            "collected_mote_ids",
            {mote.mote_id for mote in self.stage.motes},
            self.stage.stage_id,
        )
        if run_motes != len(collected):
            raise ValueError("run_energy_spheres must exactly count collected stable mote IDs")
        raw_discovered = world.resources.get("discovered_ability_ids")
        if not isinstance(raw_discovered, (tuple, list, set, frozenset)) or any(
            type(ability_id) is not str for ability_id in raw_discovered
        ):
            raise TypeError("discovered_ability_ids must be a collection of strings")
        discovered = tuple(sorted(set(raw_discovered)))
        damage_queue = validate_damage_queue(world.resources.get("damage_queue"))
        attack_requests = validate_attack_requests(world.resources.get("attack_requests"))
        pending_launches = validate_pending_enemy_launches(world.resources.get("pending_enemy_launches"))
        boss_commands = validate_boss_commands(world.resources.get("boss_commands"))
        boss_rows = world.query(BossState)
        if boss_commands and len(boss_rows) == 1:
            owner_id = boss_rows[0][0]
            for command in boss_commands:
                request = boss_attack_request(owner_id, command)
                if request is not None:
                    validate_attack_request(request)
        stage_result = world.resources.get("stage_result")
        if stage_result is not None and type(stage_result) is not StageResult:
            raise TypeError("stage_result must be a StageResult or None")
        validated_result = stage_result
        if outcome is StageOutcome.COMPLETED and validated_result is None:
            raise ValueError("completed stage_outcome requires stage_result")
        if outcome is not StageOutcome.COMPLETED and validated_result is not None:
            raise ValueError("stage_result is allowed only for a completed outcome")
        if validated_result is not None:
            expected_clear_time_ms = self._authoritative_elapsed_ms(world)
            if validated_result.clear_time_ms != expected_clear_time_ms:
                raise ValueError("stage_result.clear_time_ms must match runtime-owned fixed-step elapsed time")
            expected_result = build_stage_result(
                world,
                self.stage,
                expected_clear_time_ms,
            )
            if validated_result != expected_result:
                raise ValueError("stage_result must exactly match gameplay-owned completion facts")
            if self._result is None:
                if self._step_elapsed_ms is None:
                    raise ValueError("stage_result can be frozen only by an active fixed step")
            elif validated_result is not self._result:
                raise ValueError("world stage_result must be the frozen StageResult authority")
        return _ValidatedGameplayResources(
            active_players=active_players,
            active_authority=tuple(active_authority),
            stage_outcome=outcome,
            run_energy_spheres=run_motes,
            collected_mote_ids=collected,
            discovered_ability_ids=discovered,
            damage_queue=damage_queue,
            attack_requests=attack_requests,
            pending_enemy_launches=pending_launches,
            boss_commands=boss_commands,
            active_checkpoint_id=active_checkpoint_id,
            deaths_by_slot=deaths,
            stage_result=validated_result,
        )

    def _authoritative_elapsed_ms(self, world: World) -> int:
        """Bind result time to the runtime's fixed-step clock, never result input."""

        world_elapsed_ms = world.frame_index * self.config.fixed_dt_ms
        expected_elapsed_ms = self._step_elapsed_ms if self._step_elapsed_ms is not None else self._elapsed_ms
        if world_elapsed_ms not in {self._elapsed_ms, expected_elapsed_ms}:
            raise ValueError("runtime elapsed time must match the fixed-step frame index")
        return expected_elapsed_ms

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
                raise ValueError(f"active player slot must be between 1 and {self.config.max_local_players}")
            if player.slot in seen_slots:
                raise ValueError(f"duplicate active player slot: {player.slot}")
            seen_slots.add(player.slot)
        return tuple(sorted(players, key=lambda player: player.slot))

    def _build_snapshot(self) -> StageSnapshot:
        resources = self._validate_gameplay_resources(self.world)
        active_players = resources.active_players
        active_slot_order = tuple(player.slot for player in active_players)
        active_slots = set(active_slot_order)
        players = self._player_views(active_slots)
        enemies = self._enemy_views()
        attacks = self._attack_views()
        echo_pickups = self._echo_pickup_views()
        interactions = self._interaction_views()
        bosses = self._boss_views()
        camera_targets = self._camera_target_views(active_slots)
        checkpoints = tuple(
            CheckpointView(
                checkpoint_id=checkpoint.checkpoint_id,
                x=transform.x,
                y=transform.y,
                is_active=checkpoint.active,
            )
            for _, checkpoint, transform in self.world.query(Checkpoint, Transform)
        )
        goal_rows = self.world.query(StageGoal, GatherState, Transform, Collider)
        if len(goal_rows) != 1:
            raise RuntimeError("stages must retain exactly one goal and gather state")
        _, _, gather, goal_transform, goal_collider = cast(
            tuple[int, StageGoal, GatherState, Transform, Collider],
            goal_rows[0],
        )
        _, required_slots, at_goal_slots = goal_participation(
            self.world,
            active_slot_order,
            goal_transform,
            goal_collider,
        )
        roster_leaders = tuple(
            slot.slot
            for entity_id, slot in self.world.query(PlayerSlot)
            if slot.slot in active_slots and self.player_entities.get(slot.slot) == entity_id and slot.is_leader
        )
        visible_leader_slot = gather.leader_slot if gather.leader_slot is not None else next(iter(roster_leaders), None)
        return StageSnapshot(
            frame_index=self._snapshot_frame_index,
            elapsed_ms=self._elapsed_ms,
            stage_id=self.stage.stage_id,
            world_id=self.stage.world_id,
            node_id=self.stage.node_id,
            outcome=resources.stage_outcome,
            players=players,
            enemies=enemies,
            attacks=attacks,
            echo_pickups=echo_pickups,
            interactions=interactions,
            checkpoints=checkpoints,
            goal_gather=GoalGatherView(
                goal_x=float(goal_transform.x),
                goal_y=float(goal_transform.y),
                at_goal_slots=at_goal_slots,
                required_slots=required_slots,
                leader_slot=visible_leader_slot,
                leader_confirmed=gather.leader_confirmed,
                countdown_remaining_ms=gather.countdown_remaining_ms,
            ),
            camera_targets=camera_targets,
            bosses=bosses,
            collected_mote_ids=self._collected_mote_ids(resources),
        )

    def _player_views(self, active_slots: set[int]) -> tuple[PlayerView, ...]:
        views: list[PlayerView] = []
        for (
            entity_id,
            slot,
            transform,
            collider,
            facing,
            actor,
            health,
            ability,
            movement,
            defense,
            capture,
        ) in self.world.query(
            PlayerSlot,
            Transform,
            Collider,
            Facing,
            ActorState,
            Health,
            AbilityState,
            MovementState,
            DefenseState,
            CaptureState,
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
                    ability_id=ability.current_id,
                    ability_meter=ability.meter,
                    ability_charge_ms=ability.charge_ms,
                    guard_active=defense.guarding,
                    dodge_active=defense.dodge_remaining_ms > 0,
                    invulnerable=(
                        health.invulnerable_ms > 0
                        or defense.dodge_remaining_ms
                        > self.config.dodge_duration_ms - self.config.dodge_invulnerable_ms
                    ),
                    hover_remaining_ms=movement.hover_remaining_ms,
                    hover_max_ms=self.config.hover_duration_ms,
                    captured_ability_id=capture.captured_ability_id,
                    captured_visual_id=capture.captured_visual_id,
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
                    captured_by=(
                        captured.player_entity_id
                        if (captured := self.world.try_component(entity_id, CapturedBy)) is not None
                        else None
                    ),
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
            if not self.world.has_component(entity_id, Attack)
        ]
        views.extend(
            AttackView(
                entity_id=entity_id,
                owner_entity_id=attack.owner_entity_id,
                attack_kind=attack.attack_kind,
                visual_id=attack.visual_id,
                x=transform.x,
                y=transform.y,
                width=collider.width,
                height=collider.height,
                facing=(-1 if velocity.vx < 0.0 or (velocity.vx == 0.0 and attack.knockback_x < 0.0) else 1),
                ttl_ms=attack.ttl_ms,
            )
            for entity_id, attack, transform, collider, velocity in self.world.query(
                Attack,
                Transform,
                Collider,
                Velocity,
            )
        )
        return tuple(sorted(views, key=lambda view: view.entity_id))

    def _echo_pickup_views(self) -> tuple[EchoPickupView, ...]:
        views = [
            EchoPickupView(
                entity_id=entity_id,
                ability_id=echo.ability_id,
                x=transform.x,
                y=transform.y,
            )
            for entity_id, echo, transform in self.world.query(EchoPickup, Transform)
        ]
        return tuple(sorted(views, key=lambda view: view.entity_id))

    def _interaction_views(self) -> tuple[InteractionView, ...]:
        views = [
            InteractionView(
                entity_id=entity_id,
                interaction_id=interaction.interaction_id,
                interaction_kind=interaction.kind,
                interaction_state=interaction.state,
                x=transform.x,
                y=transform.y,
                width=collider.width,
                height=collider.height,
            )
            for entity_id, interaction, transform, collider in self.world.query(
                Interaction,
                Transform,
                Collider,
            )
        ]
        return tuple(sorted(views, key=lambda view: view.entity_id))

    def _boss_views(self) -> tuple[BossView, ...]:
        if self._boss_specs is None:
            return ()
        views: list[BossView] = []
        for entity_id, state, transform, collider, facing, actor, health in self.world.query(
            BossState,
            Transform,
            Collider,
            Facing,
            ActorState,
            Health,
        ):
            phase = self._boss_specs[state.boss_id].phases[state.phase_index]
            telegraphing = state.mode == "telegraph"
            views.append(
                BossView(
                    entity_id=entity_id,
                    boss_id=state.boss_id,
                    phase_id=state.phase_id,
                    x=transform.x,
                    y=transform.y,
                    width=collider.width,
                    height=collider.height,
                    facing=facing.direction,
                    actor_state=actor.name,
                    hp=health.current,
                    maximum_hp=health.maximum,
                    telegraph_id=(state.active_attack_id if telegraphing else None),
                    telegraph_remaining_ms=(state.remaining_ms if telegraphing else 0),
                    vulnerability_state=phase.vulnerability,
                )
            )
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

    def _collected_mote_ids(
        self,
        resources: _ValidatedGameplayResources,
    ) -> tuple[str, ...]:
        ids = set(resources.collected_mote_ids)
        return tuple(sorted(ids))


def _reset_control_intent(intent: ControlIntent) -> None:
    """Clear every edge and held input before a checkpoint retry resumes."""

    intent.move_axis = 0
    intent.jump_pressed = False
    intent.hover_held = False
    intent.draw_started = False
    intent.draw_released = False
    intent.ability_pressed = False
    intent.ability_held = False
    intent.ability_released = False
    intent.ability_consumed = False
    intent.guard_held = False
    intent.dodge_pressed = False
    intent.drop_pressed = False
    intent.gather_confirmed = False
