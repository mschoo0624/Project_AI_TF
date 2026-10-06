"""Keyword router: answers frequent requests without the LLM (target < 1 s).

List requests (search, bulk assignment, release) are parsed into one PersonFilter.
Every pattern marks the part of the sentence it used; if a meaningful word is left
over, the rule does not answer (returns Unparsed) instead of silently dropping a
condition. Example: "해군 빼고 병사 보여줘" leaves "빼고" → Unparsed(["빼고"]).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

from user.app.copilot.filters import PersonFilter
from user.app.copilot.insights import DataCheckArgs, PersonSummaryArgs, RecentChangesArgs, StatusArgs
from user.app.copilot.tools import (
	BulkAssignmentArgs, MoveArgs, ReleaseArgs, SearchMembersArgs, SquadShortageArgs, TransferSquadArgs,
)

MILITARY_NUMBER_RE = re.compile(r"(?<![0-9A-Za-z])[0-9A-Za-z]{2,}(?:-[0-9A-Za-z]+)+(?![0-9A-Za-z])")
RANKS = ("이병", "일병", "상병", "병장", "하사", "중사", "상사", "원사", "소위", "중위", "대위", "소령", "중령", "대령")


@dataclass(frozen=True)
class Unparsed:
	"""규칙이 일부만 이해한 문장. words는 이해하지 못한 말이다. 다른 규칙도 쓰지 않는다."""

	words: list[str]
	question: str | None = None  # 있으면 LLM에 넘기지 않고 바로 되묻는다.


# ------------------------------------------------------------------ 문장 소비 추적

# 조건 바로 뒤에 붙는 접미사·조사: "전입자들", "1소대의", "간부들은"
SUFFIX_RE = re.compile(
	r"(?:자들|자|들|원들|원)?(?:은|는|이|가|을|를|의|에|에서|에게|도|만|과|와|으로|로|이랑|랑|하고|중에서|중에|중)?"
)
# Meaningless words - so wont be counted
FILLER = {
	"인원", "사람", "명단", "목록", "리스트", "대상", "대상자", "좀", "다", "전부", "모두", "전체", "모든", "중", "가운데",
	"올해", "금년", "현재", "지금", "혹시", "한번", "그리고", "및", "자동", "자동으로", "명", "몇", "수", "해줘", "해",
	"줘", "주세요", "줄래", "있어", "있는", "있는지", "이야", "인가", "인가요", "인지", "야", "요", "해주세요", "부탁",
	"부탁해", "시간", "대해", "대해서", "애들", "분들", "분", "것", "거", "만", "까지", "전원",
}
PARTICLE_TAIL_RE = re.compile(r"들?(?:은|는|이|가|을|를|의|에|에서|도|만|과|와|으로|로|이랑|랑|하고|중에서|중에|중)?$")


class Sentence:
	def __init__(self, text: str) -> None:
		self.text = text
		self.used = [False] * len(text)

	def _masked(self) -> str:
		return "".join(" " if used else char for char, used in zip(self.text, self.used))

	def take(self, pattern: re.Pattern[str]) -> re.Match[str] | None:
		"""아직 안 쓴 부분에서 처음 맞는 곳을 찾아 (뒤에 붙은 조사까지) 쓴 것으로 표시한다."""
		masked = self._masked()
		match = pattern.search(masked)
		if match is None or not match.group(0).strip():
			return None
		end = match.end()
		tail = SUFFIX_RE.match(masked, end)
		if tail and tail.end() > end and (tail.end() == len(masked) or not masked[tail.end()].isalnum()):
			end = tail.end()
		for index in range(match.start(), end):
			self.used[index] = True
		return match

	def leftover(self) -> list[str]:
		words = []
		for token in re.split(r"[\s,.?!~·/]+", self._masked()):
			word = PARTICLE_TAIL_RE.sub("", token) if len(token) > 1 else token
			if token and word not in FILLER and token not in FILLER and word:
				words.append(token)
		return words


# ------------------------------------------------------------------- 조건 패턴

REFERENCE_RE = re.compile(r"(?:^|\s)(?:저|그|이|위|방금|해당)\s*(?:인원|사람|분(?!대)|애|명단|목록|전입자|미편성자)|(?:^|\s)(?:이|그|저)들")
NOT_ASSIGNABLE_RE = re.compile(r"편성\s*대상\s*(?:이\s*)?아닌|대상\s*아닌|비활성")
PROSECUTION_RE = re.compile(r"고발\s*(?:검토\s*)?(?:대상|위험)?")
SHORTFALL_RE = re.compile(
	r"(?:교육|훈련)\s*(?:시간\s*)?(?:을|를|이|가)?\s*"
	r"(?:미달|미이수|못\s*채운?|안\s*채운?|부족한?|미충족|미완료|덜\s*받은?|남은)"
)
UNASSIGNED_RE = re.compile(
	# (?<!\d)(?<!\d\s): "1소대 미편성"의 "소대"는 소대 번호이므로 미편성 표현에 넣지 않는다.
	r"(?:(?:편성\s*)?(?<!\d)(?<!\d\s)(?:부대|소대|분대|소속)\s*)?(?:미편성|미배정|미지정|미할당|미소속)"
	r"|(?:(?<!\d)(?<!\d\s)(?:부대|소대|분대)\S*\s*)?(?:(?:편성|배정|배치)\s*)?"
	r"(?<!\d)(?<!\d\s)(?:편성|배정|배치|지정|할당|소속|부대|소대|분대)\S*\s*(?:안\s*된|안\s*됨|되지\s*않은|없는|없음)"
)
ASSIGNED_RE = re.compile(r"편성된|편성돼\s*있는|편성\s*인원|편성자")
PLATOON_RE = re.compile(r"(\d{1,2})\s*소대")
SQUAD_RE = re.compile(r"(\d{1,2})\s*분대")
YEAR_RE = re.compile(r"(\d)\s*년차")
BRANCH_RE = re.compile(r"해병대?|육군|해군|공군")
RANK_RE = re.compile("|".join(RANKS))
CATEGORY_RE = re.compile(r"간부|부사관|장교|병사|용사")
TRANSFER_RE = re.compile(r"전입")


def refers_to_previous(text: str) -> bool:
	"""'저 인원들', '그 사람', '위 명단'처럼 직전 답변의 명단을 가리키는지."""
	return bool(REFERENCE_RE.search(text))


# 소속, 군번, 군, 계급, 연차 등등을 추출
def parse_filter(sentence: Sentence) -> PersonFilter:
	"""문장에서 인원 조건을 뽑는다. 겹치는 표현은 더 긴 것부터 소비한다."""
	sentence.take(REFERENCE_RE)
	number = sentence.take(MILITARY_NUMBER_RE)
	not_assignable = sentence.take(NOT_ASSIGNABLE_RE) is not None
	training = "prosecution" if sentence.take(PROSECUTION_RE) else "shortfall" if sentence.take(SHORTFALL_RE) else None
	assigned = False if sentence.take(UNASSIGNED_RE) else True if sentence.take(ASSIGNED_RE) else None
	platoon = sentence.take(PLATOON_RE) # 소대
	squad = sentence.take(SQUAD_RE) # ... 계속 추출:>
	year = sentence.take(YEAR_RE)
	branch = sentence.take(BRANCH_RE)
	rank = sentence.take(RANK_RE)
	category = sentence.take(CATEGORY_RE)
	transfer = sentence.take(TRANSFER_RE) is not None
	# 군번이 없으면 문장 첫 단어가 사람 이름일 수 있다: "정태윤 편성 해제해줘", "정태윤은 편성에서 빼줘".
	# 다른 조건을 다 뽑은 뒤에 보고, 첫 단어가 이미 조건으로 쓰였으면("미지정 병사") 이름이 아니다.
	person = None
	masked = sentence._masked()
	if not number and masked[:1].strip():
		person = person_name(masked)
		if person and sentence.take(re.compile("^" + re.escape(person))):
			person = NAME_PARTICLE_RE.sub("", person) if len(person) >= 4 else person
		else:
			person = None
	category_name = category.group(0) if category else None
	return PersonFilter(
		platoon=f"{int(platoon.group(1))}소대" if platoon else None,
		squad=f"{int(squad.group(1))}분대" if squad else None,
		branch=("해병대" if branch.group(0).startswith("해병") else branch.group(0)) if branch else None,
		rank=rank.group(0) if rank else None,
		category=None if rank else ("병사" if category_name == "용사" else category_name),
		service_year=int(year.group(1)) if year and int(year.group(1)) <= 8 else None,
		assigned=assigned,
		not_assignable=not_assignable,
		transfer_only=transfer,
		training=training,
		name=number.group(0) if number else person,
	)


# --------------------------------------------------------------------- 요청 종류

RELEASE_RE = re.compile(r"해제|빼\s*줘|빼\s*주|빼라|비워|비우|제외\s*해|제외\s*시")
RELEASE_ACTION_RE = re.compile(r"(?:편성\s*(?:에서\s*)?)?(?:해제|빼\s*(?:줘|주|라)|비워|비우|제외\s*(?:해|시))\S*")
# 이름 뒤에 붙은 조사 한 글자 ("정태윤은" → "정태윤"). 2글자 이름+조사와 헷갈리지 않게 4글자 이상에서만 뗀다.
NAME_PARTICLE_RE = re.compile(r"[은는이가을를의]$")
ASSIGN_ACTION_RE = re.compile(r"(?:편성|배치|배정)\s*(?:해|하|시|할)\S*|넣어\S*|채워\S*")  # "편성 해주세요"처럼 띄어 써도 된다
# 재편성(이동): "정태윤 재편성해줘", "다른 소대로 옮겨줘", "1소대에 있으면 안 돼"
MOVE_RE = re.compile(r"재편성|재배치|재배정|옮겨|옮기|이동|다른\s*(?:분대|소대|데|곳)")
AVOID_PLATOON_RE = re.compile(r"(\d{1,2})\s*소대\S*\s*(?:있으면\s*안|있으면\s*않|말고|빼고|제외|아닌)")
OTHER_PLATOON_RE = re.compile(r"다른\s*소대")
ASK_SQUAD_WORDS = ("어디", "추천")
SEARCH_ACTION_RE = re.compile(r"보여\S*|찾아\S*|목록|명단|누구\S*|몇\s*명\S*|검색\S*|조회\S*|리스트|뽑아\S*|알려\S*")
MANY_RE = re.compile(r"미편성|미배정|[가-힣]들(?:\s|$|을|를|은|는|도|좀)|전부|모두|전체|나머지|남은|(?:^|\s)다\s")
# 첫 단어가 이 말을 포함하면 사람 이름이 아니다.
NOT_NAME_PARTS = (
	"전입", "편성", "소대", "분대", "인원", "육군", "해군", "공군", "해병", "간부", "병사", "장교", "부사관",
	"용사", "방금", "이번", "새로", "어디", "모두", "모든", "전부", "전체", "남은", "나머지", "신규", "사람", "애들",
	"교육", "고발", "보류", "연기", "이상", "최근", "오늘", "올해",
	# 시간을 뜻하는 말: 이름으로 읽으면 '작년' 검색처럼 엉뚱한 조건이 된다(이해 못 한 말로 남겨야 한다).
	"작년", "내년", "어제", "내일", "지난", "다음", "금년", "올",
)
DATA_CHECK_RE = re.compile(
	r"이상\s*(?:데이터|자료)|데이터\s*(?:점검|검사|확인|오류)|잘못된\s*(?:데이터|편성)|오류\s*데이터|이상한\s*(?:데이터|편성)|점검해"
)
CHANGES_RE = re.compile(
	r"변경\s*(?:기록|이력|내역)|수정\s*(?:기록|이력)|작업\s*(?:기록|이력)|최근\s*(?:변경|작업)|누가\s*(?:바꿨|편성|수정|해제)"
	r"|편성\s*(?:기록|이력)|감사\s*로그"
)
ADD_SQUAD_RE = re.compile(r"추가|만들|늘려|증편|신설")
PERSON_INFO_RE = re.compile(r"정보|프로필|상세|이력|요약")
STATUS_RE = re.compile(r"현황|브리핑|요약|상황")
STATUS_FOCUS = (("보류", "보류"), ("연기", "연기"), ("고발", "고발"), ("결재", "결재"), ("미편성", "미편성"), ("교육", "교육"))


def person_name(text: str) -> str | None:
	"""문장 첫 단어가 사람 이름(한글 2~5자, 테스트 데이터는 숫자 꼬리)으로 보이면 돌려준다."""
	first = text.split()[0] if text.split() else ""
	if not re.fullmatch(r"[가-힣]{2,5}\d{0,4}", first) or first in RANKS:
		return None
	if any(part in first for part in NOT_NAME_PARTS):
		return None
	return first

# 메세지 정리 및 군번 확인
def route(message: str) -> tuple[str, BaseModel] | Unparsed | None:
	"""(도구 이름, 인자) / Unparsed(이해 못 한 말) / None(규칙 대상 아님 → LLM)."""
	text = message.strip()
	number = MILITARY_NUMBER_RE.search(text)
	# 특정 요청을 우선 확인
	if DATA_CHECK_RE.search(text):
		return "check_data_issues", DataCheckArgs()
	if CHANGES_RE.search(text):
		return "show_recent_changes", RecentChangesArgs()
	if MOVE_RE.search(text) or AVOID_PLATOON_RE.search(text):
		# 한 사람을 다른 분대로 옮긴다. 이름이 없으면 라우터가 직전 답변의 한 사람으로 채운다.
		avoid = AVOID_PLATOON_RE.search(text)
		return "propose_move", MoveArgs(
			military_number=number.group(0) if number else None,
			name=None if number or refers_to_previous(text) else person_name(text),
			avoid_platoon=f"{int(avoid.group(1))}소대" if avoid else None,
			other_platoon=bool(OTHER_PLATOON_RE.search(text)),
		)
	releases = RELEASE_RE.search(text) and ("편성" in text or "분대" in text or refers_to_previous(text))
	if not releases and "분대" in text and ADD_SQUAD_RE.search(text):
		return "explain_squad_shortage", SquadShortageArgs()  # Copilot은 분대를 만들지 않는다.
	if PERSON_INFO_RE.search(text):
		if number:
			return "person_summary", PersonSummaryArgs(military_number=number.group(0))
		name = person_name(text)
		if name:
			return "person_summary", PersonSummaryArgs(name=name)
	focus = next((value for word, value in STATUS_FOCUS if word in text), None)
	if STATUS_RE.search(text) or focus in ("보류", "연기", "고발", "결재") and re.search(r"몇|얼마", text):
		return "summarize_status", StatusArgs(focus=focus)
	return _route_list(text, number, bool(releases))


def _route_list(text: str, number: re.Match[str] | None, releases: bool) -> tuple[str, BaseModel] | Unparsed | None:
	sentence = Sentence(text)
	if releases:
		# "편성 해제해"는 "편성해"를 포함하므로 편성보다 먼저 본다.
		sentence.take(RELEASE_ACTION_RE)
		tool = "propose_release"
	elif ASSIGN_ACTION_RE.search(text) or any(word in text for word in ASK_SQUAD_WORDS):
		name = None if number or refers_to_previous(text) else person_name(text)
		if number or name or not MANY_RE.search(text):
			# 한 사람: "황성민 어디에 편성해?", "26-0001 편성해줘", "어디에 편성해?"(최근 전입자)
			return "recommend_squad_for_transfer", TransferSquadArgs(
				military_number=number.group(0) if number else None, name=name,
			)
		# 여러 명: "미편성 인원들 편성해줘", "해군 병사 전입자 다 배치해줘"
		sentence.take(ASSIGN_ACTION_RE)
		tool = "propose_bulk_assignment"
	elif sentence.take(SEARCH_ACTION_RE) or SHORTFALL_RE.search(text) or PROSECUTION_RE.search(text):
		tool = "search_members"
	else:
		return None

	condition = parse_filter(sentence)
	leftover = sentence.leftover()
	if leftover:
		# 숫자 없는 "소대"/"분대"는 LLM도 아무 소대나 고를 수 있으니 바로 되묻는다.
		unit = next((unit for unit in ("소대", "분대") if any(PARTICLE_TAIL_RE.sub("", word) == unit for word in leftover)), None)
		if unit:
			return Unparsed(leftover, f"몇 {unit}인지 숫자로 함께 말씀해 주세요. 예: \"1소대{' 3분대' if unit == '분대' else ''} 인원 보여줘\"")
		return Unparsed(leftover)
	fields = condition.model_dump(exclude_defaults=True)
	if tool == "propose_release":
		fields.pop("assigned", None)  # 해제 대상은 항상 편성된 인원
		return tool, ReleaseArgs(**fields)
	if tool == "propose_bulk_assignment":
		fields.pop("assigned", None)  # 편성 대상은 항상 미편성 인원
		return tool, BulkAssignmentArgs(**fields)
	if condition.is_empty():
		return None
	return tool, SearchMembersArgs(**fields)
