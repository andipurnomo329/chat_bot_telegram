from playwright.sync_api import sync_playwright
from config.settings import *
from datetime import datetime

def capture():
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
            "https://192.168.45.33/app/kibana#/dashboard/d3d9c860-bb5a-11ee-8e7f-b3c3d147884e?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:now-1h,to:now))&_a=(description:'',filters:!(),fullScreenMode:!f,options:(hidePanelTitles:!f,useMargins:!t),query:(language:kuery,query:''),timeRestore:!f,title:CSD,viewMode:view)",
            wait_until="networkidle"
        )

        # Screenshot
        filename = f"capt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        page.screenshot(path=f"{PICT_DIR}\{filename}", full_page=True)
        browser.close()
        return filename