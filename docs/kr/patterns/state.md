# State 패턴

- 위치: `gameplay/state_machine.py`, `components/ActorState`
- 목적: 플레이어/적의 상태 전이를 테이블로 강제
- 장점: 불법 상태 전이(예: Inhale -> Guard)를 코드 레벨에서 차단
- 확장: 보스 전용 상태를 추가할 때 전이표만 확장하면 시스템 코드는 유지
