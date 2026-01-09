from playwright.sync_api import sync_playwright
from config.settings import *
from datetime import datetime


sendingtype_map = {
    "mtel": "https://192.168.45.33/app/kibana#/dashboard/8476f2e0-a8aa-11f0-9991-e7551419b201?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-1h,to:now))&_a=(description:'',filters:!(),fullScreenMode:!f,options:(hidePanelTitles:!f,useMargins:!t),query:(language:kuery,query:''),timeRestore:!f,title:'MTELEPLUS%20NOTIF%20CC',viewMode:view)",
    "goaml": "https://192.168.45.33/app/kibana#/dashboard/224db7a0-7d48-11ee-b1ae-7ffc86917c48?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-15m,to:now))&_a=(description:'',filters:!(),fullScreenMode:!f,options:(hidePanelTitles:!f,useMargins:!t),query:(language:kuery,query:''),timeRestore:!f,title:'GO%20AML%20Dashboard',viewMode:view)",
    "4": "MVRK"
}

def capture(app_name):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        # Login page
        page.goto("https://192.168.45.33/login", wait_until="domcontentloaded")

        page.fill('[data-test-subj="loginUsername"]', "ls23")
        page.fill('[data-test-subj="loginPassword"]', "bniy2k")
        page.click('[data-test-subj="loginSubmit"]')

        page.wait_for_load_state("networkidle")

        page.goto(
            sendingtype_map[app_name],
            wait_until="domcontentloaded",
            timeout=200000
        )
        page.wait_for_load_state("networkidle")
        
        # Screenshot
        filename = f"capt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        page.screenshot(path=f"{PICT_DIR}\{filename}", full_page=True)
        browser.close()
        return filename