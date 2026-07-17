# Command 패턴

- 위치: `input/commands.py`, `input/devices.py`
- 목적: 디바이스 입력을 게임 의도 명령으로 변환
- 장점: 키보드/패드 변경이 gameplay 시스템에 전파되지 않음
- 예시: `MoveCommand`, `DrawStartCommand`, `AbilityUseCommand`
- 흐름: `DrawStartCommand`가 메아리 포획을 시작하고 `AbilityUseCommand`가 조율한 에코 능력을 발동함
