"""
Payment Gateway Service — Multi-Provider
Mendukung: Xendit (VA/QRIS/E-Wallet), BCA SNAP (Virtual Account), BRI BRIVA
Semua provider menggunakan unified interface create_payment().

CATATAN:
  - BCA & BRI memerlukan kontrak resmi dengan bank (bukan API publik)
  - Xendit: daftar di https://xendit.co → dapatkan Secret Key & Webhook Token
  - Semua callback/webhook memanggil _after_paid_actions() yang sudah ada
"""
import hashlib
import hmac
import logging
import time
import base64
import json
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# BASE
# ══════════════════════════════════════════════════════════════════════════════

class PaymentGatewayError(Exception):
    """Base exception untuk semua payment gateway error."""
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# XENDIT GATEWAY
# Docs: https://developers.xendit.co/api-reference/
# ══════════════════════════════════════════════════════════════════════════════

class XenditGateway:
    """
    Xendit payment gateway — supports Virtual Account, QRIS, dan E-Wallet.
    Autentikasi: HTTP Basic Auth dengan Secret Key sebagai username, password kosong.
    """
    BASE_URL = "https://api.xendit.co"

    def __init__(self, secret_key: str, webhook_token: str = ""):
        self.secret_key = secret_key
        self.webhook_token = webhook_token
        # Basic auth: base64(secret_key + ":")
        credentials = f"{secret_key}:"
        self._auth = base64.b64encode(credentials.encode()).decode()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Basic {self._auth}",
            "Content-Type": "application/json",
        }

    async def create_virtual_account(
        self,
        external_id: str,
        bank_code: str,
        name: str,
        expected_amount: int,
        expiration_date: Optional[str] = None,
    ) -> dict:
        """
        Buat Virtual Account (Closed VA — nominal tetap).
        Bank codes: BCA, BNI, BRI, MANDIRI, PERMATA, BSI, BJB, SAHABAT_SAMPOERNA
        """
        payload = {
            "external_id": external_id,
            "bank_code": bank_code.upper(),
            "name": name[:50],  # Xendit max 50 chars
            "expected_amount": expected_amount,
            "is_closed": True,
            "is_single_use": True,
        }
        if expiration_date:
            payload["expiration_date"] = expiration_date

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/callback_virtual_accounts",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "provider": "xendit",
                    "type": "virtual_account",
                    "bank_code": bank_code.upper(),
                    "account_number": data.get("account_number", ""),
                    "external_id": external_id,
                    "amount": expected_amount,
                    "expiration_date": data.get("expiration_date", ""),
                    "status": "pending",
                    "raw": data,
                }
        except httpx.HTTPStatusError as e:
            err_body = {}
            try:
                err_body = e.response.json()
            except Exception:
                pass
            raise PaymentGatewayError(
                f"Xendit VA error: {e.response.status_code} — {err_body.get('message', str(e))}"
            )

    async def create_qris(
        self,
        reference_id: str,
        amount: int,
        description: str = "",
        expires_seconds: int = 3600,
    ) -> dict:
        """Buat QRIS (QR Code) via Xendit QR Code API."""
        payload = {
            "reference_id": reference_id,
            "type": "DYNAMIC",
            "currency": "IDR",
            "amount": amount,
            "expires_at": (
                datetime.fromtimestamp(
                    time.time() + expires_seconds, tz=timezone.utc
                ).isoformat()
            ),
        }
        if description:
            payload["description"] = description[:255]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/qr_codes",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "provider": "xendit",
                    "type": "qris",
                    "qr_string": data.get("qr_string", ""),
                    "reference_id": reference_id,
                    "amount": amount,
                    "expires_at": data.get("expires_at", ""),
                    "status": "pending",
                    "raw": data,
                }
        except httpx.HTTPStatusError as e:
            err_body = {}
            try:
                err_body = e.response.json()
            except Exception:
                pass
            raise PaymentGatewayError(
                f"Xendit QRIS error: {e.response.status_code} — {err_body.get('message', str(e))}"
            )

    async def create_ewallet(
        self,
        reference_id: str,
        amount: int,
        ewallet_type: str,
        success_redirect_url: str = "",
        failure_redirect_url: str = "",
        mobile_number: str = "",
    ) -> dict:
        """
        Buat E-Wallet charge.
        ewallet_type: GOPAY, OVO, DANA, SHOPEEPAY, LINKAJA
        """
        payload = {
            "reference_id": reference_id,
            "currency": "IDR",
            "amount": amount,
            "checkout_method": "ONE_TIME_PAYMENT",
            "channel_code": ewallet_type.upper(),
            "channel_properties": {
                "success_redirect_url": success_redirect_url or "https://example.com/success",
                "failure_redirect_url": failure_redirect_url or "https://example.com/failure",
            },
        }
        if mobile_number and ewallet_type.upper() in ("OVO", "DANA"):
            payload["channel_properties"]["mobile_number"] = mobile_number

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/ewallets/charges",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                actions = data.get("actions", {})
                return {
                    "provider": "xendit",
                    "type": "ewallet",
                    "ewallet_type": ewallet_type.upper(),
                    "reference_id": reference_id,
                    "amount": amount,
                    "checkout_url": actions.get("desktop_web_checkout_url")
                        or actions.get("mobile_web_checkout_url")
                        or actions.get("mobile_deeplink_checkout_url", ""),
                    "status": data.get("status", "pending"),
                    "raw": data,
                }
        except httpx.HTTPStatusError as e:
            err_body = {}
            try:
                err_body = e.response.json()
            except Exception:
                pass
            raise PaymentGatewayError(
                f"Xendit E-Wallet error: {e.response.status_code} — {err_body.get('message', str(e))}"
            )

    def verify_webhook_token(self, token_header: str) -> bool:
        """Verifikasi x-callback-token dari Xendit webhook."""
        if not self.webhook_token:
            return True  # Jika token belum dikonfigurasi, loloskan (development mode)
        return hmac.compare_digest(self.webhook_token, token_header or "")

    async def get_va_status(self, external_id: str) -> str:
        """Cek status VA berdasarkan external_id. Return: 'pending' | 'paid' | 'expired'"""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/callback_virtual_accounts/payments/",
                    headers=self._headers(),
                    params={"external_id": external_id},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        return "paid"
        except Exception:
            pass
        return "pending"


# ══════════════════════════════════════════════════════════════════════════════
# BCA GATEWAY (BCA SNAP API)
# Docs: https://developer.bca.co.id/documentation
# Memerlukan pendaftaran sebagai BCA Partner/Merchant
# ══════════════════════════════════════════════════════════════════════════════

class BcaGateway:
    """
    BCA SNAP API — Virtual Account BCA.
    Otentikasi: OAuth 2.0 (Client Credentials) + Request Signature (HMAC-SHA512).
    PERHATIAN: Memerlukan Company Code & registrasi resmi di BCA Developer Portal.
    """
    # Production: https://devapi.bca.co.id   |   Sandbox: https://sandbox.bca.co.id
    BASE_URL = "https://devapi.bca.co.id"

    def __init__(self, client_id: str, client_secret: str, company_code: str, api_key: str = "", api_secret: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.company_code = company_code
        self.api_key = api_key
        self.api_secret = api_secret
        self._access_token: Optional[str] = None
        self._token_expires: float = 0

    async def _get_access_token(self) -> str:
        """Dapatkan OAuth access token dari BCA."""
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/api/oauth/token",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                )
                resp.raise_for_status()
                data = resp.json()
                self._access_token = data["access_token"]
                self._token_expires = time.time() + int(data.get("expires_in", 3600))
                return self._access_token
        except Exception as e:
            raise PaymentGatewayError(f"BCA OAuth error: {e}")

    def _sign_request(self, access_token: str, http_method: str, path: str, body_str: str, timestamp: str) -> str:
        """Generate BCA request signature (HMAC-SHA256)."""
        # BCA Signature: method + ":" + path + ":" + access_token + ":" + sha256_body + ":" + timestamp
        body_hash = hashlib.sha256(body_str.encode()).hexdigest().lower()
        string_to_sign = f"{http_method}:{path}:{access_token}:{body_hash}:{timestamp}"
        signature = hmac.new(
            self.api_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature

    async def create_virtual_account(
        self,
        invoice_number: str,
        customer_name: str,
        amount: int,
        expired_date: str = "",
    ) -> dict:
        """
        Buat Virtual Account BCA via SNAP API.
        invoice_number dipakai sebagai external_id dan SubCompanyCode.
        """
        access_token = await self._get_access_token()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        path = "/banking/v2/corporates/va"

        # Nomor VA: Company Code (5 digit) + nomor unik (up to 12 digit)
        va_number_suffix = "".join(filter(str.isdigit, invoice_number))[:10].zfill(10)
        va_number = f"{self.company_code}{va_number_suffix}"

        payload = {
            "CompanyCode": self.company_code,
            "CustomerName": customer_name[:40],
            "CustomerNumber": va_number,
            "Amount": str(amount),
            "CurrencyCode": "IDR",
            "ExpiredDate": expired_date or "",
            "FreeText1": invoice_number,
        }
        body_str = json.dumps(payload, separators=(",", ":"))
        signature = self._sign_request(access_token, "POST", path, body_str, timestamp)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Origin": "www.bca.co.id",
            "X-BCA-Key": self.api_key,
            "X-BCA-Timestamp": timestamp,
            "X-BCA-Signature": signature,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    content=body_str,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "provider": "bca",
                    "type": "virtual_account",
                    "bank_code": "BCA",
                    "account_number": va_number,
                    "external_id": invoice_number,
                    "amount": amount,
                    "status": "pending",
                    "raw": data,
                }
        except httpx.HTTPStatusError as e:
            err_body = {}
            try:
                err_body = e.response.json()
            except Exception:
                pass
            raise PaymentGatewayError(
                f"BCA VA error: {e.response.status_code} — {err_body}"
            )

    def verify_callback_signature(self, request_body: bytes, signature_header: str, timestamp: str) -> bool:
        """Verifikasi signature callback BCA SNAP."""
        try:
            body_hash = hashlib.sha256(request_body).hexdigest().lower()
            string_to_sign = f"POST:/banking/v2/corporates/va/payments:{self._access_token}:{body_hash}:{timestamp}"
            expected = hmac.new(
                self.api_secret.encode(),
                string_to_sign.encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature_header or "")
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════════
# BRI GATEWAY (BRI BRIVA API)
# Docs: https://developers.bri.co.id/documentation
# Memerlukan registrasi di BRI Partner Portal
# ══════════════════════════════════════════════════════════════════════════════

class BriGateway:
    """
    BRI BRIVA (BRI Virtual Account) API.
    Otentikasi: OAuth 2.0 + HMAC Signature.
    PERHATIAN: Memerlukan institution code & registrasi resmi di developer.bri.co.id
    """
    BASE_URL = "https://partner.api.bri.co.id"

    def __init__(self, client_id: str, client_secret: str, institution_code: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.institution_code = institution_code
        self._access_token: Optional[str] = None
        self._token_expires: float = 0

    async def _get_access_token(self) -> str:
        """Dapatkan OAuth2 token dari BRI."""
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/oauth/client_credential/accesstoken",
                    params={"grant_type": "client_credentials"},
                    headers={
                        "Accept": "application/json",
                        "Consumer-Key": self.client_id,
                        "Consumer-Secret": self.client_secret,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self._access_token = data["access_token"]
                self._token_expires = time.time() + int(data.get("expires_in", 3600))
                return self._access_token
        except Exception as e:
            raise PaymentGatewayError(f"BRI OAuth error: {e}")

    def _sign_request(self, method: str, path: str, body_str: str, timestamp: str) -> str:
        """Generate BRI HMAC-SHA256 signature."""
        body_hash = hashlib.sha256(body_str.encode()).hexdigest()
        string_to_sign = f"{method}:{path}:{body_hash}:{timestamp}"
        return hmac.new(
            self.client_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def create_virtual_account(
        self,
        invoice_number: str,
        customer_name: str,
        amount: int,
        description: str = "",
    ) -> dict:
        """
        Buat BRIVA (Virtual Account BRI).
        Nomor BRIVA: Institution Code (5 digit) + 9 digit unik.
        """
        access_token = await self._get_access_token()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+07:00")

        briva_number_suffix = "".join(filter(str.isdigit, invoice_number))[-9:].zfill(9)
        briva_number = f"{self.institution_code}{briva_number_suffix}"

        path = "/v1/briva"
        payload = {
            "institutionCode": self.institution_code,
            "brivaNo": briva_number,
            "custCode": briva_number_suffix,
            "nama": customer_name[:40],
            "amount": str(amount),
            "keterangan": description or invoice_number,
            "expiredDate": "",
        }
        body_str = json.dumps(payload)
        signature = self._sign_request("POST", path, body_str, timestamp)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "BRI-Timestamp": timestamp,
            "BRI-Signature": signature,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.BASE_URL}{path}",
                    headers=headers,
                    content=body_str,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "provider": "bri",
                    "type": "virtual_account",
                    "bank_code": "BRI",
                    "account_number": briva_number,
                    "external_id": invoice_number,
                    "amount": amount,
                    "status": "pending",
                    "raw": data,
                }
        except httpx.HTTPStatusError as e:
            err_body = {}
            try:
                err_body = e.response.json()
            except Exception:
                pass
            raise PaymentGatewayError(
                f"BRI BRIVA error: {e.response.status_code} — {err_body}"
            )

    def verify_callback_hmac(self, request_body: bytes, hmac_header: str, timestamp: str) -> bool:
        """Verifikasi HMAC callback BRI."""
        try:
            body_str = request_body.decode("utf-8")
            path = "/v1/briva/callback"
            expected = self._sign_request("POST", path, body_str, timestamp)
            return hmac.compare_digest(expected, hmac_header or "")
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED FACTORY
# ══════════════════════════════════════════════════════════════════════════════

async def create_payment(
    provider: str,
    payment_type: str,
    invoice: dict,
    customer: dict,
    settings: dict,
    **kwargs,
) -> dict:
    """
    Unified gateway interface.

    Args:
        provider: "xendit" | "bca" | "bri"
        payment_type: "virtual_account" | "qris" | "ewallet"
        invoice: dict invoice dari MongoDB
        customer: dict customer dari MongoDB
        settings: billing_settings dari MongoDB
        **kwargs: extra args (bank_code, ewallet_type, dll)

    Returns:
        dict dengan payment_info yang siap disimpan ke DB dan ditampilkan di UI
    """
    invoice_number = invoice.get("invoice_number", invoice.get("id", "")[:8].upper())
    external_id = f"{invoice_number}-{int(time.time())}"
    amount = invoice.get("total", 0)
    customer_name = customer.get("name", "Pelanggan")

    if provider == "xendit":
        gw = XenditGateway(
            secret_key=settings.get("xendit_secret_key", ""),
            webhook_token=settings.get("xendit_webhook_token", ""),
        )
        if payment_type == "virtual_account":
            bank_code = kwargs.get("bank_code") or settings.get("xendit_va_bank", "BNI")
            return await gw.create_virtual_account(
                external_id=external_id,
                bank_code=bank_code,
                name=customer_name,
                expected_amount=amount,
            )
        elif payment_type == "qris":
            return await gw.create_qris(
                reference_id=external_id,
                amount=amount,
                description=f"Tagihan {invoice_number}",
            )
        elif payment_type == "ewallet":
            ewallet_type = kwargs.get("ewallet_type", "GOPAY")
            return await gw.create_ewallet(
                reference_id=external_id,
                amount=amount,
                ewallet_type=ewallet_type,
                mobile_number=customer.get("phone", ""),
            )

    elif provider == "bca":
        gw = BcaGateway(
            client_id=settings.get("bca_client_id", ""),
            client_secret=settings.get("bca_client_secret", ""),
            company_code=settings.get("bca_company_code", ""),
            api_key=settings.get("bca_api_key", ""),
            api_secret=settings.get("bca_api_secret", ""),
        )
        return await gw.create_virtual_account(
            invoice_number=invoice_number,
            customer_name=customer_name,
            amount=amount,
        )

    elif provider == "bri":
        gw = BriGateway(
            client_id=settings.get("bri_client_id", ""),
            client_secret=settings.get("bri_client_secret", ""),
            institution_code=settings.get("bri_institution_code", ""),
        )
        return await gw.create_virtual_account(
            invoice_number=invoice_number,
            customer_name=customer_name,
            amount=amount,
            description=f"Tagihan {invoice_number}",
        )

    raise PaymentGatewayError(f"Provider tidak dikenal: {provider}")


def get_gateway_instance(provider: str, settings: dict):
    """Factory untuk mendapatkan instance gateway dari settings DB."""
    if provider == "xendit":
        return XenditGateway(
            secret_key=settings.get("xendit_secret_key", ""),
            webhook_token=settings.get("xendit_webhook_token", ""),
        )
    elif provider == "bca":
        return BcaGateway(
            client_id=settings.get("bca_client_id", ""),
            client_secret=settings.get("bca_client_secret", ""),
            company_code=settings.get("bca_company_code", ""),
            api_key=settings.get("bca_api_key", ""),
            api_secret=settings.get("bca_api_secret", ""),
        )
    elif provider == "bri":
        return BriGateway(
            client_id=settings.get("bri_client_id", ""),
            client_secret=settings.get("bri_client_secret", ""),
            institution_code=settings.get("bri_institution_code", ""),
        )
    raise PaymentGatewayError(f"Provider tidak dikenal: {provider}")
