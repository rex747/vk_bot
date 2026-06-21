import os
import asyncio
import json
import logging
import aiohttp
from dotenv import load_dotenv
from vkbottle import Bot, Keyboard, Callback, GroupEventType
from vkbottle.bot import Message, MessageEvent
from vkbottle.http import AiohttpClient
import database as db
from states import AddProductSG, DeleteProductSG, ManagePhotoSG
from keyboards import (
    main_menu_kb, product_card_kb, confirm_delete_kb, back_to_menu_kb
)

logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN = os.getenv("VK_BOT_TOKEN")
GROUP_ID_STR = os.getenv("VK_GROUP_ID")
if not TOKEN or TOKEN == "YOUR_TOKEN_HERE":
    raise ValueError("Ошибка: Токен VK не найден! Проверьте файл .env")
if not GROUP_ID_STR:
    raise ValueError("Ошибка: VK_GROUP_ID не найден в файле .env!")
GROUP_ID = int(GROUP_ID_STR)

user_temp_data: dict = {}

# Создаём бота с дефолтным клиентом (будет заменён в main)
bot = Bot(token=str(TOKEN))

# ---------- Вспомогательные функции ----------
def format_product(p: dict) -> str:
    status = "🔒 ЗАБРОНИРОВАН" if p.get("is_reserved") else "✅ Свободен"
    photos_str = p.get("photos")
    try:
        photos_list = json.loads(photos_str) if photos_str else []
    except (json.JSONDecodeError, TypeError):
        photos_list = []
    photos_info = f"\n📷 Фото: {len(photos_list)} шт." if photos_list else "\n📷 Фото: нет"
    return f"🆔 ID: {p['id']}\n📦 {p['name']}\n📝 {p['description']}\n💰 Цена: {p['price']:.2f} ₽{photos_info}\nСтатус: {status}"

def get_attachment_string(p: dict) -> str:
    photos_data = p.get("photos")
    if not photos_data:
        return ""
    if isinstance(photos_data, list):
        photos_list = photos_data
    elif isinstance(photos_data, str):
        try:
            photos_list = json.loads(photos_data)
        except (json.JSONDecodeError, TypeError):
            photos_list = []
    else:
        photos_list = []
    return ",".join(photos_list) if photos_list else ""

# ---------- Главное меню ----------
@bot.on.message(text=["/start", "Начать", "Меню"])
async def start_handler(m: Message):
    try:
        await bot.state_dispenser.delete(m.from_id)
    except KeyError:
        pass
    if m.from_id in user_temp_data:
        del user_temp_data[m.from_id]
    await db.init_db()
    await m.answer("🛍 Добро пожаловать в магазин! Выберите действие:", keyboard=main_menu_kb())

# ---------- Обработчик Callback-событий ----------
@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
async def callback_router(event: MessageEvent):
    payload_raw = event.object.payload
    if isinstance(payload_raw, dict):
        payload = payload_raw
    elif isinstance(payload_raw, str):
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}

    cmd = payload.get("cmd")
    user_id = event.object.user_id
    peer_id = event.object.peer_id

    if cmd == "menu":
        await bot.api.messages.send(peer_id=peer_id, message="🏠 Главное меню: ", keyboard=main_menu_kb(), random_id=0)
        await event.show_snackbar("Меню обновлено")
    elif cmd == "about":
        await bot.api.messages.send(peer_id=peer_id, message="🤖 Бот магазина v1.0\nPython + vkbottle", keyboard=back_to_menu_kb(), random_id=0)
    elif cmd == "catalog":
        await show_catalog(peer_id)
    elif cmd == "add_start":
        user_temp_data[user_id] = {}
        await bot.state_dispenser.set(user_id, AddProductSG.WAITING_NAME)
        await bot.api.messages.send(peer_id=peer_id, message="➕ Введите название нового товара: ", random_id=0)
    elif cmd == "del_start":
        await bot.state_dispenser.set(user_id, DeleteProductSG.WAITING_ID)
        await bot.api.messages.send(peer_id=peer_id, message="🗑 Введите ID товара для удаления (число): ", random_id=0)
    elif cmd == "manage_photo_start":
        await bot.state_dispenser.set(user_id, ManagePhotoSG.WAITING_PRODUCT_ID)
        await bot.api.messages.send(peer_id=peer_id, message="🖼 Введите ID товара, у которого нужно удалить фото: ", random_id=0)
    elif cmd == "reserve":
        product_id = payload.get("id")
        if product_id and await db.reserve_product(product_id, user_id):
            await event.show_snackbar(f"✅ Товар #{product_id} забронирован")
            await refresh_product_card(event, product_id)
        else:
            await event.show_snackbar("❌ Товар уже забронирован")
    elif cmd == "cancel_reserve":
        product_id = payload.get("id")
        if product_id and await db.cancel_reservation(product_id, user_id):
            await event.show_snackbar("🔓 Бронь снята")
            await refresh_product_card(event, product_id)
        else:
            await event.show_snackbar("❌ Нельзя снять чужую бронь")
    elif cmd == "confirm_del":
        product_id = payload.get("id")
        if product_id:
            await db.delete_product(product_id)
            await event.show_snackbar(f"🗑 Товар #{product_id} удалён")
        await bot.api.messages.send(peer_id=peer_id, message="🏠 Главное меню: ", keyboard=main_menu_kb(), random_id=0)
    elif cmd == "cancel_del":
        try:
            await bot.state_dispenser.delete(user_id)
        except KeyError:
            pass
        await bot.api.messages.send(peer_id=peer_id, message="🏠 Главное меню: ", keyboard=main_menu_kb(), random_id=0)
    elif cmd == "delete_photo_prompt":
        product_id = payload.get("id")
        product = await db.get_product(product_id)
        if product:
            photos_str = product.get("photos")
            try:
                photos_list = json.loads(photos_str) if photos_str else []
            except (json.JSONDecodeError, TypeError):
                photos_list = []

            if photos_list:
                await bot.state_dispenser.set(user_id, ManagePhotoSG.WAITING_PHOTO_INDEX)
                user_temp_data.setdefault(user_id, {})["target_product_id"] = product_id
                await bot.api.messages.send(
                    peer_id=peer_id,
                    message=f"У товара {len(photos_list)} фото. Напишите номер фото (от 1 до {len(photos_list)}), которое нужно удалить:\n\n{format_product(product)}",
                    attachment=get_attachment_string(product),
                    random_id=0
                )
            else:
                await event.show_snackbar("❌ У этого товара нет фото")

    # Обязательный ответ на callback
    await bot.api.request(
        "messages.sendMessageEventAnswer",
        {
            "event_id": event.object.event_id,
            "user_id": event.object.user_id,
            "peer_id": event.object.peer_id,
            "event_data": '{"type": "show_snackbar", "text": "✅"}'
        }
    )

def get_photos_count(p: dict) -> int:
    photos_data = p.get("photos")
    if not photos_data:
        return 0
    if isinstance(photos_data, list):
        return len(photos_data)
    if isinstance(photos_data, str):
        try:
            return len(json.loads(photos_data))
        except:
            return 0
    return 0

async def refresh_product_card(event: MessageEvent, product_id: int):
    product = await db.get_product(product_id)
    if not product:
        return
    await bot.api.messages.edit(
        peer_id=event.object.peer_id,
        conversation_message_id=event.object.conversation_message_id,
        message=format_product(product),
        keyboard=product_card_kb(
            product_id,
            product.get("is_reserved", 0),
            get_photos_count(product)
        ),
        attachment=get_attachment_string(product),
    )

async def show_catalog(peer_id: int):
    products = await db.get_all_products()
    if not products:
        await bot.api.messages.send(peer_id=peer_id, message="📦 Каталог пуст.", keyboard=main_menu_kb(), random_id=0)
        return
    for p in products:
        await bot.api.messages.send(
            peer_id=peer_id,
            message=format_product(p),
            keyboard=product_card_kb(
                p["id"],
                p.get("is_reserved", 0),
                get_photos_count(p)
            ),
            attachment=get_attachment_string(p),
            random_id=0
        )

# ---------- FSM: Добавление товара ----------
@bot.on.message(state=AddProductSG.WAITING_NAME)
async def add_name(m: Message):
    user_temp_data.setdefault(m.from_id, {})["name"] = m.text
    await bot.state_dispenser.set(m.from_id, AddProductSG.WAITING_DESCRIPTION)
    await m.answer("📝 Теперь введите описание товара:")

@bot.on.message(state=AddProductSG.WAITING_DESCRIPTION)
async def add_description(m: Message):
    user_temp_data.setdefault(m.from_id, {})["description"] = m.text
    await bot.state_dispenser.set(m.from_id, AddProductSG.WAITING_PRICE)
    await m.answer("💰 Введите цену (число, например 1500):")

@bot.on.message(state=AddProductSG.WAITING_PRICE)
async def add_price(m: Message):
    try:
        price = float(m.text.replace(",", "."))
    except ValueError:
        await m.answer("❌ Некорректная цена. Введите число:")
        return
    user_temp_data.setdefault(m.from_id, {})["price"] = price
    await bot.state_dispenser.set(m.from_id, AddProductSG.WAITING_PHOTO)
    await m.answer("🖼 Пришлите одно или несколько фото товара (до 10 шт.) или напишите 'без фото':")

@bot.on.message(state=AddProductSG.WAITING_PHOTO)
async def add_photo(m: Message):
    data = user_temp_data.get(m.from_id, {})
    photos_list = []
    if m.attachments:
        for att in m.attachments:
            if att.type == 'photo':
                access_key = getattr(att.photo, 'access_key', None)
                if access_key:
                    photos_list.append(f"photo{att.photo.owner_id}_{att.photo.id}_{access_key}")
                else:
                    photos_list.append(f"photo{att.photo.owner_id}_{att.photo.id}")
    if not photos_list and m.text and m.text.lower().strip() == "без фото":
        photos_list = []
    elif not photos_list:
        await m.answer("❌ Пришлите фото или напишите 'без фото': ")
        return

    product_id = await db.add_product(
        name=data.get("name", "Без названия"),
        description=data.get("description", "Без описания"),
        price=data.get("price", 0.0),
        photos=photos_list,
    )
    user_temp_data.pop(m.from_id, None)
    await bot.state_dispenser.delete(m.from_id)

    product = await db.get_product(product_id)
    await m.answer(
        f"✅ Товар добавлен! ID: {product_id}\n\n{format_product(product)}",
        keyboard=main_menu_kb(),
        attachment=get_attachment_string(product)
    )

# ---------- FSM: Удаление товара ----------
@bot.on.message(state=DeleteProductSG.WAITING_ID)
async def del_ask_id(m: Message):
    try:
        pid = int(m.text)
    except ValueError:
        await m.answer("❌ Введите число — ID товара:")
        return
    try:
        await bot.state_dispenser.delete(m.from_id)
    except KeyError:
        pass
    product = await db.get_product(pid)
    if not product:
        await m.answer("❌ Товар не найден.", keyboard=main_menu_kb())
        return

    await m.answer(
        f"Удалить этот товар?\n\n{format_product(product)}",
        keyboard=confirm_delete_kb(pid),
        attachment=get_attachment_string(product),
    )

# ---------- FSM: Управление фото ----------
@bot.on.message(state=ManagePhotoSG.WAITING_PRODUCT_ID)
async def manage_photo_get_id(m: Message):
    try:
        pid = int(m.text)
    except ValueError:
        await m.answer("❌ Введите число — ID товара:")
        return
    product = await db.get_product(pid)
    if not product:
        await m.answer("❌ Товар не найден.", keyboard=main_menu_kb())
        await bot.state_dispenser.delete(m.from_id)
        return
    photos_str = product.get("photos")
    try:
        photos_list = json.loads(photos_str) if photos_str else []
    except (json.JSONDecodeError, TypeError):
        photos_list = []

    if not photos_list:
        await m.answer("❌ У этого товара нет фото для удаления.", keyboard=main_menu_kb())
        await bot.state_dispenser.delete(m.from_id)
        return

    user_temp_data.setdefault(m.from_id, {})["target_product_id"] = pid
    await bot.state_dispenser.set(m.from_id, ManagePhotoSG.WAITING_PHOTO_INDEX)

    await m.answer(
        f"У товара {len(photos_list)} фото. Напишите номер фото (от 1 до {len(photos_list)}), которое нужно удалить:\n\n{format_product(product)}",
        attachment=get_attachment_string(product)
    )

@bot.on.message(state=ManagePhotoSG.WAITING_PHOTO_INDEX)
async def manage_photo_delete(m: Message):
    try:
        photo_index = int(m.text) - 1
    except ValueError:
        await m.answer("❌ Введите число (номер фото):")
        return
    pid = user_temp_data.get(m.from_id, {}).get("target_product_id")
    if not pid:
        await m.answer("❌ Ошибка сессии. Начните заново через 'Меню'.", keyboard=main_menu_kb())
        await bot.state_dispenser.delete(m.from_id)
        return
    success = await db.remove_photo_from_product(pid, photo_index)
    await bot.state_dispenser.delete(m.from_id)
    user_temp_data.pop(m.from_id, None)

    if success:
        product = await db.get_product(pid)
        photos_str = product.get("photos")
        try:
            photos_list = json.loads(photos_str) if photos_str else []
        except (json.JSONDecodeError, TypeError):
            photos_list = []

        await m.answer(
            f"✅ Фото успешно удалено. Осталось фото: {len(photos_list)}\n\n{format_product(product)}",
            keyboard=product_card_kb(pid, product.get("is_reserved", 0), get_photos_count(product)),
            attachment=get_attachment_string(product)
        )
    else:
        await m.answer("❌ Не удалось удалить фото. Возможно, указан неверный номер.", keyboard=main_menu_kb())

# ---------- Запуск ----------
async def main():
    await db.init_db()

    # Создаём HTTP-клиент с отключённой проверкой SSL
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)
    http_client = AiohttpClient(session=session)

    # Заменяем клиент и у бота, и у его API 
    bot.http_client = http_client
    bot.api.http_client = http_client

    print("✅ Бот запущен и ожидает сообщения...")
    try:
        await bot.run_polling()
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())
