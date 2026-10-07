# CLAUDE.md

Информатика бойынша ПББ тестін жаттықтыратын Django платформасы. Толық талаптар — `TZ.md`.

## Стек

- Python 3.12+, **Django 5.2 LTS**
- Деректер қоры: **PostgreSQL** (VPS), **SQLite** (жергілікті әзірлеу)
- Интерфейс: Django шаблондары + **Bootstrap 5 (CDN)**
- Суреттер: Pillow, `media/`
- `USE_TZ = True`, `TIME_ZONE = "Asia/Almaty"`
- **Қолданылмайды:** DRF (REST API), React, Celery, Docker. Django-дан басқа күрделі кітапхана қоспа.

## Жоба құрылымы

- Барлық Django қосымшалары `apps/` папкасында: `apps.accounts`, `apps.quiz`.
- `INSTALLED_APPS` ішінде `"apps.accounts"`, `"apps.quiz"`; әр `apps.py`-да `name = "apps.<атауы>"`.
- **Жаңа қосымша да `apps/` ішіне жасалады** (`apps/<атауы>/`, `name = "apps.<атауы>"`).
- Баптаулар — `config/` (settings.py, urls.py, wsgi.py); шаблондар — `templates/`; JS — `static/js/`.
- Тест параметрлері (50 сұрақ, 125 мин, 13/30/7) тек `apps/quiz/constants.py` ішінде.

## Код жазу ережелері

- **Views тек функциялар (FBV).** Класқа негізделген views жазба (тек Django-ның дайын `LoginView` / `LogoutView` / `set_language` қолданылады).
- **Бизнес-логика** (нұсқа құру, балл есептеу, банк толуы) — `apps/quiz/services.py`.
- **Форма тексерулері** — `apps/quiz/forms.py` (accounts үшін `apps/accounts/forms.py`). Views ішінде логика да, тексеру де болмайды.
- Оқытушы беттері — `apps/quiz/teacher_views.py`, `@staff_member_required`; студент беттері — `@login_required`.
- **Айнымалы/функция атаулары ағылшынша, түсініктемелер қазақша.** PEP 8.
- Код қарапайым болсын: жаңадан бастаған әзірлеуші оқи алатындай, артық абстракциясыз.

## Екі тіл (i18n)

- Интерфейс **қазақша (негізгі, `kk`) және орысша (`ru`)** — Django i18n, `LocaleMiddleware`.
- Интерфейстегі **барлық мәтін** шаблонда `{% translate %}` / `{% blocktranslate %}`, Python-да `gettext` / `gettext_lazy` ішінде жазылады. Бастапқы мәтін — қазақша.
- Аударма файлдары: `locale/kk/`, `locale/ru/` (`makemessages` / `compilemessages`).
- Сұрақтардың мазмұны аударылмайды — әр сұрақтың өз тілі бар (`language` өрісі).

## Қауіпсіздік

- `is_correct` тест аяқталмайынша HTML-ге шықпайды.
- Студент тек өз `Attempt`-ын және өз тобының сессияларын көреді (бөтеніне 404).
- Сессия уақыты мен тест мерзімін тек сервер тексереді.
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL` — `.env` файлынан.

## Жергілікті орта

Python виртуалды ортасы — **`.venv`** (Windows):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py load_topics
.venv\Scripts\python manage.py load_demo
.venv\Scripts\python manage.py runserver
```

## Тесттер

- Іске қосу: `python manage.py test` (`.venv\Scripts\python manage.py test`).
- **Әр кезеңнен кейін тесттерді міндетті түрде іске қос** және нәтижесін хабарла; жаңа функционалға тест жаз.

## Деректер

- `load_topics` — 11 тақырып, 20 тақырыпша (TZ.md, А қосымшасы).
- `load_demo` — демо сұрақтар мен контексттер, барлығы `is_demo=True`; `load_demo --delete` оларды толық өшіреді.

## Git

- Әр кезең аяқталып, тесттер өткен соң commit жаса. **Push жасама.**
