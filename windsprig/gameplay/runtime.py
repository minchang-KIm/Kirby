"""Own the deterministic stage world and its immutable frame boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import astuple, dataclass, replace

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
    boss_command_sort_key,
)
from windsprig.gameplay.components import (
    AbilityState,
    ActorState,
    Attack,
    AttackRequest,
    CameraFocus,
    CapturedBy,
    CaptureState,
    Collider,
    DamageRecord,
    DefenseState,
    EchoPickup,
    EnemyAI,
    EnemyDropAbility,
    Facing,
    Health,
    Interaction,
    MovementState,
    PendingEnemyLaunch,
    PlayerSlot,
    Projectile,
    StageGoal,
    Team,
    Transform,
    Velocity,
)
from windsprig.gameplay.events import GameplayTopic, make_event
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
from windsprig.input.commands import InputFrame
from windsprig.input.roster import ActivePlayer


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
        self.world.events.subscribe("*", self._capture_step_event)

        # Stable player IDs keep slot-to-entity traces reproducible across roster orderings.
        self.sync_active_players(active_players)
        self._spawn_stage_entities()
        self._install_scheduler()
        self._last_simulation = self.world.snapshot()

    def _install_scheduler(self) -> None:
        systems: list[System] = [
            InputCommandSystem(),
            DefenseSystem(),
            MovementSystem(),
            EnemyAISystem(),
            CollisionSystem(),
            CaptureSystem(),
            AbilitySystem(),
            AttackSpawnSystem(),
            AttackMotionSystem(),
            CombatSystem(),
            DamageSystem(),
            InteractionSystem(),
        ]
        if self._boss_director is not None:
            systems.append(BossSystem(self._boss_director))
        systems.extend(
            [
                PickupSystem(),
                CoopRespawnSystem(),
                StageGoalSystem(),
                CameraSystem(),
            ]
        )
        self.world.scheduler.systems = systems

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
            entity_id = self.player_entities[slot]
            capture = self.world.try_component(entity_id, CaptureState)
            if capture is not None:
                CaptureSystem.release_player_capture(self.world, capture)
            del self.player_entities[slot]
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
        self._last_simulation = replacement._last_simulation
        return reset_snapshot

    @property
    def can_retry_checkpoint(self) -> bool:
        """Return false until Task 9 introduces production checkpoints."""
        return False

    def retry_from_checkpoint(self) -> StageSnapshot:
        """Reject checkpoint retries until the production checkpoint task."""
        raise ValueError("checkpoint retry is unavailable")

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
        world.resources["discovered_ability_ids"] = set()
        world.resources["stage_outcome"] = StageOutcome.RUNNING
        world.resources["camera_target"] = None
        world.resources["damage_queue"] = []
        world.resources["attack_requests"] = []
        world.resources["pending_enemy_launches"] = []
        world.resources["boss_commands"] = ()
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
            self.factory.spawn_energy_sphere(mote.tile_x, mote.tile_y, self.stage.tile_size)
        for interaction in self.stage.interactions:
            self.factory.spawn_interaction(interaction, self.stage.tile_size)
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

        outcome = world.resources.get("stage_outcome")
        if not isinstance(outcome, StageOutcome):
            raise TypeError("stage_outcome must be a StageOutcome")
        run_motes = world.resources.get("run_energy_spheres")
        if type(run_motes) is not int:
            raise TypeError("run_energy_spheres must be an integer")
        if run_motes < 0:
            raise ValueError("run_energy_spheres must be non-negative")
        collected = world.resources.get("collected_mote_ids")
        if not isinstance(collected, (tuple, list, set, frozenset)) or any(
            not isinstance(mote_id, str) for mote_id in collected
        ):
            raise TypeError("collected_mote_ids must be a collection of strings")
        discovered = world.resources.get("discovered_ability_ids")
        if not isinstance(discovered, (tuple, list, set, frozenset)) or any(
            not isinstance(ability_id, str) for ability_id in discovered
        ):
            raise TypeError("discovered_ability_ids must be a collection of strings")
        raw_damage_queue = world.resources.get("damage_queue")
        if not isinstance(raw_damage_queue, list) or any(type(item) is not DamageRecord for item in raw_damage_queue):
            raise TypeError("damage_queue must be a list of DamageRecord values")
        raw_attack_requests = world.resources.get("attack_requests")
        if not isinstance(raw_attack_requests, list) or any(
            type(request) is not AttackRequest for request in raw_attack_requests
        ):
            raise TypeError("attack_requests must be a list of AttackRequest values")
        raw_pending_launches = world.resources.get("pending_enemy_launches")
        if not isinstance(raw_pending_launches, list) or any(
            type(launch) is not PendingEnemyLaunch for launch in raw_pending_launches
        ):
            raise TypeError("pending_enemy_launches must be a list of PendingEnemyLaunch values")
        raw_boss_commands = world.resources.get("boss_commands")
        if not isinstance(raw_boss_commands, tuple) or any(
            type(command) is not BossCommand for command in raw_boss_commands
        ):
            raise TypeError("boss_commands must be a tuple of BossCommand values")
        boss_commands = tuple(raw_boss_commands)
        if boss_commands != tuple(sorted(boss_commands, key=boss_command_sort_key)):
            raise ValueError("boss_commands must be sorted canonically")
        return _ValidatedGameplayResources(
            active_players=active_players,
            active_authority=tuple(active_authority),
            stage_outcome=outcome,
            run_energy_spheres=run_motes,
            collected_mote_ids=tuple(sorted(set(collected))),
            discovered_ability_ids=tuple(sorted(set(discovered))),
            damage_queue=tuple(raw_damage_queue),
            attack_requests=tuple(raw_attack_requests),
            pending_enemy_launches=tuple(raw_pending_launches),
            boss_commands=boss_commands,
        )

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
        active_slots = {player.slot for player in active_players}
        players = self._player_views(active_slots)
        enemies = self._enemy_views()
        attacks = self._attack_views()
        echo_pickups = self._echo_pickup_views()
        interactions = self._interaction_views()
        bosses = self._boss_views()
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
            if (slot.slot in active_slots and self.player_entities.get(slot.slot) == entity_id and slot.is_leader)
        )
        leader_slot = leader_slots[0] if leader_slots else None
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
                goal_x=goal_x,
                goal_y=goal_y,
                at_goal_slots=(),
                required_slots=tuple(sorted(active_slots)),
                leader_slot=leader_slot,
                leader_confirmed=False,
                countdown_remaining_ms=0,
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
        if resources.run_energy_spheres > 0:
            ids.update(mote.mote_id for mote in self.stage.motes[: resources.run_energy_spheres])
        return tuple(sorted(ids))
