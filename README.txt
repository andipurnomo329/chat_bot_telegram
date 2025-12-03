project/
│
├── main.py
│
├── config/
│   ├── settings.py          → TOKEN, username, group, menu timeout
│   ├── jenkins_services.py  → JENKINS_SERVICES
│   ├── menu.py              → MENU_STRUCTURE
│
├── utils/
│   ├── time_utils.py        → iso_now()
│   ├── logger.py            → write_log()
│   ├── http_utils.py        → safe_post()
│   ├── telegram.py          → send/edit/delete message
│
└── bot/
    ├── menu_builder.py      → build_dynamic_menu()
    └── handler.py           → seluruh callback handler + flow