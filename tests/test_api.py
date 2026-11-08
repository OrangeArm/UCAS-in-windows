import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from ucas_api import ApiError, Client, NoRedirect, Session, parse_sign, sign_parameter, validate_base, validate_template, DEFAULT_API_BASE, DEFAULT_VERIFY_TEMPLATE

BASE = 'https://school.example/app/'
VERIFY = 'http://verify.example/check?u=${0}&p=${1}&t=${2}'
SESSION = Session('user123', 'secret-session', 'student123')
LOGIN = {'STATUS': '0', 'result': {'id': 'user123', 'sessionId': 'secret-session', 'studentNo': 'student123'}}
CLOCK = {'STATUS': '0', 'timestamp': 1794100000000}
SUCCESS = {'STATUS': '0', 'result': {'stuSignStatus': '1'}}


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(response if isinstance(response, bytes) else json.dumps(response).encode())


class ApiTests(unittest.TestCase):
    def client(self, *responses):
        transport = FakeOpener(*responses)
        return Client(BASE, VERIFY, transport), transport

    def test_login_parameters_and_no_secret_repr(self):
        client, transport = self.client(LOGIN)
        session = client.login(' someone ', 'p&=中文')
        self.assertEqual(session.user_id, 'user123')
        form = parse_qs(transport.requests[0].data.decode())
        self.assertEqual(form['phone'], ['someone'])
        self.assertEqual(form['password'], ['p&=中文'])
        self.assertEqual(form['verificationUrl'], [VERIFY])
        self.assertNotIn('secret-session', repr(session))

    def test_bad_login_never_creates_session(self):
        for response in [{'STATUS': '1'}, {'STATUS': '0', 'result': {'id': 'x'}}]:
            with self.subTest(response=response), self.assertRaises(ApiError):
                self.client(response)[0].login('a', 'b')

    def test_base_url_validation(self):
        for value in ['http://example.com', 'https://u:p@example.com', 'https://example.com/?a=1',
                      'https://<host>/app/', 'https://school.example:invalid', 'https://school.example/#x']:
            with self.subTest(value=value), self.assertRaises(ApiError):
                validate_base(value)
        self.assertEqual(validate_base('https://school.example/app'), BASE)

    def test_default_template_and_missing_placeholders(self):
        self.assertEqual(validate_template(DEFAULT_VERIFY_TEMPLATE), DEFAULT_VERIFY_TEMPLATE)
        self.assertEqual(validate_base(DEFAULT_API_BASE), DEFAULT_API_BASE)
        for value in ['http://verify.example/check', VERIFY.replace('${1}', ''),
                      VERIFY + '&extra=${0}', 'http://user:pass@example.com/?u=${0}&p=${1}&t=${2}']:
            with self.subTest(value=value), self.assertRaises(ApiError):
                validate_template(value)

    def test_ids(self):
        self.assertEqual(sign_parameter('1234567'), ('courseSchedId', '1234567'))
        self.assertEqual(sign_parameter('abcdef12-1234-5678-9abc-123456789abc'),
                         ('timeTableId', 'ABCDEF12123456789ABC123456789ABC'))
        for value in ['123', '', '１２３４５６７', 'https://evil.example/?id=1234567']:
            with self.subTest(value=value), self.assertRaises(ApiError):
                sign_parameter(value)

    def test_courses_and_session_header(self):
        client, transport = self.client({'STATUS': '0', 'result': [
            {'id': 1234567, 'courseName': '课程', 'signStatus': 1},
            {'id': None, 'uuid': 'a' * 32, 'signStatus': 0}]})
        courses = client.courses(SESSION, '20261108')
        self.assertTrue(courses[0].signed)
        self.assertEqual(courses[1].code, 'a' * 32)
        self.assertEqual(transport.requests[0].get_header('Sessionid'), 'secret-session')
        self.assertEqual(parse_qs(transport.requests[0].data.decode())['dateStr'], ['20261108'])

    def test_week_fallback_only_returns_requested_day(self):
        client, _ = self.client({'STATUS': '0', 'result': []}, {'STATUS': '1', 'result': [
            {'dateStr': '2026-11-08', 'schedData': [{'id': '1234567'}]},
            {'dateStr': '20261109', 'schedData': [{'id': '9999999'}]}]})
        self.assertEqual([c.code for c in client.courses(SESSION, '20261108')], ['1234567'])

    def test_invalid_course_responses_are_not_no_courses(self):
        for root in [{'STATUS': '1', 'result': []}, {'STATUS': '0', 'result': None}]:
            with self.subTest(root=root), self.assertRaises(ApiError):
                self.client(root)[0].courses(SESSION, '20261108')

    def test_sign_uses_school_clock(self):
        client, transport = self.client(CLOCK, SUCCESS)
        self.assertTrue(client.sign(SESSION, '1234567').ok)
        query = parse_qs(urlsplit(transport.requests[1].full_url).query)
        self.assertEqual(query, {'courseSchedId': ['1234567'], 'timestamp': ['1794100000000'], 'id': ['user123']})
        self.assertEqual(transport.requests[1].get_method(), 'GET')

    def test_success_requires_explicit_sign_status(self):
        for root in [{'STATUS': '0'}, {'STATUS': '0', 'result': {'stuSignStatus': '0'}},
                     {**SUCCESS, 'ERRCODE': '100'}, {**SUCCESS, 'success': False}]:
            with self.subTest(root=root):
                self.assertFalse(parse_sign(root).ok)
        self.assertTrue(parse_sign({'data': SUCCESS}).ok)

    def test_timestamp_retry_once_only(self):
        rejected = {'STATUS': '1', 'ERRMSG': '时间戳传入异常！'}
        client, transport = self.client(CLOCK, rejected, CLOCK, rejected)
        result = client.sign(SESSION, '1234567')
        self.assertFalse(result.ok)
        self.assertEqual(len(transport.requests), 4)
        client, _ = self.client(CLOCK, rejected, CLOCK, SUCCESS)
        self.assertTrue(client.sign(SESSION, '1234567').ok)

    def test_invalid_clock_never_submits(self):
        for ts in [0, True, '1794100000000', float('nan')]:
            client, transport = self.client({'STATUS': '0', 'timestamp': ts})
            with self.subTest(ts=ts), self.assertRaises(ApiError):
                client.sign(SESSION, '1234567')
            self.assertEqual(len(transport.requests), 1)

    def test_no_automatic_retry_after_timeout(self):
        client, transport = self.client(CLOCK, URLError('secret-session'))
        with self.assertRaises(ApiError) as error:
            client.sign(SESSION, '1234567')
        self.assertNotIn('secret-session', str(error.exception))
        self.assertEqual(len(transport.requests), 2)

    def test_network_errors_and_html_are_safe(self):
        for response in [b'<html>login</html>', b'[]', HTTPError(BASE, 302, 'redirect', {}, None)]:
            with self.subTest(response=response), self.assertRaises(ApiError):
                self.client(response)[0].login('user', 'password')
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_invalid_inputs_do_not_send_requests(self):
        client, transport = self.client()
        for operation in [lambda: client.sign(SESSION, 'bad'), lambda: client.courses(SESSION, 'bad'),
                          lambda: client.login('', '')]:
            with self.assertRaises(ApiError):
                operation()
        self.assertEqual(transport.requests, [])


if __name__ == '__main__':
    unittest.main()
