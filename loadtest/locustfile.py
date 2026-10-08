"""
Жүктеме тесті (Locust): әр виртуалды студент өз тест аккаунтымен кіреді,
ашық сессияда тестті бастайды, 50 сұраққа 5–20 секунд аралықпен жауап береді
және тестті аяқтайды. Бір студент — бір тест (бір сессияда бір әрекет).

Дайындық (серверде немесе жергілікті):
    python manage.py loadtest_data --count 1000
    → LOADTEST_SESSION_ID=<id> LOADTEST_ACCOUNTS=1000 деп шығарады

Іске қосу (толығы — README, «Жүктеме тесті»):
    LOADTEST_SESSION_ID=5 LOADTEST_ACCOUNTS=1000 \\
        locust -f loadtest/locustfile.py --host https://test.example.kz \\
        --headless -u 1000 -r 10

Баптаулар (орта айнымалылары):
    LOADTEST_SESSION_ID  — тест сессиясының id-і (міндетті)
    LOADTEST_ACCOUNTS    — аккаунт саны: student001 ... (әдепкі: 100)
    LOADTEST_PASSWORD    — аккаунттардың құпия сөзі (әдепкі: loadtest_data-дағыдай)
    LOADTEST_LANGUAGE    — ескірген: тест тілін енді топ анықтайды (`loadtest_data --language`)
    LOADTEST_MIN_WAIT, LOADTEST_MAX_WAIT — жауаптар арасындағы кідіріс, секунд (5 және 20)

Маңызды: аккаунттар бір Locust процесінде ретімен беріледі, сондықтан
--processes / бөлінген (distributed) режимсіз іске қосыңыз.
"""

import itertools
import logging
import os
import random
import re

import gevent
from locust import HttpUser, constant, task
from locust.exception import StopUser

SESSION_ID = os.environ.get("LOADTEST_SESSION_ID", "")
ACCOUNTS = int(os.environ.get("LOADTEST_ACCOUNTS", "100"))
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "loadtest-pass-2026")
LANGUAGE = os.environ.get("LOADTEST_LANGUAGE", "kk")
MIN_WAIT = float(os.environ.get("LOADTEST_MIN_WAIT", "5"))
MAX_WAIT = float(os.environ.get("LOADTEST_MAX_WAIT", "20"))
QUESTIONS_TOTAL = 50

if not SESSION_ID:
    raise SystemExit(
        "LOADTEST_SESSION_ID көрсетілмеген. Алдымен: python manage.py loadtest_data"
    )

logger = logging.getLogger("loadtest")

# Әр виртуалды студентке жеке аккаунт: 1, 2, 3, ...
account_numbers = itertools.count(1)
# Тестті аяқтаған (немесе аккаунт жетпей тоқтаған) студенттер саны
finished_users = 0

ATTEMPT_URL_RE = re.compile(r"/test/(\d+)/")
ANSWER_RE = re.compile(r'name="answer" value="(\d+)"')


def question_answer_ids(page_html, path):
    """Бір сұрақтың жауап нұсқалары: бетте 50 форма бар, тек action=path формасынан аламыз."""
    match = re.search(rf'action="{re.escape(path)}"(.*?)</form>', page_html, re.S)
    if match is None:
        return []
    return ANSWER_RE.findall(match.group(1))


def final_url(response):
    """Соңғы мекенжай (байланыс қатесінде requests url бермейді — бос жол)."""
    return response.url or ""


def response_json(response):
    """AJAX жауабының JSON-ы (сервер қатесінде HTML келсе — бос сөздік)."""
    try:
        return response.json()
    except ValueError:
        return {}


class Student(HttpUser):
    # Кідірісті тапсырманың ішінде өзіміз басқарамыз (жауаптар арасында)
    wait_time = constant(0)

    def on_start(self):
        # Аккаунт тек беріледі; кіру мен тест — тапсырманың ішінде
        # (StopUser тек тапсырмада дұрыс өңделеді)
        self.number = next(account_numbers)
        self.username = f"student{self.number:03d}"

    # ---------- Көмекші әдістер ----------

    def post(self, path, data, name, ajax=False):
        """
        Django формасын жіберу: CSRF токені cookie-ден, Referer — HTTPS үшін.
        ajax=True — attempt.js сияқты (X-Requested-With), view JSON қайтарады.
        """
        data["csrfmiddlewaretoken"] = self.client.cookies.get("csrftoken", "")
        headers = {"Referer": self.host.rstrip("/") + path}
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        return self.client.post(
            path, data=data, headers=headers, name=name, catch_response=True
        )

    def user_done(self):
        """Студент жұмысын бітірді. Бәрі бітсе — Locust-ты тоқтатады."""
        global finished_users
        finished_users += 1
        runner = self.environment.runner
        if runner is not None and finished_users >= runner.target_user_count:
            logger.info("Барлық виртуалды студент тестті аяқтады.")
            gevent.spawn_later(1, runner.quit)
        raise StopUser()

    def login(self):
        self.client.get("/accounts/login/", name="/accounts/login/")
        with self.post(
            "/accounts/login/",
            {"username": self.username, "password": PASSWORD},
            name="/accounts/login/ [POST]",
        ) as response:
            # Сәтті кіргенде кабинетке бағытталады
            logged_in = "/dashboard/" in final_url(response)
            if not logged_in:
                response.failure(self.failure_text(response, "кіру сәтсіз"))
        if not logged_in:
            self.user_done()

    # ---------- Тест тапсыру ----------

    def failure_text(self, response, message):
        """Қате хабарламасы: студент, не болды, HTTP коды және соңғы мекенжай."""
        return f"{self.username}: {message} (HTTP {response.status_code}, {response.url})"

    @task
    def take_test(self):
        if self.number > ACCOUNTS:
            logger.error(
                "Аккаунт жетпейді: %s-студентке аккаунт жоқ (LOADTEST_ACCOUNTS=%s). "
                "loadtest_data --count арқылы көбірек жасаңыз.",
                self.number,
                ACCOUNTS,
            )
            self.user_done()
        self.login()

        start_path = f"/session/{SESSION_ID}/start/"
        response = self.client.get(start_path, name="/session/[id]/start/")
        # Бастау беті ашылса — тілді таңдап бастаймыз; әйтпесе бұрынғы әрекетке бағытталды
        if ATTEMPT_URL_RE.search(final_url(response)) is None:
            with self.post(
                start_path, {"language": LANGUAGE}, name="/session/[id]/start/ [POST]"
            ) as response:
                if ATTEMPT_URL_RE.search(final_url(response)) is None:
                    response.failure(self.failure_text(response, "тест басталмады"))
        match = ATTEMPT_URL_RE.search(final_url(response))
        if match is None:
            self.user_done()
        if "/result/" in final_url(response):
            logger.warning("%s: тест бұрын аяқталған", self.username)
            self.user_done()
        attempt_id = match.group(1)

        # Тест бетінде 50 сұрақтың бәрі бар, attempt.js бетті қайта жүктемейді:
        # браузер сияқты бетті бір рет аламыз (бастаған соң осы бетке бағытталды),
        # ал жауаптарды AJAX арқылы жібереміз
        page_html = response.text
        for number in range(1, QUESTIONS_TOTAL + 1):
            path = f"/test/{attempt_id}/q/{number}/"
            answer_ids = question_answer_ids(page_html, path)
            if not answer_ids:
                logger.warning("%s: %s-сұрақта жауап нұсқасы жоқ", self.username, number)
                break

            # Студент сұрақты оқып, ойланады
            gevent.sleep(random.uniform(MIN_WAIT, MAX_WAIT))

            with self.post(
                path,
                {"answer": random.choice(answer_ids)},
                name="/test/[id]/q/[n]/ [POST]",
                ajax=True,
            ) as answer:
                data = response_json(answer)
                # Мерзім өтсе, view нәтиже бетінің мекенжайын қайтарады
                expired = "redirect" in data
                if expired:
                    answer.failure(self.failure_text(answer, "жауап қабылданбады, мерзім өтті"))
                elif not data.get("saved"):
                    answer.failure(self.failure_text(answer, "жауап сақталмады"))
            if expired:
                break

        self.client.get(f"/test/{attempt_id}/finish/", name="/test/[id]/finish/")
        with self.post(
            f"/test/{attempt_id}/finish/", {}, name="/test/[id]/finish/ [POST]"
        ) as response:
            if "/result/" not in final_url(response):
                response.failure(self.failure_text(response, "тест аяқталмады"))
        self.user_done()
