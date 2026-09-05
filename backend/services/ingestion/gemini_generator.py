"""Generates lesson documentation + quizzes via Google Gemini (gemini-3.6-flash),
for the standalone lesson-content pipeline (course_code -> lessons, sourced from
courses_db.json / the "LearnWise - база извори" spreadsheet).

Not used by any live API request path - like the rest of backend/services/ingestion/,
this only runs from a standalone script, never triggered by a user's chat request.
Separate from backend/ai/chat.py on purpose: that module is the live tutor (Groq),
this one is an offline content-generation job (Gemini).

Pipeline assumptions this module is built around:
  1. Source text extraction (PDF -> text, HTML -> text) happens ONCE, upfront, for
     each source in courses_db.json, and is cached (e.g. in a future `source_texts`
     table or file storage) - NOT on every call to generate_documentation().
  2. For each lesson, before generating, the relevant chunk of the already-cached
     source text is selected - not the whole book, just the part matching the
     lesson's topic (a manually-marked page range, or found via simple
     search/title-similarity). That chunking/selection step is not implemented
     here yet - generate_documentation() takes the excerpt as a plain string.
  3. Documentation is generated FIRST. The quiz is generated SECOND, based on the
     already-generated documentation (not directly on the source) - so the quiz
     stays consistent with what the student actually reads.

Neither prompt is allowed to produce citations/references the model invents itself -
the source (title, author, URL) is always added programmatically by the backend
(from courses_db.json), never asked of the model.

Status: this is the setup/scaffolding step - the two generate_*() functions below
make real calls against the Gemini API once GEMINI_API_KEY is set, but nothing yet
wires this up to actual source-text extraction or to the database (Lesson storage
doesn't exist yet). That's the next step.
"""
import json
import logging
from textwrap import dedent
from typing import Optional

from google import genai
from google.genai import errors as genai_errors

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Silence google-genai's one-time "use Chat.send_message instead of
# Models.generate_content" notice - harmless (we deliberately don't use
# automatic function calling or the Chat wrapper here), just noisy on every
# fresh process. Scoped to that one library logger only.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

GEMINI_MODEL = "gemini-3.6-flash"

# Hard-ish cap on documentation length (real lectures are ~50-60 slides worth
# of content, not multi-page essays) - enforced via the prompt instruction
# below, and checked (not truncated - just logged) by seed_lessons.py after
# generation, since word-count instructions aren't always followed exactly.
MAX_DOCUMENTATION_WORDS = 1000

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Lazily creates the Gemini client so importing this module doesn't require
    GEMINI_API_KEY to be set (e.g. when just running other ingestion sources)."""
    global _client
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not set - add it to your .env (see .env.example). "
            "Get one from https://aistudio.google.com/apikey"
        )
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# 1. ПРОМПТ ЗА ДОКУМЕНТАЦИЈА
# ---------------------------------------------------------------------------

def build_documentation_prompt(
    course_name_mk: str,
    lesson_title: str,
    source_excerpt: str,
    source_title: str,
    source_author: str,
) -> str:
    """
    Го гради промптот за генерирање на учебна документација за ЕДНА лекција.

    source_excerpt: веќе-извадениот, релевантен дел текст од изворот
                     (не целиот извор - само делот што одговара на темата).
    """
    return dedent(f"""
        Ти си асистент кој подготвува учебен материјал за студенти по
        компјутерски науки на македонски јазик.

        ЗАДАЧА:
        Напиши учебна документација (студиски водич) на македонски јазик за
        темата "{lesson_title}", која е дел од предметот "{course_name_mk}".

        СТРОГО ПРАВИЛО ЗА ИЗВОРИ:
        Твојата документација мора да биде базирана ИСКЛУЧИВО на текстот
        даден подолу во делот "ИЗВОРЕН ТЕКСТ". НЕ смееш да додаваш факти,
        примери, дефиниции или тврдења од сопственото претходно знаење кои
        не се потврдени во дадениот текст. Ако дадениот текст не покрива
        доволно детално некој аспект од темата, само наведи го она што е
        достапно - НЕ измислувај и НЕ пополнувај празнини со претпоставки.

        ПРАВИЛО ЗА ПРОГРАМСКА ТЕРМИНОЛОГИЈА:
        Кога во изворниот текст се појавува име на тип податок, клучен збор
        (keyword), функција, вредност или друг термин специфичен за програмски
        јазик (на пр. float, int, double, string, boolean, null, void, array),
        НЕ преведувај го самиот термин на македонски со опишана фраза (пр. НЕ
        пиши "вредност со дробен дел" наместо float, НЕ пиши "ништо" наместо
        null, НЕ пиши "лебдечка запирка" наместо float). Наместо тоа, остави
        го терминот во оригиналната латинична форма, точно како што стои во
        кодот (float, null, int...), а по потреба само кратко објасни го
        значењето на македонски веднаш до него (пр. "float - тип за броеви
        со децимален (дробен) дел"; "null - специјална вредност што
        означува отсуство на вредност"). Ова важи само за вистински
        програмски термини (типови, keywords, функции, стандардни
        вредности) - општите концепти од материјалот и понатаму објаснувај
        ги природно на македонски.

        СТИЛ И СТРУКТУРА:
        - Јасен, едноставен, педагошки тон, прилагоден за студенти.
        - Користи наслови/поднаслови за организирање на содржината.
        - Каде што е корисно, вклучи кратки примери - но само ако
          произлегуваат директно од изворниот текст.
        - Не користи изрази како "според изворот" или "текстот вели" -
          пиши директно, како нормална учебна документација.
        - Должина: НАЈМНОГУ {MAX_DOCUMENTATION_WORDS} зборови (тврд лимит -
          ова е една лекција/предавање, не поглавје од книга). Но ова е
          горна граница, не цел - НЕ додавај содржина, повторувања или
          вештачки проширувања само за да се приближиш до тој број. Ако
          темата природно бара помалку зборови за јасно да се објасни, нека
          биде пократко.
        - Пиши исклучиво на македонски јазик, дури и ако изворниот текст
          е на англиски - преведи ги концептите природно.

        ИЗВОРЕН ТЕКСТ (наслов: "{source_title}", автор: "{source_author}"):
        ---
        {source_excerpt}
        ---

        Генерирај ја документацијата сега.
    """).strip()


# ---------------------------------------------------------------------------
# 2. ПРОМПТ ЗА КВИЗ (со structured JSON output)
# ---------------------------------------------------------------------------

QUIZ_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 4,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "correct_option_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "correct_option_index", "explanation"],
            },
        }
    },
    "required": ["questions"],
}


def build_quiz_prompt(lesson_title: str, documentation_text: str) -> str:
    """
    Го гради промптот за генерирање квиз, базиран на ВЕЌЕ генерираната
    документација (не директно на изворниот текст) - за да остане
    квизот усогласен со она што студентот го читал.
    """
    return dedent(f"""
        Врз основа на следната учебна документација за темата
        "{lesson_title}", генерирај краток квиз за проверка на разбирање.

        ПРАВИЛА:
        - Помеѓу 4 и 6 прашања со по 4 понудени одговори (само еден точен).
        - Прашањата смеат да проверуваат само содржина што буквално се
          наоѓа во документацијата подолу - НЕ надворешно знаење.
        - Понудените погрешни одговори треба да бидат веродостојни
          (плаузибилни), не очигледно апсурдни.
        - За секое прашање додај кратко објаснување (1-2 реченици) зошто
          точниот одговор е точен, повикувајќи се на документацијата.
        - Прашањата и одговорите се на македонски јазик.
        - Врати го резултатот СТРОГО во JSON формат според дадената шема,
          без дополнителен текст пред/по JSON-от.

        ДОКУМЕНТАЦИЈА:
        ---
        {documentation_text}
        ---
    """).strip()


# ---------------------------------------------------------------------------
# 3. ВИСТИНСКИ ПОВИЦИ КОН GEMINI API
# ---------------------------------------------------------------------------

def documentation_word_count(documentation: str) -> int:
    return len(documentation.split())


def generate_documentation(
    course_name_mk: str,
    lesson_title: str,
    source_excerpt: str,
    source_title: str,
    source_author: str,
) -> str:
    """Generates the lesson documentation text (step 1 of the pipeline). Raises
    RuntimeError if GEMINI_API_KEY is unset, or google.genai.errors.APIError on
    an API failure (rate limit, invalid key, etc.) - callers should catch and
    log/retry as appropriate, this does not swallow errors."""
    client = _get_client()
    prompt = build_documentation_prompt(
        course_name_mk=course_name_mk,
        lesson_title=lesson_title,
        source_excerpt=source_excerpt,
        source_title=source_title,
        source_author=source_author,
    )
    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    except genai_errors.APIError:
        logger.exception("Gemini documentation generation failed for lesson '%s'", lesson_title)
        raise
    return (response.text or "").strip()


def generate_quiz(lesson_title: str, documentation_text: str) -> dict:
    """Generates the quiz (step 2 of the pipeline), based on the already-generated
    documentation, constrained to QUIZ_JSON_SCHEMA. Returns the parsed dict
    ({"questions": [...]}.  Raises RuntimeError if GEMINI_API_KEY is unset,
    google.genai.errors.APIError on an API failure, or json.JSONDecodeError if
    the model somehow returns invalid JSON despite the schema constraint."""
    client = _get_client()
    prompt = build_quiz_prompt(lesson_title=lesson_title, documentation_text=documentation_text)
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": QUIZ_JSON_SCHEMA,
            },
        )
    except genai_errors.APIError:
        logger.exception("Gemini quiz generation failed for lesson '%s'", lesson_title)
        raise
    return json.loads(response.text)
