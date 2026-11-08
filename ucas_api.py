# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimal iClass client. Protocol adapted from zhan-nine/UCAS-Sign-in."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VERSION = '0.3.1'
DEFAULT_API_BASE = 'https://iclass.ucas.edu.cn:8181/app/'
DEFAULT_VERIFY_TEMPLATE = (
    'http://iclass.ucas.edu.cn:88/ve/webservices/mobileCheck.shtml'
    '?method=mobileLogin&username=${0}&password=${1}&lx=${2}'
)


def validate_template(value):
    value = value.strip()
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        raise ApiError('登录校验 URL 模板格式错误') from None
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username is not None or parts.password is not None or parts.fragment
            or '<' in value or '>' in value or any(c.isspace() for c in value)
            or not all(value.count('${' + str(i) + '}') == 1 for i in range(3))):
        raise ApiError('校验 URL 模板必须包含 ${0}、${1}、${2}，各一次；请保留原占位符')
    return value


class ApiError(Exception):
    """Safe, user-facing error (never includes request URLs or credentials)."""


class SessionExpired(ApiError):
    """The server explicitly reports an unusable login session."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward passwords/sessionId to a redirected destination.
        return None


def today():
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')


def validate_base(value):
    value = value.strip()
    try:
        parts = urlsplit(value)
        _ = parts.port  # validate port syntax
    except ValueError:
        raise ApiError('API 地址格式错误') from None
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment
            or any(c.isspace() for c in value) or '<' in value or '>' in value):
        raise ApiError('请填写真实 HTTPS API 根地址，不含账号、查询参数或片段')
    return value.rstrip('/') + '/'


def sign_parameter(code):
    code = code.strip()
    if re.fullmatch(r'[0-9]{7}', code):
        return 'courseSchedId', code
    compact = code.replace('-', '')
    if re.fullmatch(r'[0-9a-fA-F]{32}', compact):
        return 'timeTableId', compact.upper()
    raise ApiError('请输入 7 位课程 ID 或 32 位 UUID（可带连字符）')


def text(obj, key):
    value = obj.get(key)
    return '' if value is None else str(value).strip()


def school_message(root):
    result = root.get('result')
    result = result if isinstance(result, dict) else {}
    return (text(result, 'msg') or text(root, 'ERRMSG') or text(root, 'msg')
            or text(root, 'message'))


def schedule_error(stage, root):
    """Keep status codes visible without dumping identities or full responses."""
    codes = []
    for key in ('STATUS', 'ERRCODE'):
        value = text(root, key)
        if re.fullmatch(r'[A-Za-z0-9_.-]{1,32}', value):
            codes.append(f'{key}={value}')
    detail = '，'.join(codes) or '无状态码'
    return ApiError(f'{stage}未返回可用课表（{detail}）。请确认所选日期有课；若轻新课堂有课，请反馈这些状态码。')


def check_schedule_auth(root):
    # A nonzero STATUS alone does not prove that the session expired.
    message = school_message(root)
    if re.search(r'未登录|登录.*(?:失效|过期)|会话.*(?:失效|过期)|session.*(?:invalid|expired)', message, re.I):
        raise SessionExpired('学校明确提示登录或会话失效，请重新登录')


@dataclass(frozen=True)
class Session:
    user_id: str
    session_id: str = field(repr=False)
    student_no: str = ''


@dataclass(frozen=True)
class Course:
    code: str
    name: str
    begin: str
    end: str
    signed: bool
    teacher: str = ''


@dataclass(frozen=True)
class SignResult:
    ok: bool
    message: str
    timestamp_rejected: bool = False


def parse_sign(root):
    if 'STATUS' not in root and isinstance(root.get('data'), dict):
        root = root['data']
    result = root.get('result')
    result = result if isinstance(result, dict) else {}
    msg = school_message(root)
    # GET one-click requires an explicit attendance confirmation, not only STATUS=0.
    ok = (text(root, 'STATUS') == '0' and text(root, 'ERRCODE') in ('', '0')
          and text(result, 'stuSignStatus') == '1'
          and root.get('success', True) not in (False, 'false', 0)
          and not re.search(r'失效|过期|时间戳', msg))
    return SignResult(ok, '签到成功' if ok else (msg or '学校未确认签到成功，请刷新课程状态'),
                      '时间戳' in msg)


class Client:
    def __init__(self, base_url, verify_template, opener=None):
        self.base_url = validate_base(base_url)
        self.verify_template = validate_template(verify_template)
        self.opener = opener or build_opener(NoRedirect())

    def request(self, path, *, form=None, query=None, session=None, login=False):
        url = self.base_url + path
        if query:
            url += '?' + urlencode(query)
        headers = {'User-Agent': 'student_5.0.1.2_android_12__110000' if login else
                   'student_5.0.1.2_android_12_20_100000000000000_110000',
                   'Cache-Control': 'no-store', 'Accept': 'application/json'}
        if session:
            headers['sessionId'] = session.session_id
        data = None if form is None else urlencode(form).encode('utf-8')
        req = Request(url, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=15) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ApiError('学校响应过大，已停止读取')
            root = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(root, dict):
                raise ValueError()
            return root
        except HTTPError as exc:
            if exc.code == 401:
                raise SessionExpired('登录已失效，请重新登录') from None
            if exc.code == 403:
                raise ApiError('访问被拒绝或登录已失效，请检查网络并重新登录') from None
            raise ApiError(f'HTTP {exc.code}：请求失败（重定向也会被拒绝），请检查 API 地址') from None
        except (URLError, TimeoutError, OSError):
            raise ApiError('网络连接失败或超时，请检查校园网/VPN、接口地址和证书') from None
        except (ValueError, UnicodeError):
            raise ApiError('学校未返回有效 JSON，请检查 API 根地址及登录状态') from None

    def login(self, account, password):
        if not account.strip() or not password:
            raise ApiError('账号和密码不能为空')
        root = self.request('user/login.action', login=True, form={
            'phone': account.strip(), 'password': password, 'verificationType': '1',
            'verificationUrl': self.verify_template, 'userLevel': '1'})
        if text(root, 'STATUS') != '0':
            raise ApiError('登录失败，请检查账号、密码和校验 URL 模板')
        r = root.get('result')
        if not isinstance(r, dict) or not all(text(r, k) for k in ('id', 'sessionId', 'studentNo')):
            raise ApiError('学校登录响应缺少身份信息，已停止操作')
        return Session(text(r, 'id'), text(r, 'sessionId'), text(r, 'studentNo'))

    def courses(self, session, day):
        try:
            if not re.fullmatch(r'[0-9]{8}', day):
                raise ValueError()
            datetime.strptime(day, '%Y%m%d')
        except ValueError:
            raise ApiError('日期格式应为 YYYYMMDD，例如 20261108') from None
        form = {'id': session.user_id, 'dateStr': day}
        # Match the public UCAS web implementation: query parameters + GET.
        root = self.request('course/get_stu_course_sched.action', query=form, session=session)
        check_schedule_auth(root)
        rows = root.get('result')
        if text(root, 'STATUS') != '0' or not isinstance(rows, list) or not rows:
            # The Android implementation falls back even when day STATUS is nonzero.
            # Never turn that status into a login error without explicit evidence.
            week = self.request('course/get_stu_course_sched_week.action', form=form, session=session)
            check_schedule_auth(week)
            days = week.get('result')
            # Android's week endpoint uses STATUS=0 for an empty timetable;
            # nonempty weekly results commonly use STATUS=1.
            if (text(week, 'STATUS') == '0' and days is None
                    and text(week, 'ERRCODE') in ('', '0') and not school_message(week)):
                return []
            if not isinstance(days, list):
                raise schedule_error('周课表', week)
            if text(week, 'STATUS') not in ('0', '1') or text(week, 'ERRCODE') not in ('', '0'):
                raise schedule_error('周课表', week)
            rows = []
            for entry in days:
                if not isinstance(entry, dict):
                    raise schedule_error('周课表', week)
                if text(entry, 'dateStr').replace('-', '').replace('/', '') == day:
                    sched = entry.get('schedData')
                    if isinstance(sched, list):
                        rows.extend(sched)
                    else:
                        raise schedule_error('周课表', week)
        if any(not isinstance(r, dict) for r in rows):
            raise schedule_error('日课表', root)
        return [Course(text(r, 'id') or text(r, 'uuid'), text(r, 'courseName') or '未命名课程',
                       text(r, 'classBeginTime'), text(r, 'classEndTime'), text(r, 'signStatus') == '1', text(r, 'teacherName'))
                for r in rows if isinstance(r, dict)]

    def sign(self, session, code):
        key, value = sign_parameter(code)  # validate before any network operation
        for attempt in range(2):
            ts = self.server_timestamp()
            result = parse_sign(self.request('course/stu_scan_sign.action', session=session,
                                           query={key: value, 'timestamp': str(int(ts)), 'id': session.user_id}))
            if not result.timestamp_rejected or attempt == 1:
                return result

    def server_timestamp(self):
        clock = self.request('common/get_timestamp.do', query={'id': '0'}, form={})
        ts = clock.get('timestamp')
        if (text(clock, 'STATUS') != '0' or isinstance(ts, bool)
                or not isinstance(ts, (int, float)) or not 10**12 <= ts < 8640000000000001):
            raise ApiError('学校校时失败，未提交签到；请稍后重试')
        return int(ts)
