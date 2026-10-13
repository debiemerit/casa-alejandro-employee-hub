# Casa Alejandro Employee Hub — Expanded Railway build

**Philippines / Asia-Manila / semi-monthly payroll / daily-rated employees.** Flask + PostgreSQL mobile web app. This is a testable development build, **not audited production payroll software**. It must be validated with test data and legal/payroll review before handling real employee wages.

## What is implemented

- Admin-created employee and manager logins, hashed passwords and role separation.
- Employee rosters, shift creation/cancellation, in-app notices and **optional browser Web Push** for shift/payslip alerts (VAPID setup required; browser support and employee permission required).
- HTTPS browser selfie + GPS punches with server timestamps; private photo files; map links; configurable restaurant GPS geofence with flag-or-block policy; accuracy threshold.
- Break start/end events; manager attendance approval; timesheet CSV export.
- Employee availability calendar entries, leave requests/manager review, shift swap requests/manager approval.
- Holiday calendar, configurable multipliers, individual weekly rest weekday on account creation, semi-monthly payroll drafts, editable SSS/PhilHealth/Pag-IBIG/withholding tax deductions, reference contribution brackets, 13th-month accrual report, payroll CSV export and private PDF payslips.
- Installable PWA manifest; navigation optimized for mobile screens.

## Critical payroll limitations

**Do not use automatically generated amounts for live payroll without manual review.** There is **no authoritative current SSS/PhilHealth/Pag-IBIG/BIR contribution table shipped**; this prevents stale or invented deductions. The Contributions screen stores administrator-supplied reference brackets, but the app intentionally does **not automatically apply** them to payroll because the contribution basis can be monthly and different from semi-monthly basic pay. Payroll staff must enter and verify amounts per pay period. Night differential remains an editable field (not calculated automatically); holiday no-work eligibility, rest-day rotation, wage orders, 13th-month exclusions, and leave entitlements need payroll review. Break calculation is basic and should be tested with overnight shifts. A shift swap is manager-approved without checking all roster conflicts. No automated government filing, payment or remittance. Push alerts are best-effort, not guaranteed delivery. GPS can be spoofed.

## Railway deployment — WEBSITE ONLY (no npm or terminal on your PC)

### A. Put the application on GitHub
1. Download the ZIP, extract it. Open the `casa_employee_hub` folder **inside** the extracted ZIP.
2. At https://github.com sign in → top-right `+` → **New repository**. Name: `casa-alejandro-employee-hub`; choose **Private** → **Create repository**.
3. On the empty repository page click **uploading an existing file** (or **Add file → Upload files**). Drag **the contents of the `casa_employee_hub` folder**, not the outer folder or ZIP, into the GitHub uploader. Include `app.py`, `requirements.txt`, `railway.json`, `start.sh`, `Procfile`, `templates/`, `static/`.
4. Commit the files. Confirm `app.py` is visible at the repository **root**. Do **not** upload a real `.env`, employee photos, passwords, payroll CSVs, or database files.

### B. Create Railway services
5. Sign in at https://railway.com → **New Project** → **Deploy from GitHub repo** → connect/authorize GitHub and select `casa-alejandro-employee-hub`. If deployment starts before the database exists, it may fail initially; that is expected.
6. In the same Railway project click **+ New** → **Database** → **PostgreSQL**. Wait for database provisioning. Note the actual database service name, often `Postgres`.
7. Select your **web app service** (not Postgres) → **Variables** → **New Variable**. Set `DATABASE_URL` using Railway's **reference variable picker** and select the PostgreSQL `DATABASE_URL` (typically `${{Postgres.DATABASE_URL}}`, only if your service is actually named Postgres). Never copy a fake example password.
8. Add these web-service variables:
   - `SECRET_KEY` = unique unpredictable secret, at least 32 random bytes (use a password manager's random generator).
   - `ADMIN_USERNAME` = `admin` (or your preferred login).
   - `ADMIN_PASSWORD` = a unique 16+ character random password (save securely).
   - `COOKIE_SECURE` = `1`.
   - `PHOTO_STORAGE_DIR` = `/data/attendance_photos`.
9. **Persistent photo storage**: select the web service → **Settings / Volumes** (or project canvas volume option) → **Add Volume** → mount path `/data`. Railway volume features and costs vary by plan. **Without a persistent volume, attendance photos can disappear during redeploy.** Keep backups of the database and volume separately.
10. Under web service **Settings → Deploy**, use the start command `sh start.sh` if not automatically picked up from `railway.json`. The startup script creates any missing tables and seeds the first admin and example holidays, then launches Gunicorn. This avoids using Railway's command-line tool. The initial administrator is created only when no admin exists; changing `ADMIN_PASSWORD` later will not reset an existing account.
11. Wait for the latest deployment to become healthy. If it fails, open **Deployments → latest deployment → View Logs** and inspect the first error. Verify `DATABASE_URL`, secrets, start command and volume mount.
12. Web service → **Settings → Networking → Public Networking → Generate Domain**. Railway produces a URL like `https://<generated-name>.up.railway.app`. Open `<your-url>/healthz`; expected `{"ok":true}`. Then open `<your-url>/login` and sign in as admin.

### C. First-run configuration
13. Go to **Geofence** and enter the restaurant's exact latitude and longitude from a map pin. Set radius e.g. 100 m and policy **Flag for review** until GPS has been tested on site. Do not enable blocking until indoor accuracy is validated.
14. Go to **Employees** and create employee accounts with temporary strong passwords, daily rates and their regular weekly rest day. Employees should change credentials through an administrator until self-service password change is added.
15. Go to **Holidays** and verify the applicable Philippine holiday calendar with official proclamations; add local holidays, and validate configured multipliers against DOLE guidance. The included 2026 seed is **partial**, not a complete automatically updated official calendar.
16. Go to **Shifts** to publish shifts. Employees can log in on mobile and see upcoming shifts. Use **Availability**, **Leave**, and **Swaps** for requests.
17. Test on an employee phone via the HTTPS domain. Grant camera and location permission; submit a selfie clock-in and clock-out; manager checks map/photo and approves under **Times**. Test break start/end and exception handling.
18. Under **Payroll**, create a draft for a selected half-month and employee. Manually verify all amounts and deductions, including applicable holiday, overtime, night differential, SSS, PhilHealth, Pag-IBIG and withholding tax. Approve only after validation. Employee can then access their **Payslips** PDF.
19. Under **Times** and **Payroll**, download CSV files to reconcile payroll. Under **13th Month**, check estimated accruals.

### D. Optional browser push notifications
20. Generate a VAPID keypair with a trusted Web Push key generator or development tooling. Add **matching** `VAPID_PUBLIC_KEY` (URL-safe base64), `VAPID_PRIVATE_KEY` (PEM or supported key format), and `VAPID_SUBJECT` (e.g. `mailto:hr@yourdomain.com`) to Railway Variables. Do not share the private key.
21. Redeploy. Employees open the site, select **Enable Alerts**, and allow notifications. Web Push depends on browser/platform permissions and subscription persistence. On iPhone, web push typically requires the site to be installed to the Home Screen on supported iOS versions. Test on each device. The app still shows in-app notices when push is unavailable.

### E. Ongoing management
- **Deployment updates:** edit/upload files in the same private GitHub repository; Railway normally redeploys on commits.
- **Database and volume backups:** schedule and verify restores, separately. Railway's availability of automated backups depends on the plan.
- **Domain:** use the generated Railway URL first; custom subdomain can be configured later through Railway networking and DNS provider.
- **Security:** use HTTPS, strong unique passwords, restrict HR access, document Philippine Data Privacy Act compliance, provide a privacy notice and retention schedule for location/selfies, and obtain professional payroll validation.

## Developer notes
- Entry point: `app.py`; `start.sh` initializes schema on startup. For **existing** deployments from older versions, `db.create_all()` **does not add new columns to existing tables**. Use a proper database migration before upgrading an existing database. For a **fresh Railway PostgreSQL database**, no migration is needed.
- A real production launch additionally needs migration tooling, login rate limits, admin MFA, password self-service, robust backups, audit review UI, security testing, automated payroll tests, verified payroll rules, and monitoring.
- Set `FLASK_DEBUG=1`, `COOKIE_SECURE=0` only for local development, never on Railway.

## Expanded security and data management (October 2026)

**OTP:** After password login, each employee is redirected to enrol a TOTP authenticator (Google Authenticator, Microsoft Authenticator or compatible). On later logins the employee enters a six-digit TOTP code. TOTP codes are not emailed or sent by SMS. Protect the authenticator setup secret. Lost-device recovery currently requires a database administrator to securely reset `user.otp_secret` after identity verification; there is no self-service reset. Production deployments should add rate limiting, account lockouts, audited recovery, and encrypted OTP secrets before real employee use.

**Admin data management:** Open `/admin/data` to download a PostgreSQL custom-format database dump plus attendance photos as ZIP, export employees/shifts/attendance/holidays/payroll to CSV, and import employees from CSV (`username,name,position,daily_rate`). Imported new employee accounts are disabled and must be assigned passwords and activated through an administrator-controlled process. The import updates existing employee name, position and daily rate; it does not import passwords or OTP secrets. Restore is intentionally not a web button: use `pg_restore` with a new isolated PostgreSQL database and maintenance window, then separately restore photo files to the volume. Test restore before relying on a backup.

**Railway deployment:** Use the included Dockerfile so `pg_dump` is available. Create a **private** GitHub repository and upload the *contents* of this directory to the repository root. Railway → New Project → Deploy from GitHub Repo; add PostgreSQL. Under web service Variables set `DATABASE_URL` via `${{Postgres.DATABASE_URL}}` using Railway's reference picker (service name may differ), `SECRET_KEY` to a random secret, `ADMIN_USERNAME`, `ADMIN_PASSWORD` (minimum 12 characters), `COOKIE_SECURE=1`, and `PHOTO_STORAGE_DIR=/data/attendance_photos`. Add a persistent volume mounted at `/data`. Railway → web service → Settings → Networking → Generate Domain. Railway will build using Dockerfile. Check `/healthz`, log in with admin credentials, enrol your authenticator, then open Admin → Data Management.

**Security caveats:** Backup ZIP downloads are not encrypted themselves. Immediately encrypt and store offsite with limited access. Photos are backed up only when located under `PHOTO_STORAGE_DIR`; other externally stored documents need separate backup. Backups are manual, not scheduled. This upgrade does not implement an in-app restore or import of attendance/payroll; these should be added only with validation and transaction-safe workflows. The existing payroll rules remain draft estimates and require Philippine compliance validation. Do not use real employee data or payroll in production until security and end-to-end testing are complete.
