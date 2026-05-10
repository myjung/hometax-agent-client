"""홈택스 서비스 영역별 thin wrappers.

각 모듈은 한 종류의 세목/메뉴 영역을 다룬다. 모든 서비스는 ``HometaxClient``
를 받는 공통 패턴(``ServiceBase``)을 따른다. 호출은 ``client.<service>.<method>()``
형태로 일관되게 노출된다.

새 세목 추가 가이드는 ``docs/extending.md`` 참조.
"""

from .income_tax import IncomeTaxService, MaterialKind
from .inquiries import InquiryService

__all__ = [
    "InquiryService",
    "IncomeTaxService",
    "MaterialKind",
]
