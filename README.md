# PeopleCore HRMS v2.0 — TalentBridge Corporation Internal System

**TalentBridge Corporation — Human Resources Management System**
Internal use only. Not for distribution.

---

## Overview

PeopleCore HRMS v2.0 is TalentBridge Corporation's proprietary HR management platform, developed in-house starting 2008 and continuously extended by the IT team. It handles employee records, payroll processing, leave management, and HR reporting for ~1,200 employees across three regional offices (US, UK, India).

**Stack:** PHP 5.2, MySQL 5.1, Apache 2.2, Linux (CentOS 5)

---

## Modules

| Module | Path | Owner |
|---|---|---|
| Employee Management | `employee/employee_manager.php` | HR Dept / IT |
| Payroll Calculator | `payroll/payroll_calculator.php` | Finance / D.Mehta |
| Leave Manager | `leave/leave_manager.php` | HR Dept / K.Nair |
| HR Reports | `reports/hr_reports.php` | HR Dept / S.Pillai |
| Login / Auth | `auth/login.php` | IT / B.Chauhan |
| DB Configuration | `config/database.php` | IT Infra |
| Utilities | `utils/helpers.php` | IT / R.Singh |

---

## Setup

1. Copy files to `/var/www/html/hrms/` on the application server (`appsvr01.tbridge.internal`)
2. Import `db/peoplecore_schema.sql` into MySQL as root
3. Update DB credentials in `config/database.php` if host changes
4. Set Apache `AllowOverride All` for the hrms vhost
5. Ensure `/var/hrms/uploads/` is writable by `www-data`

**Default admin login:** `admin` / `Admin@2008` (change after first login — IT policy)

---

## Known Issues / Technical Debt

- PHP 5.2 upgrade to 5.6 was attempted in 2014 but rolled back due to `mysql_*` deprecation warnings breaking several modules. Upgrade to PDO is on the 2016 roadmap.
- Payroll bonus formula field (`bonus_formula`) uses `eval()` — restrict to Finance admins only via application role. Fix pending.
- Leave attachment download does not sanitize filenames — IT is aware, low priority since internal only.
- MD5 password hashing flagged in 2012 security audit. Migration to bcrypt deferred to v2.5.
- `DEBUG_MODE` and `DISPLAY_ERRORS` in `config/database.php` — must be set to `false` before any external access. Currently internal-only so considered acceptable.
- No CSRF tokens in forms — internal network policy deemed sufficient by management (2010).
- `SELECT *` in reports module — optimization tickets raised in JIRA (TB-441, TB-442), not yet scheduled.

---

## Change Log

| Version | Date | Author | Notes |
|---|---|---|---|
| 2.0 | 2013-11-10 | S.Pillai | Reports module, CSV export, leave audit |
| 1.9 | 2012-06-03 | D.Mehta | Multi-country payroll (IN, UK added) |
| 1.7 | 2011-08-05 | K.Nair | Leave delegation, balance override |
| 1.5 | 2010-02-17 | R.Singh | Helpers lib, ereg validators |
| 1.0 | 2008-09-01 | B.Chauhan | Initial release |

---

## Support

Contact IT Helpdesk: ext. 204 | helpdesk@tbridge.internal
System owner: IT Manager — P.Okafor (p.okafor@tbridge.internal)
