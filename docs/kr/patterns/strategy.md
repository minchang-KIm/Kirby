# Strategy 패턴

- 위치: `gameplay/abilities/base.py`, `gameplay/abilities/registry.py`
- 목적: 카피 능력별 공격/연출 차이를 객체로 분리
- 장점: 능력 추가 시 기존 시스템 수정 없이 JSON + Strategy 등록으로 확장
- 기본 구현: `DataDrivenAbilityStrategy`
