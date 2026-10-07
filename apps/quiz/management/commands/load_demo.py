"""
Тексеруге арналған демо сұрақтарды жүктейді (барлығы is_demo=True), әр пәнге бөлек.

Әр пәнде, әр тіл (kk, ru) үшін:
- әр тақырыпшаға 6 үлгі сұрақ (деңгейлері A, A, B, B, B, C);
- 4 контекст × 5 сұрақ;
- пәнге тән нақты сұрақтар: информатикада — Python коды (13–16 тақырыпшалар)
  және программасы бар контекст; математикада — формулалар (KaTeX), формуласы
  бар контекст және жауаптары тек суреттен тұратын сұрақ.

Іске қосу:
    python manage.py load_demo                                # тақырыптары жүктелген барлық пән
    python manage.py load_demo --subject mathematics          # бір пән
    python manage.py load_demo --delete                       # барлық демо деректерді өшіру
    python manage.py load_demo --delete --subject mathematics # бір пәннің демо деректерін

Нақты пайдалануға дейін `load_demo --delete` міндетті түрде орындалады.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw

from apps.quiz.constants import SUBTOPICS_COUNT
from apps.quiz.models import Answer, Attempt, Context, Question, Subject, Subtopic

LANGUAGES = ["kk", "ru"]

# Бір тақырыпшадағы үлгі сұрақтардың деңгейлері
SINGLE_LEVELS = ["A", "A", "B", "B", "B", "C"]

# Үлгі контексттегі 5 сұрақтың деңгейлері
CONTEXT_LEVELS = ["A", "B", "B", "B", "C"]

# Үлгі мәтіндер
TEMPLATE_TEXT = {
    "kk": "[ДЕМО] {subtopic:02d}-тақырыпша, {level} деңгей, №{index} сұрақ. Дұрыс жауапты таңдаңыз.",
    "ru": "[ДЕМО] Подтема {subtopic:02d}, уровень {level}, вопрос №{index}. Выберите правильный ответ.",
}
TEMPLATE_ANSWER = {
    "kk": "Демо жауап {letter}",
    "ru": "Демо ответ {letter}",
}


# ---------- Python коды бар нақты сұрақтар ----------
# Әр жауап тізімінде бірінші нұсқа — дұрыс (тест кезінде реті араластырылады)

REAL_QUESTIONS = [
    {
        "subtopic": 13,
        "level": "A",
        "text": {
            "kk": "x жұп сан болғанда «Yes» шығаратын код қайсы?",
            "ru": "Какой код выводит «Yes», когда x — чётное число?",
        },
        "code": "",
        "answers": [
            'if x % 2 == 0:\n    print("Yes")',
            'if x % 2 == 1:\n    print("Yes")',
            'if x / 2 == 0:\n    print("Yes")',
            'if x // 2 == 0:\n    print("Yes")',
        ],
    },
    {
        "subtopic": 13,
        "level": "B",
        "text": {
            "kk": "Программа нені шығарады?",
            "ru": "Что выведет программа?",
        },
        "code": (
            "x = 7\n"
            "if x > 5:\n"
            "    if x % 2 == 0:\n"
            '        print("A")\n'
            "    else:\n"
            '        print("B")\n'
            "else:\n"
            '    print("C")'
        ),
        "answers": ["B", "A", "C", "AB"],
    },
    {
        "subtopic": 14,
        "level": "A",
        "text": {
            "kk": "Программа нені шығарады?",
            "ru": "Что выведет программа?",
        },
        "code": "s = 0\nfor i in range(1, 5):\n    s += i\nprint(s)",
        "answers": ["10", "15", "4", "6"],
    },
    {
        "subtopic": 14,
        "level": "B",
        "text": {
            "kk": "Цикл аяқталғаннан кейін count айнымалысының мәні қандай?",
            "ru": "Какое значение будет у переменной count после завершения цикла?",
        },
        "code": "n = 100\ncount = 0\nwhile n > 1:\n    n = n // 2\n    count += 1\nprint(count)",
        "answers": ["6", "7", "5", "50"],
    },
    {
        "subtopic": 15,
        "level": "B",
        "text": {
            "kk": "Программа нені шығарады?",
            "ru": "Что выведет программа?",
        },
        "code": "a = [5, 2, 8, 1]\na.sort(reverse=True)\nprint(a[1])",
        "answers": ["5", "2", "8", "1"],
    },
    {
        "subtopic": 16,
        "level": "C",
        "text": {
            "kk": "f(7) функциясы қандай мән қайтарады?",
            "ru": "Какое значение вернёт функция f(7)?",
        },
        "code": (
            "def f(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * f(n - 2)\n"
            "\n"
            "print(f(7))"
        ),
        "answers": ["105", "5040", "15", "35"],
    },
]


# ---------- Контексттер ----------

# Python программасы бар нақты контекст және оның 5 сұрағы
REAL_CONTEXT = {
    "title": {
        "kk": "[ДЕМО] Жұп сандардың қосындысы",
        "ru": "[ДЕМО] Сумма чётных чисел",
    },
    "text": {
        "kk": "Төмендегі Python программасын оқып, сұрақтарға жауап беріңіз.",
        "ru": "Прочитайте программу на Python и ответьте на вопросы.",
    },
    "code": (
        "numbers = [3, 8, 1, 6, 4]\n"
        "total = 0\n"
        "for n in numbers:\n"
        "    if n % 2 == 0:\n"
        "        total += n\n"
        "print(total)"
    ),
    "questions": [
        {
            "subtopic": 14,
            "level": "A",
            "text": {
                "kk": "Программа нені шығарады?",
                "ru": "Что выведет программа?",
            },
            "answers": ["18", "22", "4", "8"],
        },
        {
            "subtopic": 14,
            "level": "B",
            "text": {
                "kk": "for циклі неше рет орындалады?",
                "ru": "Сколько раз выполнится цикл for?",
            },
            "answers": ["5", "3", "4", "6"],
        },
        {
            "subtopic": 13,
            "level": "B",
            "text": {
                "kk": "«n % 2 == 0» шартын «n % 2 == 1» деп ауыстырса, программа нені шығарады?",
                "ru": "Что выведет программа, если условие «n % 2 == 0» заменить на «n % 2 == 1»?",
            },
            "answers": ["4", "18", "3", "0"],
        },
        {
            "subtopic": 15,
            "level": "B",
            "text": {
                "kk": "numbers айнымалысының типі қандай?",
                "ru": "Какой тип у переменной numbers?",
            },
            "answers": ["list", "tuple", "dict", "set"],
        },
        {
            "subtopic": 14,
            "level": "C",
            "text": {
                "kk": "Циклдің үшінші қадамынан кейін total мәні қандай?",
                "ru": "Чему равно total после третьего шага цикла?",
            },
            "answers": ["8", "9", "12", "0"],
        },
    ],
}

# Үлгі контексттер: атауы, мәтіні және сұрақтарының тақырыпшалары
TEMPLATE_CONTEXTS = [
    {
        "title": {
            "kk": "[ДЕМО] Дүкеннің сатылым кестесі",
            "ru": "[ДЕМО] Таблица продаж магазина",
        },
        "text": {
            "kk": "Тауар | Саны | Бағасы\nДәптер | 120 | 150\nҚалам | 300 | 80\nКітап | 45 | 2500",
            "ru": "Товар | Количество | Цена\nТетрадь | 120 | 150\nРучка | 300 | 80\nКнига | 45 | 2500",
        },
        "subtopics": [9, 10, 10, 9, 10],
    },
    {
        "title": {
            "kk": "[ДЕМО] Кітапхананың мәліметтер қоры",
            "ru": "[ДЕМО] База данных библиотеки",
        },
        "text": {
            "kk": "Books(id, title, author, year) және Readers(id, name, book_id) кестелері берілген.",
            "ru": "Даны таблицы Books(id, title, author, year) и Readers(id, name, book_id).",
        },
        "subtopics": [11, 11, 12, 12, 11],
    },
    {
        "title": {
            "kk": "[ДЕМО] Мектептің компьютерлік желісі",
            "ru": "[ДЕМО] Компьютерная сеть школы",
        },
        "text": {
            "kk": "Мектепте 3 компьютер сыныбы бар, олар бір коммутатор арқылы Wi-Fi роутерге қосылған.",
            "ru": "В школе 3 компьютерных класса, подключённых через коммутатор к Wi-Fi роутеру.",
        },
        "subtopics": [6, 6, 7, 7, 6],
    },
]


# ---------- Математика: формуласы бар нақты сұрақтар (TZ.md, 10.6) ----------
# Формула белгілеуі: \( ... \) — жол ішінде (KaTeX). Бірінші жауап — дұрыс.

MATH_QUESTIONS = [
    {
        "subtopic": 4,
        "level": "A",
        "text": {
            "kk": "Теңдеуді шешіңіз: \\(x^2 - 5x + 6 = 0\\).",
            "ru": "Решите уравнение: \\(x^2 - 5x + 6 = 0\\).",
        },
        "answers": [
            "\\(x_1 = 2,\\ x_2 = 3\\)",
            "\\(x_1 = -2,\\ x_2 = -3\\)",
            "\\(x_1 = 1,\\ x_2 = 6\\)",
            "\\(x_1 = -1,\\ x_2 = 6\\)",
        ],
    },
    {
        "subtopic": 7,
        "level": "B",
        "text": {
            "kk": "Арифметикалық прогрессияда \\(a_1 = 2\\), \\(d = 3\\). \\(a_{10}\\) табыңыз.",
            "ru": "В арифметической прогрессии \\(a_1 = 2\\), \\(d = 3\\). Найдите \\(a_{10}\\).",
        },
        "answers": ["\\(29\\)", "\\(32\\)", "\\(30\\)", "\\(27\\)"],
    },
    {
        "subtopic": 8,
        "level": "A",
        "text": {
            "kk": "\\(\\sin^2\\alpha + \\cos^2\\alpha\\) өрнегінің мәні неге тең?",
            "ru": "Чему равно значение выражения \\(\\sin^2\\alpha + \\cos^2\\alpha\\)?",
        },
        "answers": ["\\(1\\)", "\\(0\\)", "\\(2\\)", "\\(\\sin 2\\alpha\\)"],
    },
    {
        "subtopic": 15,
        "level": "B",
        "text": {
            "kk": "\\(f(x) = x^3 - 3x\\) функциясының туындысын табыңыз.",
            "ru": "Найдите производную функции \\(f(x) = x^3 - 3x\\).",
        },
        "answers": ["\\(3x^2 - 3\\)", "\\(3x^2\\)", "\\(x^2 - 3\\)", "\\(3x - 3\\)"],
    },
    {
        "subtopic": 16,
        "level": "B",
        "text": {
            "kk": "Есептеңіз: \\[\\int_0^1 2x\\,dx\\]",
            "ru": "Вычислите: \\[\\int_0^1 2x\\,dx\\]",
        },
        "answers": ["\\(1\\)", "\\(2\\)", "\\(\\frac{1}{2}\\)", "\\(0\\)"],
    },
    {
        "subtopic": 17,
        "level": "A",
        "text": {
            "kk": "Есептеңіз: \\(\\sqrt{49} + \\sqrt[3]{8}\\).",
            "ru": "Вычислите: \\(\\sqrt{49} + \\sqrt[3]{8}\\).",
        },
        "answers": ["\\(9\\)", "\\(11\\)", "\\(7\\)", "\\(15\\)"],
    },
    {
        "subtopic": 20,
        "level": "C",
        "text": {
            "kk": "\\(z = 3 + 4i\\) комплекс санының модулін табыңыз.",
            "ru": "Найдите модуль комплексного числа \\(z = 3 + 4i\\).",
        },
        "answers": ["\\(5\\)", "\\(7\\)", "\\(25\\)", "\\(\\sqrt{7}\\)"],
    },
]

# Жауап нұсқалары тек суреттен тұратын сұрақ (TZ.md, 10.7): бірінші сурет — дұрыс
MATH_IMAGE_QUESTION = {
    "subtopic": 2,
    "level": "A",
    "text": {
        "kk": "Суреттегі қай фигура — ромб?",
        "ru": "Какая фигура на рисунке — ромб?",
    },
    "shapes": ["rhombus", "trapezoid", "triangle", "circle"],
}

# Математиканың формуласы бар контексті
MATH_CONTEXT = {
    "title": {
        "kk": "[ДЕМО] Квадраттық функция",
        "ru": "[ДЕМО] Квадратичная функция",
    },
    "text": {
        "kk": "\\(f(x) = x^2 - 4x + 3\\) функциясы берілген.",
        "ru": "Дана функция \\(f(x) = x^2 - 4x + 3\\).",
    },
    "subtopics": [4, 4, 5, 19, 19],
}


def generic_contexts(count):
    """
    Кез келген пәнге жарайтын үлгі контексттер: әрқайсында 5 сұрақ,
    тақырыпшалары 01–05, 06–10, 11–15, 16–20.
    """
    contexts = []
    for index in range(count):
        first = index * 5 + 1
        contexts.append(
            {
                "title": {
                    "kk": f"[ДЕМО] Үлгі контекст №{index + 1}",
                    "ru": f"[ДЕМО] Пример контекста №{index + 1}",
                },
                "text": {
                    "kk": "Контекстің мәтіні: кесте, сызба немесе жағдаят сипаттамасы.",
                    "ru": "Текст контекста: таблица, чертёж или описание ситуации.",
                },
                "subtopics": list(range(first, first + 5)),
            }
        )
    return contexts


# Әр пәннің демо деректері. Барлық пәнде әр тілде 4 толық контекст болады.
SUBJECT_DEMO = {
    "informatics": {
        "questions": REAL_QUESTIONS,
        "code_contexts": [REAL_CONTEXT],
        "contexts": TEMPLATE_CONTEXTS,
        "image_questions": [],
    },
    "mathematics": {
        "questions": MATH_QUESTIONS,
        "code_contexts": [],
        "contexts": [MATH_CONTEXT] + generic_contexts(3),
        "image_questions": [MATH_IMAGE_QUESTION],
    },
}
# Қалған пәндер (көркем еңбек, ...): тек үлгі сұрақтар мен үлгі контексттер
DEFAULT_DEMO = {
    "questions": [],
    "code_contexts": [],
    "contexts": generic_contexts(4),
    "image_questions": [],
}


def shape_png(shape):
    """Демо сурет: ақ фонда бір геометриялық фигура (PNG байттары)."""
    image = Image.new("RGB", (200, 140), "white")
    draw = ImageDraw.Draw(image)
    color = (13, 110, 253)
    if shape == "rhombus":
        draw.polygon([(100, 10), (170, 70), (100, 130), (30, 70)], outline=color, width=4)
    elif shape == "trapezoid":
        draw.polygon([(60, 20), (140, 20), (180, 120), (20, 120)], outline=color, width=4)
    elif shape == "triangle":
        draw.polygon([(100, 15), (175, 125), (25, 125)], outline=color, width=4)
    else:
        draw.ellipse([(45, 15), (155, 125)], outline=color, width=4)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def create_question(subtopic, language, level, text, answers, code="", context=None):
    """Сұрақ пен оның 4 жауабын жасайды; answers тізімінің бірінші элементі — дұрыс."""
    question = Question.objects.create(
        subtopic=subtopic,
        context=context,
        language=language,
        text=text,
        code=code,
        level=level,
        is_demo=True,
    )
    for index, answer_text in enumerate(answers):
        Answer.objects.create(question=question, text=answer_text, is_correct=(index == 0))
    return question


def create_image_question(subtopic, language, item):
    """Жауап нұсқалары тек суреттен тұратын сұрақ; бірінші сурет — дұрыс."""
    question = create_question(subtopic, language, item["level"], item["text"][language], [])
    for index, shape in enumerate(item["shapes"]):
        answer = Answer(question=question, is_correct=(index == 0))
        # Файл аты кездейсоқ болады (models.answer_image_path)
        answer.image.save(f"{shape}.png", ContentFile(shape_png(shape)), save=False)
        answer.save()
    return question


def template_answers(language):
    return [TEMPLATE_ANSWER[language].format(letter=letter) for letter in "ABCD"]


class Command(BaseCommand):
    help = "Демо сұрақтарды жүктейді (--subject — бір пәнге, --delete — өшіреді)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject",
            metavar="CODE",
            help="Тек осы пән (мысалы, mathematics); берілмесе — тақырыптары жүктелген барлық пән.",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Демо сұрақтар мен контексттерді өшіру (--subject берілсе — тек сол пәннің).",
        )

    def handle(self, *args, **options):
        if options["subject"]:
            subjects = list(Subject.objects.filter(code=options["subject"]))
            if not subjects:
                raise CommandError(
                    f"«{options['subject']}» пәні жоқ. Алдымен: "
                    f"python manage.py load_subjects --only {options['subject']}"
                )
        else:
            subjects = list(Subject.objects.all())

        if options["delete"]:
            self.delete_demo(subjects)
            return

        loaded = [subject for subject in subjects if self.subtopics(subject)]
        if not loaded:
            only = f" --only {options['subject']}" if options["subject"] else ""
            raise CommandError(
                f"Алдымен тақырыптарды жүктеңіз: python manage.py load_subjects{only}"
            )
        for subject in loaded:
            self.load_subject(subject)

    def subtopics(self, subject):
        """Пәннің тақырыпшалары {нөмірі: тақырыпша}; 20-сы толық жүктелмесе — бос сөздік."""
        subtopics = {
            subtopic.number: subtopic
            for subtopic in Subtopic.objects.filter(topic__subject=subject)
        }
        return subtopics if len(subtopics) == SUBTOPICS_COUNT else {}

    @transaction.atomic
    def delete_demo(self, subjects):
        demo_questions = Question.objects.filter(
            is_demo=True, subtopic__topic__subject__in=subjects
        )
        # Демо сұрақтар кездескен тест әрекеттері де өшеді (олар тек тексеруге арналған)
        attempt_ids = list(
            Attempt.objects.filter(items__question__in=demo_questions)
            .values_list("pk", flat=True)
            .distinct()
        )
        Attempt.objects.filter(pk__in=attempt_ids).delete()

        image_names = set(
            Answer.objects.filter(question__in=demo_questions)
            .exclude(image="")
            .values_list("image", flat=True)
        )
        question_count = demo_questions.count()
        demo_questions.delete()  # жауаптары бірге өшеді (CASCADE)
        # Демо суреттердің файлдары да өшеді (басқа жауап қолданбаса)
        for name in image_names:
            if not Answer.objects.filter(image=name).exists():
                default_storage.delete(name)

        # Нақты (демо емес) сұрақ байланған демо контекст өшірілмейді
        demo_contexts = Context.objects.filter(is_demo=True, subject__in=subjects)
        used_contexts = demo_contexts.filter(questions__isnull=False).distinct()
        free_contexts = demo_contexts.exclude(pk__in=used_contexts)
        context_count = free_contexts.count()
        free_contexts.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Өшірілді: {question_count} демо сұрақ, {context_count} демо контекст, "
                f"{len(attempt_ids)} тест әрекеті."
            )
        )
        if used_contexts.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Назар аударыңыз: келесі демо контексттерге нақты сұрақтар байланған, "
                    "сондықтан олар өшірілмеді: "
                    + ", ".join(str(context.pk) for context in used_contexts)
                )
            )

    @transaction.atomic
    def load_subject(self, subject):
        """Бір пәннің демо деректері: әр тілде үлгі сұрақтар, нақты сұрақтар, 4 контекст."""
        subtopics = self.subtopics(subject)
        demo_questions = Question.objects.filter(is_demo=True, subtopic__topic__subject=subject)
        if demo_questions.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"{subject.code}: демо сұрақтар бұрыннан бар. Қайта жүктеу үшін алдымен "
                    f"`python manage.py load_demo --delete --subject {subject.code}` орындаңыз."
                )
            )
            return

        demo = SUBJECT_DEMO.get(subject.code, DEFAULT_DEMO)
        for language in LANGUAGES:
            # 1) Әр тақырыпшаға 6 үлгі сұрақ
            for number, subtopic in subtopics.items():
                for index, level in enumerate(SINGLE_LEVELS, start=1):
                    text = TEMPLATE_TEXT[language].format(
                        subtopic=number, level=level, index=index
                    )
                    create_question(subtopic, language, level, text, template_answers(language))

            # 2) Пәнге тән нақты сұрақтар (информатикада — Python коды, математикада — формула)
            for item in demo["questions"]:
                create_question(
                    subtopics[item["subtopic"]],
                    language,
                    item["level"],
                    item["text"][language],
                    item["answers"],
                    code=item.get("code", ""),
                )
            for item in demo["image_questions"]:
                create_image_question(subtopics[item["subtopic"]], language, item)

            # 3) Нақты сұрақтары бар контекст (информатика: Python программасы)
            for real_context in demo["code_contexts"]:
                context = Context.objects.create(
                    subject=subject,
                    language=language,
                    title=real_context["title"][language],
                    text=real_context["text"][language],
                    code=real_context["code"],
                    is_demo=True,
                )
                for item in real_context["questions"]:
                    create_question(
                        subtopics[item["subtopic"]],
                        language,
                        item["level"],
                        item["text"][language],
                        item["answers"],
                        context=context,
                    )

            # 4) Үлгі контексттер (5 үлгі сұрақтан)
            for template in demo["contexts"]:
                context = Context.objects.create(
                    subject=subject,
                    language=language,
                    title=template["title"][language],
                    text=template["text"][language],
                    is_demo=True,
                )
                for index, (number, level) in enumerate(
                    zip(template["subtopics"], CONTEXT_LEVELS), start=1
                ):
                    text = TEMPLATE_TEXT[language].format(
                        subtopic=number, level=level, index=index
                    )
                    create_question(
                        subtopics[number],
                        language,
                        level,
                        text,
                        template_answers(language),
                        context=context,
                    )

        question_count = demo_questions.count()
        context_count = Context.objects.filter(is_demo=True, subject=subject).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{subject.code}: жүктелді {question_count} демо сұрақ, "
                f"{context_count} демо контекст."
            )
        )
