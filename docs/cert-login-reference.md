# 공인인증서(NPKI) 로그인 참고 — `hometax-scraper` 분석

본 라이브러리에서 **아직 미구현** 인 NPKI 공인인증서 인증 흐름의 참고
자료. 사용자의 옛 프로젝트 `hometax-scraper` (2022 ~ 2023 분량) 에 동작
했던 흐름이 남아 있어, 향후 `auth/cert.py` 추가 시 출발점으로 활용한다.

> ⚠️ **검증 시점 주의.** 옛 코드는 2026-05 의 `pubcLogin` 보호 스크립트
> 변경 이전에 작성되었다. 그 시점에는 직접 form POST 가 통과했지만,
> 2026-05 이후 같은 흐름이 그대로 동작한다는 보장은 없다. 본 라이브러리
> 도입 전 **새 캡처로 재검증** 필요.

---

## 1. 흐름 요약

세무대리인(또는 사용자) 로그인은 **2단계** 로 진행된다.

```
Step A   POST /pubcLogin.do                    ← ID/PW (1차)
         body: {id, pswd, ssoLoginYn, scrnId=UTXPPABA01, ...}
         응답 'code':'S'  →  1차 통과
                'code':'F'  →  실패 (decodeURI/decodeURIComponent 메시지)

Step B   POST /wqAction.do?actionId=ATXPPZXA001R01&screenId=UTXPPABA01
         body: '<map id="ATXPPZXA001R01"></map>'
         응답 본문에 <pkcEncSsn>...</pkcEncSsn> 포함  ← 서버 챌린지

Step C   인증서로 챌린지 서명 후 다시 pubcLogin
         POST /pubcLogin.do?domain=hometax.go.kr&mainSys=Y
         body: {logSgnt, cert, randomEnc, pkcLoginYnImpv=Y, ...}
         응답 'code':'S'  →  최종 로그인 성공
```

핵심은 **첫 번째 pubcLogin (id/pswd) 만으로는 세무대리 메뉴 진입이
불가능**하고, 그 뒤의 인증서 챌린지/응답까지 통과해야 등급이 올라간다는
점.

## 2. 인증서 입력

### 인증서 파일 위치 (Windows 기준)

```
%userprofile%\AppData\LocalLow\NPKI\yessign\User\<cert_id>\
├── SignCert.der    ← 공개키 (PUBLIC_CERT_NAME)
└── SignPri.key     ← 암호화된 개인키 (PRIVATE_CERT_NAME)
```

`yessign` 는 가장 흔한 한국 NPKI CA. `SignCert.der`/`SignPri.key` 는
NPKI 전체에서 공통 파일명. macOS/Linux 에서는 사용자가 cert 디렉터리를
직접 옮겨 와야 한다 (옛 코드는 Windows 만 가정).

### `pypinksign` 으로 cert 객체 생성

```python
import pypinksign

cert = pypinksign.PinkSign(
    pubkey_path="/path/to/SignCert.der",
    prikey_path="/path/to/SignPri.key",
    prikey_password=cert_password.encode("utf8"),  # bytes
)
```

`PinkSign` 객체는 다음 메서드 / 속성 노출:

- `cert.pub_cert.public_bytes(PEM)` → PEM-encoded 인증서 bytes
- `cert.serialnum()` → 시리얼 정수 (헥사 변환해 `serial_num` 필드)
- `cert.sign(message_bytes)` → 개인키로 서명, bytes 반환
- `cert._rand_num` → 인증서 객체의 ASN.1 Random number (논스)

## 3. Step A — ID/PW 1차 (옛 형식)

옛 `hometax-scraper:193` `_login_agent`:

```python
id_encoded = base64.b64encode(self.id.encode("utf8"))
                  .decode("utf8")
                  .replace("=", "")               # padding 제거 ← 옛 형식
pw_hashed_encoded = base64.b64encode(
    hashlib.sha256(self.pw.encode("utf8"))
           .hexdigest()
           .upper()
           .encode("utf8"),
).decode("utf8")

data = {
    "ssoLoginYn": "Y",
    "secCardLoginYn": "",
    "secCardId": "",
    "cncClCd": "01",
    "id": id_encoded,
    "pswd": pw_hashed_encoded,
    "ssoStatus": "",
    "portalStatus": "",
    "scrnId": "UTXPPABA01",
    "userScrnRslnXcCnt": 1920,
    "userScrnRslnYcCnt": 1080,
}
session.post(
    "https://hometax.go.kr/pubcLogin.do?domain=hometax.go.kr&mainSys=Y",
    data,
)
```

### 현재 IdPwAuth 와의 차이

| 항목 | 옛 hometax-scraper | 현 hometax-agent-client `IdPwAuth` |
|---|---|---|
| `pswd` 인코딩 | `base64(sha256(pw).upper())` | `base64(pw)` (평문 base64) |
| `id` 인코딩 | `base64(id).replace("=","")` | `base64(id)` (R07 응답 보정값 우선) |
| 사전 검증 | 없음 | `ATXPPABA001R07` 통과 필수 |
| 2차 인증 (sq2) | 없음 | `txprDscmNo` 주민번호 7자리 |

→ **홈택스가 옛 SHA256-uppercase 인코딩에서 R07 사전검증 + 평문 base64
방식으로 마이그레이션** 했음을 알 수 있다. 현 `IdPwAuth` 는 새 방식을
따르므로 이 부분은 그대로 둔다.

## 4. Step B — 인증서 챌린지(`pkcEncSsn`) 가져오기

옛 `hometax-scraper:254` `_cert_login`:

```python
url = "https://hometax.go.kr/wqAction.do"
params = {
    "actionId": "ATXPPZXA001R01",
    "screenId": "UTXPPABA01",
}
data = '<map id="ATXPPZXA001R01"></map>'
headers = {
    "Accept": "application/xml; charset=UTF-8",
    "Referer": (
        "https://hometax.go.kr/websquare/websquare.wq"
        "?w2xPath=/ui/comm/a/b/UTXPPABA01.xml"
        "&w2xHome=/ui/pp/&w2xDocumentRoot="
    ),
}
r = session.post(url, params=params, data=data, headers=headers)
# r.text 에 <pkcEncSsn>{base64-blob}</pkcEncSsn> 포함

pkc_enc_ssn = parser.substring(r.text, "<pkcEncSsn>", "</pkcEncSsn>")
```

응답 형식이 옛 코드 시점엔 XML 이었다. 현재(2026-04 캡처)는 wqAction
응답이 JSON 으로 마이그레이션된 액션이 많아 (`hometax-facts.md` §12),
**이 액션의 응답이 JSON 으로 바뀌었는지 재확인 필요**.

`pkcEncSsn` 은 보통 base64-encoded 임의 바이트열 (서버가 서명 대상으로
던지는 challenge).

> ⚠️ 옛 코드는 wqAction 본문에 `nts_encrypt(...)` 서명을 부착하지 않은
> 채로 호출했다. 현재 hometax 는 거의 모든 wqAction 호출에 nts_encrypt
> 서명을 요구하므로, 새로 구현 시 본 라이브러리의 `nts_encrypt` 를
> 부착해야 할 가능성이 높다.

## 5. Step C — 챌린지 서명 + 인증서 로그인

옛 `hometax-scraper:91` `LoginInfo.get_hometax_cert_login_info`:

```python
def get_hometax_cert_login_info(
    self, pkc_enc_ssn: str,
) -> tuple[str, str, str]:
    cert_der = self.cert.pub_cert.public_bytes(
        CryptoEncoding.PEM,
    ).decode("utf8")

    serial_num = hex(self.cert.serialnum())[2:]
    current_time = datetime.now(KST).strftime("%Y%m%d%H%M%S")
    signed = base64.b64encode(
        self.cert.sign(pkc_enc_ssn.encode("utf8")),
    ).decode("utf8")

    sgnt_plain = (
        f"{pkc_enc_ssn}${serial_num}${current_time}${signed}"
    )
    log_sgnt = base64.b64encode(
        sgnt_plain.encode("utf8"),
    ).decode("utf8")

    rand_num = base64.b64encode(
        bitstring_to_bytes(self.cert._rand_num.asBinary()),
    ).decode("utf8")
    return log_sgnt, cert_der, rand_num
```

여기서 **서명 메시지의 형식** 이 핵심:

```
sgnt_plain = "{pkcEncSsn}${serial_num}${YYYYMMDDhhmmss}${base64(sign(pkcEncSsn))}"
log_sgnt   = base64(sgnt_plain)
```

`$` 구분자가 4개 필드를 결합. 시간은 KST 기준 14자리. 서명은 NPKI 개인
키로 `pkcEncSsn` 자체를 서명한 결과 (PKCS#1 RSA SHA1/SHA256 — pypinksign
default).

`rand_num` 은 인증서 내부 random ASN.1 bitstring 을 bytes 로 풀어 base64.
NPKI 인증서 객체의 부속 nonce 로 보임.

### 그리고 두 번째 pubcLogin 호출:

```python
url = "https://hometax.go.kr/pubcLogin.do?domain=hometax.go.kr&mainSys=Y"
data = {
    "logSgnt": log_sgnt,
    "cert": cert_der,                # PEM-encoded 인증서
    "randomEnc": rand_num,
    "pkcLoginYnImpv": "Y",           # 인증서 로그인 플래그
    "ssoStatus": "",
    "portalStatus": "",
    "scrnId": "UTXPPABA01",
    "userScrnRslnXcCnt": 1280,
    "userScrnRslnYcCnt": 1024,
}
r = session.post(url, data)
# 'code':'S' 면 성공. 그 외 실패 메시지는 decodeURI/decodeURIComponent.
```

이 시점 응답이 OK 면 세션 쿠키(`TXPPsessionID`, `JSESSIONID` 등)가 jar
에 박혀 있고, 이후 `wqAction.do` 호출은 ID/PW 단독보다 **상위 등급**으로
동작한다 (세무대리인 권한 메뉴 등 접근 가능).

## 6. 헬퍼 함수 — `bitstring_to_bytes`

`hometax-scraper:63`:

```python
def bitstring_to_bytes(s: str) -> bytes:
    """ASN.1 bitstring (e.g. '01010110...') → bytes (big-endian)."""
    v = int(s, 2)
    b = bytearray()
    while v:
        b.append(v & 0xFF)
        v >>= 8
    return bytes(b[::-1])
```

`pypinksign` 의 `_rand_num.asBinary()` 가 ASN.1 bitstring 형식의 문자열을
돌려주므로 이걸 raw bytes 로 풀어주는 헬퍼.

## 7. 의존성

옛 코드의 인증서 처리 의존성 (현재 라이브러리에는 없음):

```toml
pypinksign      # NPKI cert 객체 + 서명
cryptography    # PEM 변환
pyopenssl       # pypinksign 의 transitive
pyasn1          # ASN.1 디코더 (pypinksign transitive)
pycryptodomex   # AES 등 (utils.decrypt_ztax_regis_number 에서 사용)
```

신규 `auth/cert.py` 추가 시 `[cert]` extras 로 격리 후보:

```toml
[project.optional-dependencies]
cert = ["pypinksign>=0.5", "cryptography>=42"]
```

## 8. 예상 인터페이스 (미구현 — 가이드라인)

본 라이브러리에 추가한다면 `OACXAuth` / `IdPwAuth` 와 동일한 인터페이스
패턴:

```python
# hometax_client/auth/cert.py
@dataclass
class CertAuthResult:
    user_id: str
    tin: str | None
    cookies: dict[str, str]


class CertAuth:
    """공인인증서(NPKI) 로그인.

    세무대리인 ID/PW 1차 + 인증서 서명 2차 흐름.
    """

    def __init__(
        self,
        *,
        user_id: str,
        password: str,
        cert_dir: Path,             # SignCert.der + SignPri.key 가 든 폴더
        cert_password: str,
        impersonate: str = "chrome",
    ) -> None:
        ...

    def authenticate(self) -> CertAuthResult:
        # 1. _prime_login_context()
        # 2. step_a_idpw_login()
        # 3. step_b_fetch_pkc_enc_ssn()
        # 4. step_c_cert_signed_login()
        ...

    def to_client(self, ...) -> HometaxClient:
        ...
```

`HometaxClient.login(auth=CertAuth(...))` 로 OACX/IdPw 와 동일하게 진입.

## 9. 현재 시점 검증 필요 항목

옛 `hometax-scraper` 가 동작했던 시점과 현재(2026-05) 사이의 변경 가능
지점:

| 항목 | 검증 방법 |
|---|---|
| Step A pubcLogin 본문이 옛 SHA256 형식 vs 현 base64 평문 | 지금은 평문 base64 일 가능성 높음 (`IdPwAuth` 와 동일). 캡처로 확인. |
| Step B `ATXPPZXA001R01` 응답 포맷 (XML/JSON) | 현 hometax 는 대부분 JSON 으로 마이그레이션. 직접 호출 후 `Content-Type` 확인. |
| Step B 호출 시 `nts_encrypt` 서명 필요 여부 | 현재 거의 모든 wqAction 이 서명 요구. 무서명 호출 시 거부될 가능성. |
| Step C `pubcLogin` 본문이 보호 스크립트로 wrap 되는지 | **2026-05 보호 스크립트가 cert path 에도 적용되는지가 핵심**. 적용된다면 ID/PW 와 같은 부트스트랩 우회 필요. |
| `pkcEncSsn` 챌린지 형식 / 서명 알고리즘 | 옛 코드는 PKCS#1 RSA-SHA1 (pypinksign default). 현재 RSA-SHA256 으로 바뀌었을 가능성. |
| `logSgnt` 결합 형식 (`$` 4개 필드) | 그대로일 가능성 높지만 timestamp 형식, 서명 알고리즘 변경 가능. |

## 10. 액션 카탈로그 추가 후보

`hometax_client/facts/current.toml` 에 추가될 항목:

```toml
[auth.cert]
challenge_action = "ATXPPZXA001R01"
challenge_screen = "UTXPPABA01"
challenge_field = "pkcEncSsn"
pubc_login_path = "/pubcLogin.do?domain=hometax.go.kr&mainSys=Y"
cert_login_flag = "pkcLoginYnImpv"

[auth.cert.signature_format]
# log_sgnt = base64("{pkc_enc_ssn}${serial_num}${current_time}${b64_sign}")
delimiter = "$"
time_format = "%Y%m%d%H%M%S"
```

## 11. 보안 메모

- 인증서 비밀번호 / 개인키 / `SignPri.key` 자체는 **메모리 외부에 절대
  쓰지 않는다.** 라이브러리 입장에선 호출 측에서 받아 그대로 사용.
- `cert_dir` 와 `cert_password` 는 환경변수 / OS 키링 / GUI 부트스트랩
  도구로만 받는 것을 권장.
- 인증서 로그인 세션은 ID/PW 보다 등급이 높으므로 캐시 파일 보안에 더
  주의 (이미 `0o600` + `.gitignore` 처리되어 있지만 운영 시 추가 정책
  필요).

## 12. 우선순위 / 다음 액션

본 문서는 참고용이며, 즉시 구현 대상은 아니다. 다음 순서를 권장:

1. **pubcLogin 보호 스크립트 RE 또는 부트스트랩 도구** 가 먼저
   (ID/PW 가 안 풀리면 인증서도 같은 보호 layer 에 막힐 가능성).
2. 보호 스크립트 우회 방법이 정해지면 그 위에 `CertAuth` 추가.
3. `pkcEncSsn` 챌린지 + `logSgnt` 형식이 변경되었는지 새 캡처로 검증.
4. `pypinksign` 또는 더 가벼운 NPKI 라이브러리로 cert 객체 처리.
5. `[cert]` extras 로 격리 (core 의존성 늘리지 않음).

## 13. 참고 — 옛 코드의 함정들

향후 작업 시 그대로 가져오지 말 것:

- `constants.py:9` `YESSIGN_CERT_PATH = os.path.join(os.getenv("userprofile"), ...)` — Windows 전제. macOS/Linux 에서는 ``NoneType`` 으로 import 단계 에러.
- `main.py:706-770` 에 자격증명 + cert 경로 + cert 비밀번호가 **하드코딩**. 운영용 파일 아님, 단순 개발 테스트용. 새 구현은 환경변수/입력으로만.
- `user.py` 의 `request_login_by_public_cert` 메서드명은 **misleading** — 실제로는 OACX 카카오 인증을 수행한다 (인증서 아님). 이름에 속아 그 코드를 cert 참조로 쓰지 말 것.
- 옛 코드의 `requests.Session()` 직접 사용은 현 hometax 의 TLS fingerprint 검사를 통과 못 할 수 있음. 새 구현은 본 라이브러리처럼 `curl_cffi` 를 사용해야 안전.
- `Parser.substring(...)` 헬퍼는 단순 문자열 슬라이스. 응답이 JSON 으로 바뀐 부분에서는 사용 불가.
