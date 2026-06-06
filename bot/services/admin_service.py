from bot.services.database import Database

STATUS_EMOJI = {
    "PENDING": "⏳",
    "CONFIRMED": "✅",
    "DECLINED": "❌",
    "CANCELLED": "🚫",
}


class AdminService:
    def __init__(self, db: Database, admin_ids: list[int]):
        self.db = db
        self.admin_ids = admin_ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    async def get_dashboard_stats(self) -> dict:
        pending = await self.db.get_pending_bookings()
        return {
            "total_users": await self.db.get_user_count(),
            "total_bookings": await self.db.get_booking_count(),
            "pending": pending,
            "avg_rating": await self.db.get_average_rating(),
        }

    async def get_detailed_stats(self) -> dict:
        stats = await self.get_dashboard_stats()
        all_bookings = await self.db.get_all_bookings(limit=100)
        stats["confirmed"] = sum(1 for booking in all_bookings if booking["status"] == "CONFIRMED")
        stats["declined"] = sum(1 for booking in all_bookings if booking["status"] == "DECLINED")
        return stats

    def status_emoji(self, status: str) -> str:
        return STATUS_EMOJI.get(status, "❓")
