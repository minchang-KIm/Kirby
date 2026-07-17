# Windsprig 한국어 학습 가이드

Windsprig: Echoes of the Gale은 하나의 결정론적 게임 런타임과 객체지향/디자인 패턴을 함께 설명하는 오리지널 액션 플랫폼 프로젝트입니다.

## 학습 순서

1. `core/ecs.py` 읽기: 월드/컴포넌트/시스템 스케줄러 구조 파악
2. `input/commands.py` 읽기: Command 패턴 입력 추상화 이해
3. `gameplay/systems/` 읽기: 시스템 단위 책임 분리 확인
4. `gameplay/abilities/` 읽기: Strategy 패턴 기반 에코 능력 확장 구조 확인
5. `meta/` 읽기: 월드맵 해금/세이브 스키마 흐름 이해
6. `docs/kr/labs/` 실습 수행

## 공식 용어

- Draw: 바람을 모아 가까운 메아리를 끌어오는 행동
- Capture: 끌어온 메아리를 포획하는 단계
- Harmonize: 포획한 메아리와 조율해 에코 능력을 얻는 단계
- Echo ability: 조율한 메아리로 사용하는 능력
- Wind Mote: 각 스테이지에서 수집하는 탐험 보상

## 패턴 매핑

- State: `gameplay/state_machine.py`
- Command: `input/commands.py`, `input/devices.py`
- Strategy: `gameplay/abilities/`
- Observer: `core/events.py`
- Factory Method: `gameplay/factory.py`
- Component(ECS): `gameplay/components/`, `core/ecs.py`
- Facade: `app.py` (`GameApp`)
- Template Method: 보스 페이즈 확장 포인트(능력/AI 루프 오버라이드 지점)

## 핵심 규칙

- 컴포넌트는 데이터만 가진다.
- 시스템은 한 책임만 가진다.
- 에코 능력과 AI의 변화 포인트는 전략 객체로 분리한다.
- 월드맵과 저장은 gameplay와 결합하지 않고 meta 계층에서 처리한다.
