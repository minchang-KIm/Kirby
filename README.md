# Kirby RTD Study Clone (ECS + OOP)

Kirby’s Return to Dream Land 계열 메커닉을 학습 목적으로 재구성한 2D 액션 플랫폼 프로젝트입니다.

핵심 목표:
- 흡입 -> 삼키기/뱉기 -> 카피 능력 전환 루프 구현
- 월드맵 진행 + 해금 + 저장 구조 구현
- 로컬 4인(키보드 2인 + 게임패드 2인) 입력 구조 구현
- 디자인 패턴/객체지향 학습 자료와 코드 동시 제공

## 구현 상태

- ECS 하이브리드 런타임(`World + SystemScheduler`) 적용
- Command 패턴 입력 계층(`InputCommand`, `InputFrame`, 디바이스 mux) 적용
- Ability Strategy 레지스트리(데이터 드리븐 JSON) 적용
- 6월드 x 5노드(총 30 스테이지) 캠페인 카탈로그/월드맵 데이터 적용
- Save 스키마(`profiles[3]`, `unlocked_worlds`, `cleared_nodes`, `energy_spheres`, `best_times`) 적용
- 단위/통합 테스트에서 결정론 해시 및 진행/저장 규칙 검증

## 빠른 실행

1. `uv` 설치
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. 가상환경/의존성 설치
```powershell
python -m uv venv
python -m uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
```

3. 게임 실행
```powershell
python -m uv run python -m kirby_clone
```

4. 테스트 실행
```powershell
python -m uv run pytest -q
```

5. 패키징
```powershell
python -m uv run pyinstaller build.spec --noconfirm --clean
```

## 기본 조작

- 월드맵:
  - `Left/Right`, `A/D`: 노드 선택
  - `Enter`: 스테이지 시작
  - `Esc`: 종료
- 스테이지:
  - `Esc`: 월드맵 복귀
  - `R`: 스테이지 재시작

플레이어 키맵:
- P1: `A/D` 이동, `W` 점프/호버, `S` 흡입(눌렀다 떼기), `F` 능력 사용, `G` 가드, `H` 회피, `T` 능력 버리기
- P2: `Left/Right` 이동, `Up` 점프/호버, `Down` 흡입, `.` 능력 사용, `/` 가드, `Right Shift` 회피, `,` 능력 버리기
- P3/P4: 게임패드(기본 Xbox 버튼 매핑)

## 주요 디렉터리

- `kirby_clone/core/`: ECS, 이벤트 버스, 고정 시간 스텝, RNG
- `kirby_clone/input/`: 명령 객체, 키바인딩, 디바이스 입력 수집
- `kirby_clone/gameplay/`: 컴포넌트, 시스템, 능력 전략, 엔티티 팩토리, 런타임
- `kirby_clone/content/`: 캠페인/능력 데이터(JSON)
- `kirby_clone/meta/`: 월드맵 해금 규칙, 저장/완료 추적
- `docs/kr/`: 패턴 설명, 다이어그램, 실습 과제
- `tests/`: 단위/통합 테스트

## 학습 문서

- 패턴 개요: [docs/kr/README.md](docs/kr/README.md)
- 다이어그램: [docs/kr/diagrams.md](docs/kr/diagrams.md)
- 실습 과제: `docs/kr/labs/`

## 법적 고지

- 본 저장소는 학습 목적의 팬 프로젝트 구조 예시입니다.
- Nintendo/Kirby 원저작권 자산은 포함하지 않습니다.
- 팬에셋 사용 시 비공개 개인 학습용으로만 유지하고 외부 배포하지 마세요.
- 자세한 정책은 [assets/LICENSES.md](assets/LICENSES.md) 참고.
