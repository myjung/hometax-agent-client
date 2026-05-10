"""카카오 간편인증 (``kakao_v1.5``)."""

from __future__ import annotations

from .oacx import OACXAuth


class KakaoAuth(OACXAuth):
    PROVIDER_ID = "kakao"
    PROVIDER = "kakao_v1.5"
    NETFUNNEL_AID = "simple_cert_kakao"
