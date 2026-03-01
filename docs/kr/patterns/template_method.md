# Template Method 패턴

- 현재 적용 지점: `EnemyAISystem`/능력 루프의 공통 업데이트 틀
- 확장 방향: 보스 페이즈 클래스를 `BossPhaseBase.update()` 템플릿으로 고정하고
  세부 행동(`select_pattern`, `emit_attack`)을 하위 클래스에서 오버라이드
- 학습 과제: 보스 2페이즈를 Template Method로 분리 구현
