# ReuseHub — Project Directory & Architecture Reference

> **ReuseHub** is a full-featured community item-sharing platform built with Django. It connects neighbors to pass on pre-loved belongings, support repairable reuse, and reduce landfill waste.

---

## 📁 Repository Overview

```text
d:\ReuseHub/
├── .gitignore                   # Git ignore specifications (venv, cache, local secrets)
├── PROJECT_STRUCTURE.md         # Comprehensive project directory and architecture reference
├── pyrightconfig.json           # Pyright/Pylance configuration and Python venv bindings
├── requirements.txt             # Pinned project dependencies and third-party libraries
├── venv/                        # Python virtual environment (ignored by Git)
│
└── miniproject/                 # Main Django project workspace
    ├── manage.py                # Django CLI management entry point
    ├── .env                     # Local environment variables & secrets (DB, Google OAuth, SMTP)
    ├── .env.example             # Example environment configuration template
    ├── db.sqlite3               # SQLite fallback database for zero-config local dev
    │
    ├── miniproject/             # Django core configuration package
    │   ├── __init__.py
    │   ├── asgi.py              # ASGI configuration for async server deployments
    │   ├── settings.py          # Central Django configuration (apps, middleware, DB, allauth)
    │   ├── urls.py              # Global URL dispatcher and routing configuration
    │   └── wsgi.py              # WSGI configuration for production deployment
    │
    ├── app/                     # Primary application domain logic
    │   ├── __init__.py
    │   ├── adapters.py          # Google OAuth 2.0 social adapter & account linking
    │   ├── admin.py             # Django admin interface customizations & inline models
    │   ├── apps.py              # AppConfig definition
    │   ├── community.py         # Trust metrics, badge algorithms & rating aggregates
    │   ├── emails.py            # Centralized email utility (HTML templates & SMTP dispatch)
    │   ├── forms.py             # Django form definitions, validation & multi-file upload
    │   ├── models.py            # Core database models (Item, Request, Report, Review, OTP)
    │   ├── tests.py             # Comprehensive automated test suite (33 unit/integration tests)
    │   ├── test_google_auth.py  # Automated tests for Google OAuth authentication flows
    │   ├── urls.py              # Application-level URL routes & endpoint handlers
    │   ├── views.py             # View functions (User, Dashboards, Auth, Admin)
    │   │
    │   ├── management/          # Custom management commands
    │   │   └── commands/
    │   │       └── seed_data.py # Sample database populator command
    │   │
    │   └── migrations/          # Django schema migration files
    │
    ├── media/                   # User-uploaded files (avatars & item listing photos)
    │   ├── avatars/             # User profile photos
    │   └── items/               # Item listing galleries partitioned by year/month
    │
    ├── static/                  # Static assets (custom vanilla CSS, JS, branding images)
    │   ├── css/                 # Modular CSS stylesheets (color themes & layouts)
    │   │   ├── about.css
    │   │   ├── categories.css
    │   │   ├── dashboard.css
    │   │   ├── dashboard_ui.css # Modern persistent sidebar layout styles
    │   │   ├── help.css
    │   │   ├── home.css
    │   │   ├── item_confirm_delete.css
    │   │   ├── item_detail.css
    │   │   ├── item_form.css
    │   │   ├── listings.css
    │   │   ├── login.css
    │   │   ├── modal.css
    │   │   ├── my_listings.css
    │   │   ├── my_requests.css
    │   │   ├── notifications.css
    │   │   ├── profile.css
    │   │   ├── public_profile.css
    │   │   ├── register.css
    │   │   ├── report_form.css
    │   │   ├── reports.css
    │   │   ├── style.css        # Global CSS design tokens & navigation styles
    │   │   └── users.css
    │   │
    │   ├── images/              # Platform assets, logos, and illustration mockups
    │   │   ├── about_hero_banner.png
    │   │   ├── hero_box_lavender.png
    │   │   ├── hero_clean_bg.png
    │   │   ├── hero_clean_bg_retina.png
    │   │   ├── login_3d.jpg
    │   │   ├── profile_cover_banner.jpg
    │   │   ├── register_3d.jpg
    │   │   ├── register_fullscreen_bg.jpg
    │   │   └── reusehub_logo.png
    │   │
    │   └── js/                  # Client-side dynamic interaction scripts
    │       ├── form_validation.js
    │       ├── location_autocomplete.js
    │       ├── modal.js
    │       └── notifications.js
    │
    └── templates/               # Django HTML templates
        ├── base.html            # Master layout template (Navbar, notifications, footer)
        │
        ├── app/                 # User module pages & components
        │   ├── about.html       # About & mission page
        │   ├── help.html        # Help center, FAQs & support ticket submission
        │   ├── home.html        # Homepage item discovery feed & search filters
        │   ├── item_confirm_delete.html
        │   ├── item_detail.html # Item showcase, donor badges, request & report modals
        │   ├── item_form.html   # Create & edit listing with multi-image selector
        │   ├── my_listings.html # Donor listings manager dashboard
        │   ├── my_requests.html # Requester status dashboard
        │   ├── notifications.html
        │   ├── profile.html     # Private account settings & profile management
        │   ├── public_profile.html # Public member trust profile, reviews & ratings
        │   ├── report_form.html
        │   ├── report_user_form.html
        │   │
        │   ├── admin/           # Platform moderator & admin portal templates
        │   │   ├── categories.html
        │   │   ├── dashboard.html
        │   │   ├── listings.html
        │   │   ├── reports.html
        │   │   ├── support.html
        │   │   └── users.html
        │   │
        │   ├── auth/            # Authentication & verification templates
        │   │   ├── login.html
        │   │   ├── register.html
        │   │   ├── verify_otp.html
        │   │   ├── password_reset.html
        │   │   ├── password_reset_done.html
        │   │   ├── password_reset_confirm.html
        │   │   └── password_reset_complete.html
        │   │
        │   └── partials/        # Reusable template components
        │       ├── dashboard_mobile_header.html
        │       └── dashboard_sidebar.html
        │
        ├── emails/              # Responsive HTML transactional email templates
        │   ├── base_email.html
        │   ├── account_notification.html
        │   ├── item_request_notification.html
        │   ├── item_status_update.html
        │   ├── password_reset.html
        │   ├── registration_otp.html
        │   └── request_status_notification.html
        │
        └── socialaccount/       # Third-party OAuth error pages
            └── authentication_error.html
```

---

## 🏛️ Architecture & Component Breakdown

### 1. Core Data Models (`app/models.py`)
* **`Category`**: Taxonomies for organizing listings with auto-slugification.
* **`Item`**: Belongs to a donor; tracks title, description, condition, repairability, coordinates, moderation status, and primary cover photo.
* **`ItemImage`**: Gallery photos (up to 5 images per item) with cover photo flag.
* **`ItemRequest`**: Manages pickup requests, communications, and exchange workflow (`PENDING` → `ACCEPTED` / `REJECTED` → `COMPLETED`).
* **`Report`**: User-filed moderation flags against listings or user profiles.
* **`SupportInquiry`**: Help desk ticketing system tracking user issues through `PENDING`, `IN_PROGRESS`, `RESOLVED`, and `CLOSED`.
* **`UserProfile`**: One-to-one extension of `User` storing avatar, bio, location, phone, trust badges, and email verification state.
* **`EmailOTP`**: Cryptographically secure 6-digit one-time passcodes with expiration timestamps and rate-limiting.
* **`UserReview`**: 1–5 star community feedback left between exchange participants after item collection.

### 2. View Controllers (`app/views.py`)
* **Discovery & Listing**: `item_list`, `item_detail`, `item_create`, `item_edit`, `item_delete`.
* **Exchange Operations**: `request_item`, `cancel_request`, `respond_request`, `mark_given_away`, `mark_available`.
* **Community Profiles**: `profile_view`, `public_profile_view`, `submit_review_view`, `report_user_view`.
* **Authentication & OTP**: `register_view`, `verify_otp_view`, `resend_otp_view`, `login_view`, `logout_view`, and full password reset suite.
* **Admin & Moderation**: `admin_dashboard`, `admin_listings`, `admin_moderate_action`, `admin_categories`, `admin_reports`, `admin_support`, `admin_users`.

### 3. Google OAuth & Account Linking (`app/adapters.py`)
* Implements `ReuseHubSocialAccountAdapter` via `django-allauth`.
* Safely connects Google OAuth accounts to existing accounts when emails match and are verified by Google.
* Automatically marks profile email as verified and synchronizes names.

### 4. Design System & Frontend (`static/css/`, `templates/`)
* **Pure Vanilla CSS**: Built with custom CSS custom properties (variables) avoiding Tailwind/Bootstrap dependencies.
* **Lavender & Slate Color Palette**: Warm, clean, accessible aesthetic with glassmorphism cards and smooth micro-animations.
* **Responsive Layouts**: Desktop sidebars collapse into responsive mobile drawer headers.

---

## 🚀 Common Commands

```powershell
# 1. Activate Virtual Environment
..\venv\Scripts\activate

# 2. Run Database Migrations
python manage.py migrate

# 3. Populate Sample Data (Optional)
python manage.py seed_data

# 4. Run Automated Test Suite
python manage.py test

# 5. Start Development Server
python manage.py runserver
```
