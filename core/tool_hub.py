"""
tool_hub.py — Tool Hub: kết nối CRM/Booking/Odoo

Hiện tại: stub implementation — trả mock data
Tích hợp thật: điền BASE_URL + API_KEY của hệ thống Suối Tiên

Tools:
  check_ticket_availability  — kiểm tra slot vé còn trống
  create_booking             — tạo đơn đặt vé
  get_booking_status         — xem trạng thái đơn
  check_restaurant_table     — đặt bàn nhà hàng
  send_confirmation_email    — gửi email xác nhận
  get_crm_customer           — lấy thông tin khách hàng từ CRM/Odoo
"""
import os, logging, httpx
from datetime import datetime
from typing import Optional

logger = logging.getLogger("suoitien.tool_hub")

# ── Config — điền URL thật của hệ thống Suối Tiên ─────────────────────────────
BOOKING_API_URL = os.getenv("BOOKING_API_URL", "")
BOOKING_API_KEY = os.getenv("BOOKING_API_KEY", "")
ODOO_URL        = os.getenv("ODOO_URL", "")
ODOO_DB         = os.getenv("ODOO_DB", "")
ODOO_USER       = os.getenv("ODOO_USER", "")
ODOO_PASSWORD   = os.getenv("ODOO_PASSWORD", "")

_IS_LIVE = bool(BOOKING_API_URL and BOOKING_API_KEY)


async def _api_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(
            f"{BOOKING_API_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {BOOKING_API_KEY}"}
        )
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{BOOKING_API_URL}{path}",
            json=data,
            headers={"Authorization": f"Bearer {BOOKING_API_KEY}",
                     "Content-Type": "application/json"}
        )
        resp.raise_for_status()
        return resp.json()


# ── Public tools ───────────────────────────────────────────────────────────────

async def check_ticket_availability(
    ticket_type: str,
    visit_date: str,
    quantity: int = 1,
) -> dict:
    """Kiểm tra còn vé không cho ngày cụ thể."""
    if _IS_LIVE:
        try:
            return await _api_get("/tickets/availability", {
                "type": ticket_type, "date": visit_date, "qty": quantity
            })
        except Exception as e:
            logger.warning("Booking API error: %s", e)

    # Mock response khi chưa có API thật
    return {
        "available":      True,
        "remaining_slots": 234,
        "ticket_type":    ticket_type,
        "visit_date":     visit_date,
        "price_adult":    80000,
        "price_child":    40000,
        "buy_url":        "https://suoitien.vn/mua-ve",
        "note":           "Dữ liệu mẫu — chưa kết nối booking thật",
    }


async def create_booking(
    ticket_type: str,
    visit_date: str,
    adult_count: int,
    child_count: int = 0,
    customer_name: str = "",
    customer_phone: str = "",
    customer_email: str = "",
) -> dict:
    """Tạo đơn đặt vé."""
    if _IS_LIVE:
        try:
            return await _api_post("/bookings", {
                "ticket_type":  ticket_type,
                "visit_date":   visit_date,
                "adults":       adult_count,
                "children":     child_count,
                "name":         customer_name,
                "phone":        customer_phone,
                "email":        customer_email,
            })
        except Exception as e:
            logger.warning("Create booking error: %s", e)

    total = adult_count * 80000 + child_count * 40000
    return {
        "booking_id":    f"ST{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "status":        "pending",
        "total_amount":  total,
        "visit_date":    visit_date,
        "adults":        adult_count,
        "children":      child_count,
        "payment_url":   "https://suoitien.vn/thanh-toan",
        "note":          "Đơn mẫu — chưa kết nối hệ thống thật. Gọi 1900 636 787 để đặt.",
    }


async def get_booking_status(booking_id: str) -> dict:
    """Xem trạng thái đơn đặt."""
    if _IS_LIVE:
        try:
            return await _api_get(f"/bookings/{booking_id}")
        except Exception as e:
            logger.warning("Get booking error: %s", e)

    return {
        "booking_id": booking_id,
        "status":     "confirmed",
        "note":       "Dữ liệu mẫu",
    }


async def check_restaurant_table(
    restaurant_name: str,
    date: str,
    guests: int,
) -> dict:
    """Kiểm tra bàn nhà hàng."""
    return {
        "available":       True,
        "restaurant":      restaurant_name,
        "date":            date,
        "guests":          guests,
        "contact":         "1900 636 787",
        "note":            "Vui lòng gọi hotline để đặt bàn",
    }


async def get_crm_customer(phone: str) -> dict:
    """Lấy thông tin khách hàng từ CRM/Odoo."""
    if not (ODOO_URL and ODOO_USER):
        return {"found": False, "note": "CRM chưa kết nối"}
    try:
        import xmlrpc.client
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid    = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        records = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            "res.partner", "search_read",
            [[["phone", "=", phone]]],
            {"fields": ["name", "email", "phone"], "limit": 1}
        )
        if records:
            return {"found": True, **records[0]}
        return {"found": False}
    except Exception as e:
        logger.warning("Odoo CRM error: %s", e)
        return {"found": False, "error": str(e)}


def hub_status() -> dict:
    return {
        "booking_api": "live" if _IS_LIVE else "mock",
        "odoo_crm":    "live" if ODOO_URL else "not_configured",
        "endpoints":   [
            "check_ticket_availability",
            "create_booking",
            "get_booking_status",
            "check_restaurant_table",
            "get_crm_customer",
        ]
    }
