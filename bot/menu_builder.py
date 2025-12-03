from config.menu import MENU_STRUCTURE

def build_dynamic_menu(path):
    ptr = MENU_STRUCTURE
    for p in path:
        ptr = ptr.get(p, {})

    buttons = []

    if isinstance(ptr, dict):
        for k in ptr:
            buttons.append([{
                "text": k,
                "callback_data": "go::" + "::".join(path + [k])
            }])

    elif isinstance(ptr, list):
        for item in ptr:
            buttons.append([{
                "text": item,
                "callback_data": f"site::{item}"
            }])

    if path:
        back = "::".join(path[:-1])
        callback = f"go::{back}" if back else "go::"
        buttons.append([{
            "text": "⬅️ Kembali",
            "callback_data": callback
        }])

    title = "📁 " + " → ".join(path) if path else "📁 MENU UTAMA"

    return title, {"inline_keyboard": buttons}
