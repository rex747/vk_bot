from vkbottle import Keyboard, Callback

def main_menu_kb():
    kb = Keyboard(inline=False)
    kb.add(Callback("📦 Каталог товаров", payload={"cmd": "catalog"}))
    kb.add(Callback("➕ Добавить товар", payload={"cmd": "add_start"}))
    kb.row()
    kb.add(Callback("🗑 Удалить товар", payload={"cmd": "del_start"}))
    kb.add(Callback("🖼 Управление фото", payload={"cmd": "manage_photo_start"}))
    kb.row()
    kb.add(Callback("ℹ️ О боте", payload={"cmd": "about"}))
    return kb.get_json()

def product_card_kb(product_id: int, is_reserved: bool, photos_count: int):
    kb = Keyboard(inline=True)
    if is_reserved:
        kb.add(Callback("❌ Снять бронь", payload={"cmd": "cancel_reserve", "id": product_id}))
    else:
        kb.add(Callback("🔒 Забронировать", payload={"cmd": "reserve", "id": product_id}))
    
    if photos_count > 0:
        kb.row()
        kb.add(Callback("🗑 Удалить 1 фото", payload={"cmd": "delete_photo_prompt", "id": product_id}))
        
    return kb.get_json()

def confirm_delete_kb(product_id: int):
    kb = Keyboard(inline=True)
    kb.add(Callback("✅ Да, удалить", payload={"cmd": "confirm_del", "id": product_id}))
    kb.add(Callback("❌ Отмена", payload={"cmd": "cancel_del"}))
    return kb.get_json()

def back_to_menu_kb():
    kb = Keyboard(inline=True)
    kb.add(Callback("🏠 Главное меню", payload={"cmd": "menu"}))
    return kb.get_json()
