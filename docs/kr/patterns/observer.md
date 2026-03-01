# Observer 패턴

- 위치: `core/events.py`
- 목적: 시스템 간 느슨한 결합을 위한 이벤트 버스 제공
- 예시 이벤트: `ability_used`, `ability_copied`, `stage_cleared`, `actor_dead`
- 주의: 이벤트 큐는 프레임 단위로 소거해 무한 누적을 방지
