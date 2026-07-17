"""Generate canonical byte-stable English and Korean release catalogs."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

type CopyPair = tuple[str, str]
type StageCopy = tuple[str, int, str, str, str, str]

OUTPUT_PATHS = (
    Path("windsprig/content/strings.en.json"),
    Path("windsprig/content/strings.ko.json"),
)

STAGE_COPY: tuple[StageCopy, ...] = (
    (
        "world_1",
        1,
        "First Flight",
        "첫 비행",
        "Ride gentle gusts over the waking meadow.",
        "깨어나는 들판의 잔잔한 돌풍을 타세요.",
    ),
    (
        "world_1",
        2,
        "Millstream Run",
        "물레바람 질주",
        "Cross turning mills and open a bramble shortcut.",
        "회전하는 풍차를 건너 덩굴 지름길을 여세요.",
    ),
    (
        "world_1",
        3,
        "Bramble Updraft",
        "가시덤불 상승풍",
        "Break thorn gates while chaining rising gusts.",
        "상승풍을 이어 타며 가시 문을 부수세요.",
    ),
    (
        "world_1",
        4,
        "Valewind Gauntlet",
        "계곡바람 시련",
        "Master gust timing across the high vale.",
        "높은 계곡에서 돌풍 타이밍을 완성하세요.",
    ),
    (
        "world_1",
        5,
        "Rootjaw Burrow",
        "뿌리턱 굴",
        "Follow the trembling roots to Rootjaw's den.",
        "떨리는 뿌리를 따라 뿌리턱의 굴로 가세요.",
    ),
    (
        "world_2",
        1,
        "Kilnwalk",
        "가마길",
        "Learn the rhythm of conveyors and cooling vents.",
        "컨베이어와 냉각 통풍구의 리듬을 익히세요.",
    ),
    (
        "world_2",
        2,
        "Conveyor Crossing",
        "컨베이어 교차로",
        "Change lanes before the furnace gaps open.",
        "용광로 틈이 열리기 전에 선로를 바꾸세요.",
    ),
    (
        "world_2",
        3,
        "Shutter Furnace",
        "차단문 용광로",
        "Read timed shutters through waves of heat.",
        "열기 파동 사이에서 차단문 시간을 읽으세요.",
    ),
    (
        "world_2",
        4,
        "Molten Clockwork",
        "용융 태엽장치",
        "Chain every factory mechanism without stopping.",
        "멈추지 말고 모든 공장 장치를 이어 가세요.",
    ),
    (
        "world_2",
        5,
        "Crucible Crab",
        "도가니 게",
        "Cool the armored keeper of the molten lanes.",
        "용융 선로의 갑옷 수호자를 식히세요.",
    ),
    (
        "world_3",
        1,
        "Pod Pools",
        "부유열매 웅덩이",
        "Use buoyant pods to cross the moonlit pools.",
        "부유열매로 달빛 웅덩이를 건너세요.",
    ),
    (
        "world_3",
        2,
        "Current Choir",
        "해류 합창",
        "Let aligned currents carry each echo onward.",
        "정렬된 해류에 메아리를 실어 보내세요.",
    ),
    (
        "world_3",
        3,
        "Waterfall Vault",
        "폭포 금고",
        "Climb behind falling water to find the upper route.",
        "떨어지는 물 뒤로 올라가 위쪽 길을 찾으세요.",
    ),
    (
        "world_3",
        4,
        "Mooncurrent Maze",
        "달해류 미로",
        "Reverse currents and navigate the deepest grotto.",
        "해류를 뒤집어 가장 깊은 동굴을 통과하세요.",
    ),
    (
        "world_3",
        5,
        "Luma Eel",
        "루마 장어",
        "Track the true light through Luma Eel's decoys.",
        "루마 장어의 미끼 빛 사이에서 진짜 빛을 찾으세요.",
    ),
    (
        "world_4",
        1,
        "Live Line",
        "활선",
        "Ride the first rail and ground its charge safely.",
        "첫 전기 레일을 타고 안전하게 접지하세요.",
    ),
    (
        "world_4",
        2,
        "Conductor Crossing",
        "도체 교차로",
        "Link conductors to open a path through the storm.",
        "도체를 연결해 폭풍 속 길을 여세요.",
    ),
    (
        "world_4",
        3,
        "Turntable Tempest",
        "회전탑 폭풍",
        "Transfer between rotating towers at full speed.",
        "최고 속도로 회전탑 사이를 갈아타세요.",
    ),
    (
        "world_4",
        4,
        "Observatory Ascent",
        "관측소 등반",
        "Master rails, conductors, and tower rotation.",
        "레일과 도체와 회전탑을 모두 정복하세요.",
    ),
    (
        "world_4",
        5,
        "Volt Roc",
        "볼트 로크",
        "Ground the sky hunter before its chain lightning lands.",
        "연쇄 번개가 닿기 전에 하늘 사냥꾼을 접지하세요.",
    ),
    (
        "world_5",
        1,
        "Mirror Seed",
        "거울씨앗",
        "Turn one beam with a living mirror.",
        "살아 있는 거울로 한 줄기 빛을 돌리세요.",
    ),
    (
        "world_5",
        2,
        "Chromatic Canopy",
        "색채 수관",
        "Match beam colors across the crystal canopy.",
        "수정 수관에서 빛줄기 색을 맞추세요.",
    ),
    (
        "world_5",
        3,
        "Gravity Petal",
        "중력 꽃잎",
        "Bloom new gravity paths through the garden.",
        "정원에 새로운 중력 길을 피우세요.",
    ),
    (
        "world_5",
        4,
        "Refraction Labyrinth",
        "굴절 미궁",
        "Reflect, recolor, and invert the longest route.",
        "가장 긴 길을 반사하고 채색하고 뒤집으세요.",
    ),
    (
        "world_5",
        5,
        "Prism Warden",
        "프리즘 수호자",
        "Find the real Warden among mirrored clones.",
        "거울 분신 사이에서 진짜 수호자를 찾으세요.",
    ),
    (
        "world_6",
        1,
        "Hushed Court",
        "고요한 뜰",
        "Carry motion through the first silence field.",
        "첫 침묵장을 지나 움직임을 이어 가세요.",
    ),
    (
        "world_6",
        2,
        "Shattered Orbit",
        "부서진 궤도",
        "Remix gravity, rails, and silence in open sky.",
        "열린 하늘에서 중력과 레일과 침묵을 엮으세요.",
    ),
    (
        "world_6",
        3,
        "Locked Echoes",
        "잠긴 메아리",
        "Recover each ability after the crown locks it away.",
        "왕관이 잠근 능력을 하나씩 되찾으세요.",
    ),
    (
        "world_6",
        4,
        "Crown of Motion",
        "움직임의 왕관",
        "Prove mastery of all six islands in one ascent.",
        "한 번의 등반으로 여섯 섬의 숙련을 증명하세요.",
    ),
    (
        "world_6",
        5,
        "The Stillness",
        "정지",
        "Release every learned motion against the final silence.",
        "배운 모든 움직임을 마지막 침묵에 풀어놓으세요.",
    ),
)

ROWS: dict[str, CopyPair] = {
    "game.title": ("Windsprig: Echoes of the Gale", "바람싹: 질풍의 메아리"),
    "action.start": ("Start", "시작"),
    "action.continue": ("Continue", "계속"),
    "action.back": ("Back", "뒤로"),
    "action.confirm": ("Confirm", "확인"),
    "action.cancel": ("Cancel", "취소"),
    "action.next_stage": ("Next Stage", "다음 스테이지"),
    "action.replay": ("Replay", "다시 하기"),
    "action.world_map": ("World Map", "월드맵"),
    "action.retry_checkpoint": ("Retry Checkpoint", "체크포인트 재도전"),
    "action.retry_stage": ("Retry Stage", "스테이지 재도전"),
    "action.create_profile": ("Create Profile", "프로필 만들기"),
    "action.delete_profile": ("Hold to Delete", "길게 눌러 삭제"),
    "screen.profile.title": ("Choose a Profile", "프로필 선택"),
    "screen.map.title": ("Sky Island Map", "하늘섬 지도"),
    "screen.results.title": ("Stage Clear", "스테이지 완료"),
    "screen.settings.title": ("Settings", "설정"),
    "screen.controls.title": ("Controls & Accessibility", "조작 및 접근성"),
    "screen.credits.title": ("Credits", "제작진"),
    "screen.pause.title": ("Paused", "일시 정지"),
    "screen.defeat.title": ("The wind rests", "바람이 잠시 쉽니다"),
    "profile.empty": ("New profile", "새 프로필"),
    "profile.completion": ("Completion {percent}%", "달성도 {percent}%"),
    "profile.motes": ("Wind Motes {found} / 90", "바람 티끌 {found} / 90"),
    "profile.play_time": ("Play time {time}", "플레이 시간 {time}"),
    "profile.no_stage": ("No stage played", "플레이 기록 없음"),
    "map.locked": ("Locked", "잠김"),
    "map.available": ("Available", "입장 가능"),
    "map.cleared": ("Cleared", "완료"),
    "map.best": ("Best {time}", "최고 {time}"),
    "results.time": ("Time {time}", "기록 {time}"),
    "results.best": ("Best {time}", "최고 {time}"),
    "results.new_best": ("New best! {delta} faster", "신기록! {delta} 단축"),
    "results.first_clear": ("First clear", "첫 완료"),
    "results.motes": ("Wind Motes", "바람 티끌"),
    "results.abilities": ("Echoes discovered", "발견한 메아리"),
    "results.unlocks": ("Unlocked", "해금"),
    "save.saved": ("Saved", "저장됨"),
    "save.saving": ("Saving", "저장 중"),
    "save.failed": ("Save failed — retry", "저장 실패 — 다시 시도"),
    "audio.muted_failure": ("Audio unavailable — muted", "오디오를 사용할 수 없어 음소거됨"),
    "settings.master": ("Master volume", "전체 음량"),
    "settings.music": ("Music volume", "음악 음량"),
    "settings.sfx": ("SFX volume", "효과음 음량"),
    "settings.mute": ("Mute", "음소거"),
    "settings.fullscreen": ("Fullscreen", "전체 화면"),
    "settings.integer_scale": ("Integer scaling", "정수 배율"),
    "settings.shake": ("Screen shake", "화면 흔들림"),
    "settings.reduced_motion": ("Reduced motion", "동작 줄이기"),
    "settings.draw_toggle": ("Draw action: toggle", "끌어당기기: 전환"),
    "settings.draw_hold": ("Draw action: hold", "끌어당기기: 누르기"),
    "settings.guard_toggle": ("Guard: toggle", "가드: 전환"),
    "settings.guard_hold": ("Guard: hold", "가드: 누르기"),
    "settings.language": ("Language", "언어"),
    "settings.english": ("English", "영어"),
    "settings.korean": ("Korean", "한국어"),
    "settings.controls": ("Control reference", "조작 안내"),
    "settings.keyboard_p1": ("Keyboard layout 1", "키보드 배치 1"),
    "settings.keyboard_p2": ("Keyboard layout 2", "키보드 배치 2"),
    "settings.gamepad": ("Gamepad mapping guide", "게임패드 배치 안내"),
    "hud.hp": ("HP {current}/{maximum}", "체력 {current}/{maximum}"),
    "hud.lives": ("Lives {count}", "목숨 {count}"),
    "hud.motes": ("Motes {found}/3", "티끌 {found}/3"),
    "hud.hover": ("Hover", "활공"),
    "hud.captured": ("Held echo: {ability}", "보유 메아리: {ability}"),
    "hud.boss_incoming": ("Incoming attack", "준비 중"),
    "hud.none": ("None", "없음"),
    "hud.gather": ("Gather {seconds}", "집결 {seconds}"),
    "status.invulnerable": ("Invulnerable", "무적"),
    "status.guard": ("Guard", "가드"),
    "status.dodge_ready": ("Dodge ready", "회피 준비"),
    "status.boss_phase": ("Phase {phase}/3", "단계 {phase}/3"),
    "ability.bloomblade.name": ("Bloomblade", "꽃날"),
    "ability.cinder.name": ("Cinder", "불씨"),
    "ability.voltsong.name": ("Voltsong", "전율노래"),
    "ability.galehook.name": ("Galehook", "질풍갈고리"),
    "ability.stoneheart.name": ("Stoneheart", "돌심장"),
    "ability.tempest.name": ("Tempest", "대폭풍"),
    "world.world_1.name": ("Sunleaf Vale", "햇잎 골짜기"),
    "world.world_1.identity": ("Warm meadows and windmills", "따뜻한 초원과 풍차"),
    "world.world_2.name": ("Emberglass Works", "잿불유리 공방"),
    "world.world_2.identity": ("A glowing kiln city", "빛나는 가마 도시"),
    "world.world_3.name": ("Tidemoon Grotto", "밀물달 동굴"),
    "world.world_3.identity": ("Moonlit water caverns", "달빛 물동굴"),
    "world.world_4.name": ("Thunderrail Heights", "천둥레일 고지"),
    "world.world_4.identity": ("A storm observatory", "폭풍 관측소"),
    "world.world_5.name": ("Prismbloom Dream", "프리즘꽃 꿈"),
    "world.world_5.identity": ("A crystalline living garden", "수정으로 살아 있는 정원"),
    "world.world_6.name": ("Stillstar Crown", "고요별 왕관"),
    "world.world_6.identity": ("A fractured sky palace", "부서진 하늘 궁전"),
    "mechanic.gust_lift.name": ("Gust lifts", "돌풍 상승기류"),
    "mechanic.breakable.name": ("Breakables", "파괴물"),
    "mechanic.conveyor.name": ("Conveyors", "컨베이어"),
    "mechanic.heat_vent.name": ("Heat vents", "열기 통풍구"),
    "mechanic.timed_shutter.name": ("Timed shutters", "시간 차단문"),
    "mechanic.current.name": ("Currents", "해류"),
    "mechanic.buoyant_pod.name": ("Buoyant pods", "부유열매"),
    "mechanic.falling_water.name": ("Falling water", "낙수"),
    "mechanic.rail.name": ("Storm rails", "폭풍 레일"),
    "mechanic.conductor.name": ("Conductors", "도체"),
    "mechanic.rotating_tower.name": ("Rotating towers", "회전탑"),
    "mechanic.mirror.name": ("Mirrors", "거울"),
    "mechanic.color_beam.name": ("Color beams", "색광선"),
    "mechanic.gravity_bloom.name": ("Gravity blooms", "중력꽃"),
    "mechanic.silence_field.name": ("Silence fields", "침묵장"),
    "mechanic.ability_lock.name": ("Ability locks", "능력 잠금"),
    "boss.rootjaw.name": ("Rootjaw", "뿌리턱"),
    "boss.crucible_crab.name": ("Crucible Crab", "도가니 게"),
    "boss.luma_eel.name": ("Luma Eel", "루마 장어"),
    "boss.volt_roc.name": ("Volt Roc", "볼트 로크"),
    "boss.prism_warden.name": ("Prism Warden", "프리즘 수호자"),
    "boss.the_stillness.name": ("The Stillness", "정지"),
    "enemy.breezeling.name": ("Breezeling", "산들씨"),
    "enemy.bramblekin.name": ("Bramblekin", "덤불족"),
    "enemy.millmite.name": ("Millmite", "풍차진드기"),
    "enemy.cinderling.name": ("Cinderling", "불씨족"),
    "enemy.slagroller.name": ("Slag Roller", "광재굴림이"),
    "enemy.shutterimp.name": ("Shutter Imp", "차단도깨비"),
    "enemy.bubblefin.name": ("Bubblefin", "거품지느러미"),
    "enemy.shellskiff.name": ("Shell Skiff", "조개배"),
    "enemy.moonjelly.name": ("Moonjelly", "달해파리"),
    "enemy.coilbird.name": ("Coilbird", "코일새"),
    "enemy.railrunner.name": ("Rail Runner", "레일달림이"),
    "enemy.stormlens.name": ("Storm Lens", "폭풍눈"),
    "enemy.petalisk.name": ("Petalisk", "꽃잎뱀"),
    "enemy.mirrormite.name": ("Mirror Mite", "거울진드기"),
    "enemy.gravitybud.name": ("Gravity Bud", "중력봉오리"),
    "enemy.hushshade.name": ("Hush Shade", "고요그늘"),
    "enemy.lockwarden.name": ("Lock Warden", "잠금수호자"),
    "enemy.riftling.name": ("Riftling", "균열씨"),
    "debug.english_only": ("English diagnostic", "English diagnostic"),
}

REWARD_COPY: dict[str, CopyPair] = {
    "gallery.sunleaf": ("Sunleaf gallery", "햇잎 갤러리"),
    "palette.mint": ("Mint palette", "민트 팔레트"),
    "challenge.sunleaf": ("Sunleaf challenge", "햇잎 도전"),
    "gallery.emberglass": ("Emberglass gallery", "잿불유리 갤러리"),
    "palette.ember": ("Ember palette", "잿불 팔레트"),
    "challenge.emberglass": ("Emberglass challenge", "잿불유리 도전"),
    "gallery.tidemoon": ("Tidemoon gallery", "밀물달 갤러리"),
    "palette.moon": ("Moon palette", "달빛 팔레트"),
    "challenge.tidemoon": ("Tidemoon challenge", "밀물달 도전"),
    "gallery.thunderrail": ("Thunderrail gallery", "천둥레일 갤러리"),
    "palette.storm": ("Storm palette", "폭풍 팔레트"),
    "challenge.thunderrail": ("Thunderrail challenge", "천둥레일 도전"),
    "gallery.prismbloom": ("Prismbloom gallery", "프리즘꽃 갤러리"),
    "palette.prism": ("Prism palette", "프리즘 팔레트"),
    "challenge.prismbloom": ("Prismbloom challenge", "프리즘꽃 도전"),
    "gallery.stillstar": ("Stillstar gallery", "고요별 갤러리"),
    "palette.stillstar": ("Stillstar palette", "고요별 팔레트"),
    "challenge.stillstar": ("Stillstar challenge", "고요별 도전"),
}


def build() -> dict[str, dict[str, str]]:
    """Build complete sorted language tables from the reviewed copy records."""

    rows = dict(ROWS)
    for world, index, en_name, ko_name, en_intro, ko_intro in STAGE_COPY:
        rows[f"stage.{world}.{index:02d}.name"] = (en_name, ko_name)
        rows[f"stage.{world}.{index:02d}.intro"] = (en_intro, ko_intro)
    for reward_id, pair in REWARD_COPY.items():
        rows[f"reward.{reward_id}.name"] = pair
    return {
        "en": {key: pair[0] for key, pair in sorted(rows.items())},
        "ko": {key: pair[1] for key, pair in sorted(rows.items())},
    }


def _serialize(payload: Mapping[str, str]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def canonical_outputs() -> dict[Path, str]:
    """Serialize every locale fully before publication can begin."""

    catalogs = build()
    return {
        OUTPUT_PATHS[0]: _serialize(catalogs["en"]),
        OUTPUT_PATHS[1]: _serialize(catalogs["ko"]),
    }


def check_outputs(root: Path = Path(".")) -> tuple[Path, ...]:
    """Return every stale locale path without changing the filesystem."""

    stale = [
        relative_path
        for relative_path, canonical in canonical_outputs().items()
        if not (root / relative_path).exists() or (root / relative_path).read_bytes() != canonical.encode("utf-8")
    ]
    return tuple(sorted(stale, key=lambda path: path.as_posix()))


def _temporary_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _replace(source: str | Path, destination: str | Path) -> None:
    os.replace(source, destination)


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    temporary = _temporary_file(path, previous)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_outputs(root: Path = Path(".")) -> None:
    """Transactionally publish fully serialized locale files."""

    documents = canonical_outputs()
    destinations = {relative: root / relative for relative in documents}
    previous = {
        relative: destination.read_bytes() if destination.exists() else None
        for relative, destination in destinations.items()
    }
    temporary: dict[Path, Path] = {}
    try:
        for relative, canonical in documents.items():
            temporary[relative] = _temporary_file(destinations[relative], canonical.encode("utf-8"))
        published: list[Path] = []
        try:
            for relative in documents:
                _replace(temporary[relative], destinations[relative])
                published.append(relative)
        except BaseException:
            for relative in reversed(published):
                _restore(destinations[relative], previous[relative])
            raise
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None, *, root: Path = Path(".")) -> int:
    """Generate release locale bytes or verify them without writing."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        stale = check_outputs(root)
        if stale:
            print("STALE: " + ", ".join(path.as_posix() for path in stale))
            return 1
    else:
        write_outputs(root)
    print(f"locales: {len(build()['en'])} keys in en/ko")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
