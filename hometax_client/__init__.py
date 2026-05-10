"""hometax_client — 홈택스 HTTP 직접 호출 라이브러리.

브라우저 없이 카카오/공인인증서 세션 쿠키 + ``nts_encrypt`` 만으로 홈택스를
다룬다. 세션 자체의 발급(인증)은 범위 밖 — Playwright 등으로 한 번 받아
``cookies.json`` 으로 넘겨주는 것을 가정한다 (``HometaxClient.from_cookies``).

기본 사용::

    from hometax_client import HometaxClient

    client = HometaxClient.from_cookies(
        cookies_path="captures/<...>/cookies.json",
        user_id="<홈택스 ID>",
        tin="<납세자통합관리번호>",
    )
    info = client.session_info()
    print(info.user_name, info.tin)

    statements = client.inquiries.income_statements(attr_year=2024)
    filings = client.inquiries.tax_filings(start="20240101", end="20241231")
    income = client.income_tax.income_details(attr_year=2024)
"""

from . import auth, facts
from .client import HometaxClient
from .crypto import nts_encrypt, nts_report_signature
from .exceptions import (
    AuthGradeInsufficientError,
    BlockedError,
    BusinessAccountUnsupportedError,
    HometaxError,
    LoginRequiredError,
    ProtectedLoginError,
    ResponseSchemaDriftError,
    SessionExpiredError,
    UnknownResponseError,
    ValidationError,
    WqActionFailedError,
)
from .models import IncomeStatement, SessionInfo, TaxFiling
from .sessions import SessionEntry, SessionHealth, SessionStore

__all__ = [
    # Client
    "HometaxClient",
    # Crypto
    "nts_encrypt",
    "nts_report_signature",
    # Sub-packages
    "auth",
    "facts",
    # Models
    "SessionInfo",
    "IncomeStatement",
    "TaxFiling",
    # Sessions
    "SessionStore",
    "SessionEntry",
    "SessionHealth",
    # Errors
    "HometaxError",
    "WqActionFailedError",
    "SessionExpiredError",
    "ValidationError",
    "LoginRequiredError",
    "AuthGradeInsufficientError",
    "BusinessAccountUnsupportedError",
    "BlockedError",
    "UnknownResponseError",
    "ResponseSchemaDriftError",
    "ProtectedLoginError",
]
