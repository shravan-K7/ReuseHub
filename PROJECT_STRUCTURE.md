# ReuseHub — Basic Folder Structure

```text
ReuseHub/
│
├── miniproject/
│   ├── manage.py            <-- Django CLI entry point (run commands here)
│   ├── app/                 # Main Django application
│   ├── miniproject/         # Core settings and root URLs
│   ├── templates/           # HTML templates
│   ├── static/              # CSS, JS, and image assets
│   └── media/               # Uploaded files
│
├── requirements.txt         # Project dependencies
└── venv/                    # Python virtual environment
```

### Running Commands

Always run Django commands from the `miniproject` directory containing [manage.py](file:///d:/ReuseHub/miniproject/manage.py):

```powershell
cd miniproject
py manage.py runserver
```

