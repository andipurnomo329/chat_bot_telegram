project/
│
├── main.py                  → entry point bot Telegram (polling loop)
├── autoreload.py            → jalankan main.py dengan auto-restart saat file berubah (dev only)
│
├── .env                     → (TIDAK di-commit) isi kredensial asli, salin dari .env.example
├── .env.example             → template nama environment variable yang dibutuhkan
│
├── config/
│   ├── settings.py          → baca TOKEN, kredensial ES/Kibana, group, authorized users dari .env
│   ├── jenkins_services.py  → JENKINS_SERVICES (token webhook dibaca dari .env)
│   ├── paths.py              → path dasar project
│   ├── menu.py               → MENU_STRUCTURE
│
├── utils/
│   ├── env_loader.py         → load_env_file(), baca file .env ke os.environ
│   ├── time_utils.py         → iso_now()
│   ├── logger.py              → write_log()
│   ├── http_utils.py          → safe_post()
│   ├── telegram.py            → send/edit/delete message, send_photo
│   ├── telegram_api.py        → helper request ke Telegram Bot API
│   ├── helper.py               → get_app_name(), send_to_jenkins()
│
└── bot/
    ├── menu_builder.py               → build_dynamic_menu()
    ├── callback_handler.py           → seluruh callback handler + flow
    ├── message_handler.py            → handle pesan masuk & menu
    ├── elk_getdata.py                → orkestrasi query ke Elasticsearch/Kibana per menu
    ├── playwrigth.py                 → capture screenshot dashboard Kibana (Playwright)
    │
    ├── queryElk/
    │   ├── ams.py                    → amsQuery()
    │   ├── goaml.py                  → goamlQuery(), detailDatecode()
    │   ├── mtel.py                   → mtelQuery(), getSmsContentMtel()
    │   ├── notifcc.py                → notifcc_query()
    │   ├── wicpbi.py                 → wicQuery(cif)
    │
    ├── report_engine_notif_hilda*.py     → script standalone: generate & kirim report engine notif via bot Telegram terpisah
    ├── report_mteleplus_hilda.py         → script standalone: generate & kirim report Mteleplus
    ├── report_kcln_job_notif*.py         → script standalone: auto-notif status job KCLN (pakai cache lokal)
    └── otomasi_report/                    → salinan/varian script report di atas untuk penjadwalan otomatis (mis. Task Scheduler)

Setup kredensial:
1. Salin .env.example menjadi .env di root project.
2. Isi semua value di .env (token Telegram, kredensial Elasticsearch, Kibana Hub, login Kibana, token webhook Jenkins).
3. Jangan pernah commit file .env — sudah masuk .gitignore.

File runtime yang sengaja tidak di-track git (lihat .gitignore): __pycache__/, *.log, *.png, *.xlsx,
bot/auto_notif_cache.json (cache state notifikasi, dibuat ulang otomatis oleh bot saat berjalan).
