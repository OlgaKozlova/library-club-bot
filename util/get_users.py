# export_members.py
import csv
import sys
from telethon import TelegramClient
from telethon.tl.types import User

API_ID = int(input("api_id: ").strip())
API_HASH = input("api_hash: ").strip()

# Можно вставить @username группы или ссылку t.me/..., или numeric id
CHAT = input("chat (например @mygroup или https://t.me/mygroup): ").strip()

OUT = "members.csv"

async def main():
    client = TelegramClient("user_session", API_ID, API_HASH)
    await client.start()  # попросит телефон/код/2FA при первом запуске

    entity = await client.get_entity(CHAT)

    rows = []
    async for u in client.iter_participants(entity):
        if not isinstance(u, User):
            continue
        rows.append({
            "user_id": u.id,
            "username": u.username or "",
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "phone": u.phone or "",
            "is_bot": int(bool(u.bot)),
            "deleted": int(bool(u.deleted)),
        })

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [
            "user_id","username","first_name","last_name","phone","is_bot","deleted"
        ])
        w.writeheader()
        w.writerows(rows)

    print(f"Saved {len(rows)} members to {OUT}")

if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
