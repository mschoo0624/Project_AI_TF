"""Rebuild the reviewed rule catalog from explicit conditions, never from an LLM."""
import hashlib
import json
from pathlib import Path
import pdfplumber
from backend.classifier_agent.extraction import extraction_dependencies

BASE = Path(__file__).parent


def leaf(id, label, op, fields, **kwargs):
    return dict(id=id, label=label, op=op, fields=fields, **kwargs)


def group(id, label, op, *children):
    return dict(id=id, label=label, op=op, children=list(children))


def present(key, label=None): return leaf(key, label or key, 'present', [key])
def eq(key, value, label): return leaf(key, label, 'equals', [key], value=value)
def enum(key, accepted, label, rejected=()): return leaf(key, label, 'enum', [key], accepted=accepted, rejected=list(rejected))
def manual(id, label, fields=()): return leaf(id, label, 'manual', list(fields))
def overlap(start, end): return leaf(start+'_overlap', '사유 기간과 훈련기간의 중복(양 끝 날짜 포함)', 'overlap', [start, end, 'context.training_start', 'context.training_end'])
def window(key, before, after, label): return leaf(key+'_window', label, 'window', [key, 'context.training_start', 'context.training_end'], before=before, after=after)


def references(rules):
    used = set()
    for rule in rules:
        used.update(k for k in rule.get('fields', []) + rule.get('supporting_fields', []) if not k.startswith('context.'))
        used.update(references(rule.get('children', [])))
    return used


def build():
    common = json.loads((BASE/'common_fields.json').read_text(encoding='utf-8'))
    sources = json.loads((BASE/'sources.json').read_text(encoding='utf-8'))['sources']
    pages = {}
    for source in sources:
        path = BASE/source['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
        with pdfplumber.open(path) as pdf:
            pages[source['table']] = [p.extract_text() for p in pdf.pages]
    types = {}
    for name in ('statutory_hold', 'policy_hold', 'postponement'):
        data = json.loads((BASE/f'{name}.json').read_text(encoding='utf-8'))
        table = data['source_table']
        source = next(s for s in sources if s['table'] == table)
        for item in data['types']:
            citation = {**source, 'page': item['source_page'], 'item': item['label'],
                        'provision': f'예비군 교육훈련 훈령 제{24 if table == 7 else 23}조 관련 별표 {table}',
                        'page_text': pages[table][item['source_page']-1],
                        'source_url': f'/verification-sources/{table}#page={item["source_page"]}'}
            types[item['id']] = {'label': item['label'], 'citation': citation,
                'coverage': 'manual',
                'training_scope': '신청 훈련종류에 대한 별표의 참가/보류 및 횟수 범위를 별도로 확인. 일괄 면제로 취급하지 않음.',
                'checks': [manual('specific_criteria', item['extraction_notes'] + ' — 원문 조건·예외를 담당자가 확인해야 합니다.',
                    list(dict.fromkeys(k for g in item['field_groups'] if g != 'identity' for k in common['field_groups'][g])))],
                'document_options': item.get('source_document_options', [])}

    def setrule(key, *checks, coverage='structured'):
        types[key]['checks'] = list(checks)
        types[key]['coverage'] = coverage

    current = eq('current_employment', True, '현재 재직 근거')
    employer = present('employer', '소속 기관 근거')
    for key, titles in {
        'police': ['경찰관', '순경', '경장', '경사', '경위', '경감', '경정', '총경', '경무관', '치안감', '치안정감', '치안총감'],
        'firefighter': ['소방관', '소방사', '소방교', '소방장', '소방위', '소방경', '소방령', '소방정'],
        'correction': ['교도관', '교정직 교도관', '기술·보건 위생 관리운영 전문 경력직 교도관'],
    }.items():
        setrule('statutory.'+key, employer, current, enum('job_title', titles, '법규보류 대상 직종의 명시적 근거'))
    setrule('statutory.assembly', current, enum('job_title', ['국회의원'], '국회의원 재직'),
            manual('assembly_scope', '2015.12.31부터 훈련대상에 포함된 예외: 동원/훈련 구분 확인'), coverage='partial')
    setrule('policy.police_student', enum('school_kind', ['경찰학교'], '경찰학교'),
            enum('academic_status', ['재학', '재학중', '재학 중'], '재학 상태', ['휴학', '휴학중', '졸업', '제적']))
    setrule('policy.judge_prosecutor', current, enum('job_title', ['판사', '검사', '현직판사', '법관'], '현직 판사 또는 검사'))
    setrule('policy.basic_livelihood', enum('designation_kind', ['기초생활수급자', '기초생활 수급자'], '기초생활수급 등록'),
            eq('context.registration_current', True, '현재 등록 유효 여부(공적 조회)'))
    setrule('policy.school_student',
            enum('academic_status', ['재학', '재학중', '재학 중'], '재학 중', ['휴학', '휴학중', '졸업', '제적']),
            enum('school_kind', ['중학교', '고등학교', '대학교', '대학', '대학원', '산업대학', '교육대학', '전문대학', '기능대학'], '학교 종류'),
            eq('context.school_recognized', True, '법령에 따른 인정 학교 여부(공적 조회)'),
            eq('excess_semester', False, '표준 재학기간 이내'),
            eq('thesis_only', False, '논문과정만 등록한 경우 제외'),
            enum('study_mode', ['출석', '출석수업', '대면', '통학'], '원격·방송·통신 과정 제외', ['원격', '사이버', '방송통신', '통신']),
            manual('student_exceptions', '기능대학 학위과정·재입학/편입/심화과정 및 별도 공문 예외 확인', ['degree_course', 'study_stage']), coverage='partial')
    setrule('policy.school_teacher', employer, current,
            enum('job_title', ['교사', '교원', '기간제 교사', '기간제 교원', '전문상담교사', '특수교육순회교사'], '교사 직위'),
            manual('teacher_exceptions', '학교 인가, 평생교육시설 제외, 기간제·상담·순회교사 6개월 이상 재직 조건 확인', ['school_kind', 'accreditation', 'employment_kind', 'employment_start']), coverage='partial')
    setrule('policy.ship_crew', present('vessel_name', '선박명'), present('crew_role', '승선 직책'),
            manual('tonnage_document', '25톤 이상/이하 증명 구분과 정확히 25톤인 경우 해석 확인', ['vessel_tonnage', 'document_title', 'onboard_start', 'onboard_end']), coverage='partial')

    relatives_death = ['부', '모', '부친', '모친', '아버지', '어머니', '배우자', '자녀', '아들', '딸', '조부', '조모', '친조부', '친조모', '외조부', '외조모', '증조부', '증조모', '외증조부', '외증조모', '손자', '손녀', '배우자의 부', '배우자의 모', '장인', '장모', '시부', '시모', '형', '동생', '누나', '오빠', '언니', '형제자매', '백부', '백모', '숙부', '숙모', '고모', '고모부', '이모', '이모부', '외숙부', '외숙모']
    death = group('death', '허용 가족 사망 및 7일 기간', 'all',
        enum('relationship', relatives_death, '사망 허용 관계(미등록 표현은 검토)'),
        present('relationship_path', '관계증명 자료'),
        window('death_date', 0, 6, '사망일을 1일로 포함한 7일과 소집기간 중복'),
        eq('context.death_document_confirmed', True, '사망확인서 제출 확인'))
    critical = group('critical', '직계가족 등 위독·대체 간호자 없음', 'all',
        enum('relationship', ['부', '모', '부친', '모친', '자녀', '아들', '딸', '조부', '조모', '외조부', '외조모', '장인', '장모', '시부', '시모'], '위독 허용 관계'),
        enum('critical_condition', ['위독', '위독 상태'], '위독 소견'),
        eq('other_caregiver_available', False, '본인 외 간호 가능 가족 없음'),
        overlap('care_start', 'care_end'), eq('context.medical_document_confirmed', True, '의료기관 진단서 확인'))
    setrule('postponement.family', group('family_reason', '위독 또는 사망(대체 요건)', 'any', death, critical))
    setrule('postponement.disaster', present('disaster_kind', '재난 종류'), present('damage_details', '피해 사실'),
        overlap('recovery_start', 'recovery_end'), eq('context.recovery_required', True, '신청자 수습 필요 확인'),
        leaf('application_after_disaster', '재난 발생 전 신청은 제외', 'not_after', ['disaster_date', 'context.application_date']),
        eq('context.administrative_disaster_document', True, '행정관서 사실확인서 확인'))
    for key in ('statutory.overseas', 'postponement.overseas'):
        setrule(key, overlap('departure_date', 'return_date'),
                eq('context.immigration_records_confirmed', True, '공적 출입국 기록과 실제 체류기간 확인'),
                manual('overseas_scope', '미귀국의 종료일·예정 출국의 사후 확인 및 훈련종류별 적용 범위 검토', ['travel_status']), coverage='partial')
    setrule('postponement.exam', present('exam_name', '응시 시험'),
            group('exam_period', '일반 시험 또는 단계별 시험', 'any', overlap('registration_date', 'exam_date'),
                  manual('multi_stage_exam', '다단계 시험 합격/발표 대기 및 최초 부과일 기준 다음 시험 6개월 제한은 담당자가 원본으로 확인', ['exam_stage'])),
            leaf('exam_limit', '병무청 포함 통산 시험 연기 6회 미만', 'less_than', ['context.exam_lifetime_count'], limit=6),
            eq('context.exam_document_confirmed', True, '시험일·응시 증빙 확인(필요 시 시행기관 조회)'), coverage='partial')
    setrule('postponement.distance_attendance',
            enum('study_mode', ['방송통신', '원격', '사이버', '통신', '방송'], '방송통신 또는 원격 교육'),
            overlap('event_start', 'event_end'), eq('context.attendance_schedule_confirmed', True, '출석수업 또는 시험 일정의 증빙 확인'))
    own_wedding = group('own_wedding', '본인 결혼', 'all', enum('event_kind', ['본인 결혼', '본인 결혼식'], '본인 결혼 행사'), leaf('wedding_window', '소집일자 기준 본인 결혼일 전후 14일', 'point_window', ['event_date', 'context.training_start'], days=14))
    childbirth = group('spouse_birth', '배우자 출산', 'all', eq('context.spouse_birth_confirmed', True, '배우자 출산 관계·증빙 확인'),
        group('birth_day', '실제 또는 예정 출산일 전후 30일', 'any', window('birth_date', 30, 30, '출산일 전후 30일'), window('expected_birth_date', 30, 30, '출산예정일 전후 30일')))
    leave = group('parental_leave', '육아휴직', 'all', overlap('parental_leave_start', 'parental_leave_end'), eq('context.parental_leave_confirmed', True, '육아휴직 증빙 확인'))
    setrule('postponement.family_event', group('event_reason', '경조사·출산·육아휴직의 대체 요건', 'any', own_wedding, childbirth, leave,
        manual('other_family_event', '형제자매 결혼·부모/처부모 회갑 등 관계와 해당일 검토', ['event_kind', 'relationship', 'event_date'])), coverage='partial')
    setrule('postponement.work', leaf('work_limit', '병무청 포함 통산 주요업무 연기 6회 미만', 'less_than', ['context.work_lifetime_count'], limit=6),
        manual('work_branches', '합숙교육 전후 1일·회의·대체불가 업무·국제/전국대회 확정·기타 부득이한 사유별 기간과 증빙 확인', ['work_description', 'work_start', 'work_end', 'event_kind', 'event_participation', 'event_start', 'event_end']), coverage='partial')
    setrule('postponement.agriculture', leaf('agriculture_limit', '해당 연도 농어업 연기 2회 미만', 'less_than', ['context.agriculture_annual_count'], limit=2),
        overlap('busy_start', 'busy_end'), eq('context.successor_farmer_confirmed', True, '후계농어업인·후계경영인 자격 증빙 확인'),
        eq('context.agricultural_impact_confirmed', True, '농번기·성어기 참석 시 막대한 생업 지장 확인'))
    setrule('postponement.other', manual('other_branch', '대체역 신청 접수~결정 기간 또는 군동원업체 필수요원 심사와 별도 업무지시 확인', ['receipt_date', 'decision_date', 'application_status', 'designation_status']), coverage='manual')

    # Employer/duty recognition is an external fact, never inferred from an institution name.
    jobs = {
        'statutory.military_civilian': (['군무원'], '군부대 근무 확인'),
        'statutory.foreign_forces_employee': (['종업원', '직원'], '주한외국군부대 고용 확인'),
        'statutory.navigation_aid': (['항로표지 공무원', '항로표지정비 공무원'], '등대·항로표지용 선박 또는 항로표지정비 해당 업무 확인'),
        'statutory.aircraft_maintenance': (['항공기 정비사', '항공교통관제사', '항공무선표지소 근무요원'], '국내 항공사 소속 정비업체(하청·계약 포함) 등 적용 범위 확인'),
        'statutory.coastal_radio': (['통신사', '정비사'], '해안무선국 근무 확인'),
        'statutory.rail_technical': (['기관사', '차량관리원', '장비관리원', '시설관리원', '전기원'], '철도 해당 직무 근무 확인'),
        'statutory.metro_technical': (['기관사', '보선원', '철도토목원'], '도시·광역철도의 승무사무소/시설사업소/철도토목사무소 근무 확인'),
        'statutory.foreign_news': (['공무원'], '외교부 외신담당 공무원 확인'),
        'policy.postal': (['우편집배원', '우편물 배달원', '집배원'], '우체국 일반·상시 계약 집배원으로 배달 업무 확인'),
        'policy.presidential': (['수행비서', '전문통역요원', '경호요원'], '대통령실 해당 수행·통역·경호 업무 확인'),
        'policy.immigration': (['출입국관리직'], '출입국심사·선박검색·외국인보호·체류관리 업무 확인'),
        'policy.juvenile_protection': (['보호직 공무원'], '소년원 또는 소년분류심사원 근무 확인'),
        'policy.nis': (['정보수사요원', '정보수사 요원'], '국가정보원 해당 직무 확인'),
        'policy.ground_handling': (['항공기 지상조업', '항공기 장비정비사', '지상조업원', '장비정비사'], '항공사(하청·계약 포함) 항공기 유도·견인·전원·급유·지원장비 업무 확인'),
        'policy.rail_staff': (['역무원', '부기관사', '열차운용원', '차장'], '역무/수송 담당 또는 운전취급·신호기 조작 등 해당 직무 확인'),
        'policy.rail_police': (['철도 특별사법경찰관', '철도특별사법경찰관'], '철도 특별사법경찰관 지위 확인'),
        'policy.miner': (['광부'], '채탄·일반광업소 갱내 종사 확인, 간접부요원 제외'),
        'policy.urban_rail_staff': (['관제사', '사령원', '역무원', '통신원', '설비원', '건축원', '신호원', '전기원', '차장', '검수원'], '도시·광역철도 해당 직무 확인'),
        'policy.defense_research': (['연구직', '기술직'], '국방과학연구소·한국국방연구원·국방기술품질원 소속 확인'),
        'policy.forest_helicopter': (['승무원', '정비사', '방송통신사'], '산림청 산림항공본부·산림항공관리소 소속 및 직종별 훈련범위 확인'),
    }
    for key, (titles, qualification) in jobs.items():
        setrule(key, employer, current, enum('job_title', titles, '대상 직종의 명시적 근거'),
                eq('context.organization_duty_confirmed', True, qualification))
    for key, label in {
        'policy.intelligence_records': '국군정보사 특수기록과 담당 확인',
        'policy.air_warning': '중앙통제소 또는 광역시·도 경보통제소 근무 확인',
        'policy.radio_monitor': '중앙전파관리소 전파관제과 근무 확인',
        'policy.security_telecom': '중앙 통신운용센터 근무 확인',
        'policy.road_control': '한국도로공사 교통정보센터·종합상황실 근무 확인',
        'policy.private_prison': '법무부 위탁 민영교도소 직원 확인',
    }.items():
        setrule(key, employer, current, present('department', '근무 부서'), eq('context.organization_duty_confirmed', True, label))
    setrule('statutory.international_ship', present('vessel_name', '선박'), present('crew_role', '선원 직책'),
            enum('route_kind', ['국제선', '국제항로', '국외 왕래'], '국외 왕래 항로'),
            eq('context.current_boarding_confirmed', True, '해당 시점 선원 승선·재직 확인'))
    setrule('statutory.international_aircrew', current, employer,
            enum('job_title', ['조종사', '승무원', '항공기 조종사', '항공기 승무원'], '항공기 조종사·승무원'),
            eq('context.international_route_confirmed', True, '국외 왕래 항공기 근무 확인'))
    setrule('statutory.fishery_guidance', present('vessel_name', '어업지도선'), present('crew_role', '승선 직책'),
            eq('context.fishery_guidance_boarding_confirmed', True, '어업지도선 실제 승선요원 확인'))
    setrule('statutory.civil_defense_head', enum('job_title', ['민방위대장'], '민방위대장 직위'),
            present('appointment_basis', '임명 근거'), eq('context.appointment_valid', True, '민방위기본법에 따른 현재 임명 유효 확인'))
    setrule('statutory.usfk_agreement', employer, current,
            present('appointment_basis', '고용·협정 적용 근거'),
            manual('usfk_branches', 'SOFA 종업원/한국노무단 협정 고용원/국내 용역업체 경비요원의 해당 분기·계약 범위 확인', ['contract_relationship', 'job_title']), coverage='partial')
    for key, label in {
        'policy.veteran': '전상·공상·재해부상 군경·공무원 사유로 보훈기관 등록된 대상 확인',
        'policy.essential_worker': '적격 군동원업체 필수요원 선발 및 당해 연도 수임군부대 명령/심의 확인',
        'policy.customs': '세관 조사공무원의 사법경찰관리 지명 확인',
        'policy.petition_police': '청원경찰법 적용 대상 확인',
        'policy.special_guard': '국가중요시설 배치 및 특수경비 업무 확인',
    }.items():
        setrule(key, present('designation_kind', '지정·등록 종류'),
                eq('context.designation_eligibility_confirmed', True, label),
                eq('context.registration_current', True, '현재 지정·등록 효력 확인'))
    setrule('policy.single_parent_low_income', eq('household_head', True, '한부모가족의 가장'),
            eq('context.low_income_certificate_confirmed', True, '차상위계층 증명서 확인'),
            eq('context.single_parent_certificate_confirmed', True, '한부모가족 증명서 확인'))
    setrule('policy.older_cadre', enum('context.rank_group', ['장교', '준사관', '부사관'], '예비역 간부 구분'),
            leaf('cadre_age', '만 41세가 되는 해의 1월 1일부터', 'year_age', ['context.applicant_birth_date', 'context.assessment_date'], years=41))
    setrule('policy.custody', enum('custody_kind', ['구속', '수감', '사회봉사', '가석방'], '처분 구분'),
            manual('custody_period', '수감·가석방 기간 또는 6개월 이상 사회봉사명령 이행기간을 분리 확인(6개월을 수감 전체에 적용하지 않음)', ['custody_start', 'custody_end', 'custody_duration']), coverage='partial')
    setrule('policy.female_reservist', eq('context.female_reservist_confirmed', True, '여군 출신 예비군 확인'),
            manual('female_branches', '임신~출산 후 12개월, 유산·사산 주수별 3/6/12개월, 6세 이하 자녀, 배우자 군인·군무원·예비군, 불임치료의 대체 요건 확인',
                   ['pregnancy_status', 'birth_date', 'pregnancy_loss_date', 'gestation_weeks', 'child_birth_date', 'spouse_service_category', 'infertility_treatment']), coverage='partial')
    setrule('policy.university_professor', employer, current,
            enum('job_title', ['교수', '부교수', '조교수', '전임강사'], '대상 교수 직위', ['명예교수', '시간강사', '초빙교수', '겸임교원']),
            eq('context.university_professor_scope_confirmed', True, '고등교육법/특별법 대상 대학 및 원격·평생교육·연구전담 등 제외 확인'))
    setrule('policy.hydrographic', employer, present('annual_sea_service', '연간 해상근무 기간'),
            eq('context.hydrographic_service_confirmed', True, '국립해양조사원·해양조사사무소 해당 수로원/해양원 및 연간 6개월 이상 해상근무 확인'))
    setrule('policy.fire_candidate', enum('academic_status', ['재학', '재학중', '재학 중'], '재학 상태'),
            enum('school_kind', ['소방학교'], '소방학교'), eq('context.fire_cadre_candidate_confirmed', True, '소방간부후보생 신분 확인'))
    setrule('policy.vocational_teacher', current, employer,
            enum('job_title', ['교수', '부교수', '조교수', '전임강사', '교사'], '교수·교사 직위'),
            eq('context.vocational_institution_recognized', True, '국민 평생 직업능력 개발법상 기능대학 또는 공공직업훈련시설 확인'))
    setrule('policy.vocational_student', enum('academic_status', ['재학', '재학중', '재학 중', '훈련 중'], '재학·훈련 상태'),
            eq('context.vocational_institution_recognized', True, '해당 법상 기능대학 또는 공공직업훈련시설 확인'),
            eq('degree_course', False, '기능대학 학위과정 학생 제외'),
            manual('vocational_duration', '공공직업훈련시설 훈련생의 6개월 이상 교육과정 및 기능대학 분기 확인', ['school_kind', 'course_duration']), coverage='partial')

    # Conditions belong to the same catalog as every other application type.
    duration = dict(
        duration_pattern=r'(?:진단일(?:로)?부터\s*)?(?P<count>\d+)\s*(?P<unit>일|주)(?:간)?(?:의)?\s*(?:안정\s*및\s*)?(?:치료|가료)(?:가|를)?\s*필요(?:합니다|하다|함|할 것으로 사료됩니다)?[.]?',
        split_pattern=r'(?<=[.!?])\s+|\n', unit_days={'일': 1, '주': 7},
        exclude_pattern=r'(?:치료|가료).{0,20}(?:필요하지|불필요|종료|완료|않|경우)')
    period = leaf('treatment_period', '진단일을 1일째로 포함한 명시적 치료 기간과 훈련 기간 대조', 'overlap',
        ['diagnosis_date', 'treatment_opinion', 'context.training_start', 'context.training_end'],
        **{**duration, 'duration_pattern': duration['duration_pattern'].replace(r'(?:진단일(?:로)?부터\s*)?', r'진단일(?:로)?부터\s*')})
    branches = [overlap('admission_date', 'discharge_date')]
    for key, label, accepted, extra in [
        ('immobile', '명시적 거동 불가 소견', ['거동 불가', '거동할 수 없음', '거동이 불가능함'], []),
        ('supervision', '명시적 보호·감시 필요 소견', ['보호 필요', '감시 필요', '보호 또는 감시 필요'],
         [eq('context.mental_illness_confirmed', True, '정신질환 진단 해당 여부 확인')]),
        ('visible', '명시적 훈련 참석 불가 소견', ['훈련 참석 불가', '훈련 참석이 어려움'],
         [eq('context.visible_illness_confirmed', True, '외관상 명백한 질병·장애 확인')]),
    ]:
        branches.append(group(key, label, 'all',
            leaf(key+'_opinion', label+' (간접 표현은 담당자 검토)', 'enum', ['treatment_opinion'],
                 accepted=accepted, split_pattern=r'\n|(?<=\.)\s+', strip_suffix='.'), period, *extra))
    setrule('postponement.illness',
        group('medical_reason', '훈련일 입원·거동 불가·정신질환 보호·외관상 명백한 질환의 대체 요건', 'any', *branches), coverage='partial')
    setrule('policy.long_illness',
        group('diagnosis', '질병·심신장애 진단', 'any', present('diagnosis', '주 질병·부상'), present('secondary_diagnosis', '부 질병·부상')),
        leaf('long_treatment', '소견에 명시된 180일 이상 장기치료', 'days_at_least', ['treatment_opinion'], days=180, **duration),
        eq('context.medical_certificate_confirmed', True, '진단서 제출 및 의료기관 발급 확인'), coverage='partial')
    setrule('policy.medical_service_change',
        eq('context.medical_service_history_confirmed', True,
           '공적 병역 이력 확인: 현역→보충역 복무 후 예비군, 간부 심신장애 1~9급 전역, 정신과 4급 이력 중 해당 요건 및 관련 공문 확인'), coverage='partial')

    result = {'version': '1.4.1', 'basis': 'provided_pdf', 'common': [
        group('identity', '신청자와 증빙 대상자 일치', 'all',
              leaf('name_match', '성명 대조', 'equal_fields', ['subject_name', 'context.applicant_name']),
              group('identity_number', '군번 또는 생년월일 대조', 'any',
                    leaf('number_match', '군번 대조', 'equal_fields', ['subject_service_number', 'context.applicant_service_number']),
                    leaf('birth_match', '생년월일 대조', 'equal_fields', ['subject_birth_date', 'context.applicant_birth_date']))),
        eq('context.documents_acceptable', True, '신청 분기에 맞는 구비서류·발급주체·유효기간 확인'),
        eq('context.training_scope_applicable', True, '신청한 훈련종류에 해당 보류/연기 범위 적용')], 'types': types}
    for kind in ('postponement.illness', 'policy.long_illness', 'policy.medical_service_change'):
        types[kind]['common'] = [
            group('identity', '환자와 신청자 본인 확인', 'all',
                  leaf('name_match', '환자 성명 대조', 'equal_fields', ['subject_name', 'context.applicant_name']),
                  leaf('patient_identity', '원본 신원 자료와 신청자 일치 확인', 'equals',
                       ['context.patient_identity_confirmed'], value=True, supporting_fields=['subject_birth_date'])),
            {**result['common'][1], 'supporting_fields': ['diagnosis', 'secondary_diagnosis', 'treatment_opinion']},
            result['common'][2]]
    for kind, entry in types.items():
        entry['review_items'] = [
            dict(id='identity', label='본인확인', fields=['subject_name', 'subject_service_number', 'subject_birth_date'], person_fields=['name', 'military_number']),
            dict(id='eligibility', label='보류/연기 사유 포함 여부', fields=sorted(references(entry['checks'])), context_fields=[]),
            dict(id='issuer', label='발급주체 및 원본 확인', fields=[], context_fields=[]),
        ]
    for kind in ('postponement.illness', 'policy.long_illness', 'policy.medical_service_change'):
        types[kind]['review_items'] = [
            dict(id='identity', label='본인확인', fields=['subject_name', 'subject_birth_date'], person_fields=['name', 'military_number']),
            dict(id='eligibility', label='보류/연기 사유 포함 여부', fields=['diagnosis', 'secondary_diagnosis', 'treatment_opinion']),
            dict(id='issuer', label='발급주체 확인', fields=['medical_institution', 'doctor_name', 'doctor_license', 'doctor_kind']),
            dict(id='injury', label='부상·질병 내용', fields=['diagnosis', 'secondary_diagnosis', 'treatment_opinion']),
            dict(id='dates', label='발병 시기와 훈련 날짜', fields=['onset_date'] + (['diagnosis_date', 'admission_date', 'discharge_date'] if kind == 'postponement.illness' else []), context_fields=['training_start', 'training_end']),
        ]
    used = set()
    for entry in types.values():
        used.update(references(entry.get('common', result['common']) + entry['checks'] + entry['review_items']))
    used = extraction_dependencies(used, common)
    assert used <= common['fields'].keys(), used - common['fields'].keys()
    common['fields'] = {k: v for k, v in common['fields'].items() if k in used}
    common['field_groups'] = {k: [f for f in v if f in used] for k, v in common['field_groups'].items()}
    common['version'] = '0.3.0'
    (BASE/'common_fields.json').write_text(json.dumps(common, ensure_ascii=False, indent=2), encoding='utf-8')
    (BASE/'verification_rules.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__': build()
