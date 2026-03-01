# Kirby RTD 학습 가이드

이 프로젝트는 게임 구현과 객체지향/디자인 패턴 학습을 동시에 진행하기 위한 구조를 목표로 합니다.

## 학습 순서

1. `core/ecs.py` 읽기: 월드/컴포넌트/시스템 스케줄러 구조 파악
2. `input/commands.py` 읽기: Command 패턴 입력 추상화 이해
3. `gameplay/systems/` 읽기: 시스템 단위 책임 분리 확인
4. `gameplay/abilities/` 읽기: Strategy 패턴 능력 확장 구조 확인
5. `meta/` 읽기: 월드맵 해금/세이브 스키마 흐름 이해
6. `docs/kr/labs/` 실습 수행

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
- 능력/AI의 변화 포인트는 전략 객체로 분리한다.
- 월드맵/저장은 gameplay와 결합하지 않고 meta 계층에서 처리한다.
