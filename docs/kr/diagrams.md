# 아키텍처 다이어그램

## 1) 런루프 (Facade -> ECS)

```mermaid
flowchart LR
  A["GameApp.run"] --> B["InputDeviceMux.collect_frame"]
  B --> C["World.step(dt, input_frame)"]
  C --> D["SystemScheduler.run"]
  D --> E["InputCommandSystem"]
  D --> F["Movement/Collision/Inhale/Ability"]
  D --> G["Combat/Damage/Pickup/Goal/Respawn"]
  G --> H["HUD/Camera Snapshot"]
  H --> I["Renderer"]
```

## 2) 입력 -> 명령 -> 의도

```mermaid
flowchart LR
  A["Keyboard/Pads"] --> B["InputDeviceMux"]
  B --> C["InputFrame{slot -> commands}"]
  C --> D["InputCommandSystem"]
  D --> E["ControlIntent Component"]
  E --> F["Movement/Inhale/Ability Systems"]
```

## 3) 흡입/카피 시퀀스

```mermaid
sequenceDiagram
  participant P as Player
  participant IS as InhaleSystem
  participant W as World
  participant AS as AbilitySystem

  P->>IS: InhaleStartCommand
  IS->>W: set InhaleState.active
  IS->>W: capture nearby enemy
  P->>IS: InhaleReleaseCommand
  IS->>W: swallow enemy + set AbilityState.current
  P->>AS: AbilityUseCommand
  AS->>W: spawn projectile entity
```
