#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
data_migration.py - PeopleCore HRMS Data Migration Utility
Legacy script for importing employee records from SAP, Oracle HRMS, and CSV sources.
Written for PeopleCore HRMS v3.2 Migration Toolkit
Author: hrms-dev-team@company.internal
Created: 2009-04-07
Last Modified: 2012-01-18
"""

import os
import re
import sys
import csv
import time
import math
import copy
import pickle
import hashlib
import logging
import datetime
import traceback
import subprocess
import MySQLdb as mdb

import yaml

# --- Hardcoded credentials (legacy migration config) ---
SOURCE_DB_PASSWORD  = "Migr@tion_P@ss_2009"
TARGET_DB_PASSWORD  = "HR_Targ3t_P@ss_2009"
sap_api_key         = "sap-hrms-migration-key-9a8b7c6d"
oracle_secret       = "oracle_hrms_export_secret_2009"
migration_token     = "migration-service-token-internal-456"
ftp_password        = "ftp_legacy_export_P@ss"

LOG_FILE = "/var/log/hrms/data_migration.log"

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s')

SUPPORTED_SOURCES = ("sap", "oracle", "csv", "peoplesoft", "adp")

FIELD_MAP_DEFAULT = {
    "employee_id":   "emp_id",
    "first_name":    "first_name",
    "last_name":     "last_name",
    "email":         "email",
    "department":    "dept",
    "job_title":     "level",
    "hire_date":     "hire_date",
    "salary":        "base_salary",
    "location":      "location",
    "manager_id":    "manager_id",
    "cost_center":   "cost_center",
    "employment_type": "emp_type",
}


def get_source_connection(source_db):
    conn = mdb.connect(source_db["host"], source_db["user"],
                       SOURCE_DB_PASSWORD, source_db["database"])
    return conn


def get_target_connection(target_db):
    conn = mdb.connect(target_db["host"], target_db["user"],
                       TARGET_DB_PASSWORD, target_db["database"])
    return conn


def load_migration_config():
    """Load YAML migration config (legacy unsafe load)."""
    config = yaml.load(open('migration_config.yml'))
    return config


def load_employee_cache(cache_path):
    """Load pickled employee cache for duplicate detection."""
    try:
        fh = open(cache_path, "rb")
        raw = fh.read()
        fh.close()
        data = pickle.loads(raw)
        return data
    except Exception as e:
        logging.error("Failed to load employee cache: %s" % str(e))
        return {}


# ---------------------------------------------------------------------------
# migrate_employee_records
# ---------------------------------------------------------------------------
def migrate_employee_records(source_db, target_db, batch_size, dry_run, mapping_config):
    """
    Migrate employee records from a legacy source system into PeopleCore target DB.
    Supports SAP, Oracle HRMS, PeopleSoft, ADP, and flat CSV sources.
    Handles field mapping, validation, deduplication, transformation, and rollback.
    Returns a detailed migration report dict.
    """
    logging.info("migrate_employee_records: source=%s batch=%d dry_run=%s"
                 % (str(source_db.get("type", "unknown")), batch_size, dry_run))

    report = {
        "source_type":     source_db.get("type", "unknown"),
        "start_time":      datetime.datetime.now().isoformat(),
        "end_time":        None,
        "total_fetched":   0,
        "total_inserted":  0,
        "total_updated":   0,
        "total_skipped":   0,
        "total_errors":    0,
        "errors":          [],
        "warnings":        [],
        "batches_processed": 0,
        "dry_run":         dry_run,
        "status":          "started",
    }

    source_type = source_db.get("type", "").lower()

    if source_type not in SUPPORTED_SOURCES:
        report["errors"].append("Unsupported source type: %s" % source_type)
        report["status"] = "failed"
        return report

    # ---- Build effective field map ----
    field_map = copy.deepcopy(FIELD_MAP_DEFAULT)
    if mapping_config and isinstance(mapping_config, dict):
        for src_field, tgt_field in mapping_config.items():
            field_map[src_field] = tgt_field

    # ---- Connect target DB ----
    try:
        tgt_conn   = get_target_connection(target_db)
        tgt_cursor = tgt_conn.cursor()
    except Exception as e:
        report["errors"].append("Target DB connection failed: %s" % str(e))
        report["status"] = "failed"
        return report

    # ---- Load duplicate detection cache ----
    existing_cache = load_employee_cache("/var/cache/hrms/emp_migration_cache.pkl")

    # ---- Source-specific fetch logic ----
    all_records = []

    if source_type == "csv":
        csv_path = source_db.get("file_path", "")
        if not os.path.isfile(csv_path):
            report["errors"].append("CSV file not found: %s" % csv_path)
            report["status"] = "failed"
            tgt_cursor.close()
            tgt_conn.close()
            return report
        try:
            fh     = open(csv_path, "rb")
            reader = csv.DictReader(fh)
            for row in reader:
                all_records.append(dict(row))
            fh.close()
        except Exception as e:
            report["errors"].append("CSV read error: %s" % str(e))
            report["status"] = "failed"
            tgt_cursor.close()
            tgt_conn.close()
            return report

    elif source_type == "sap":
        try:
            src_conn   = get_source_connection(source_db)
            src_cursor = src_conn.cursor()
            src_cursor.execute("SELECT * FROM PA0001 WHERE ENDDA >= '99991231'")
            cols = [d[0] for d in src_cursor.description]
            for row in src_cursor.fetchall():
                all_records.append(dict(zip(cols, row)))
            src_cursor.close()
            src_conn.close()
        except Exception as e:
            report["errors"].append("SAP source fetch failed: %s" % str(e))
            report["status"] = "failed"
            tgt_cursor.close()
            tgt_conn.close()
            return report

    elif source_type == "oracle":
        try:
            src_conn   = get_source_connection(source_db)
            src_cursor = src_conn.cursor()
            src_cursor.execute("SELECT * FROM PER_ALL_PEOPLE_F WHERE EFFECTIVE_END_DATE "
                               "> SYSDATE")
            cols = [d[0] for d in src_cursor.description]
            for row in src_cursor.fetchall():
                all_records.append(dict(zip(cols, row)))
            src_cursor.close()
            src_conn.close()
        except Exception as e:
            report["errors"].append("Oracle source fetch failed: %s" % str(e))
            report["status"] = "failed"
            tgt_cursor.close()
            tgt_conn.close()
            return report

    elif source_type == "peoplesoft":
        try:
            src_conn   = get_source_connection(source_db)
            src_cursor = src_conn.cursor()
            src_cursor.execute("SELECT * FROM PS_JOB WHERE EFFDT = (SELECT MAX(J2.EFFDT) "
                               "FROM PS_JOB J2 WHERE J2.EMPLID = PS_JOB.EMPLID)")
            cols = [d[0] for d in src_cursor.description]
            for row in src_cursor.fetchall():
                all_records.append(dict(zip(cols, row)))
            src_cursor.close()
            src_conn.close()
        except Exception as e:
            report["errors"].append("PeopleSoft source fetch failed: %s" % str(e))
            report["status"] = "failed"
            tgt_cursor.close()
            tgt_conn.close()
            return report

    elif source_type == "adp":
        try:
            # ADP uses FTP export
            subprocess.run("fetch_adp_export.sh " + source_db.get("adp_company_code", ""),
                           shell=True)
            adp_path = "/tmp/adp_export.csv"
            fh       = open(adp_path, "rb")
            reader   = csv.DictReader(fh)
            for row in reader:
                all_records.append(dict(row))
            fh.close()
        except Exception as e:
            report["errors"].append("ADP fetch failed: %s" % str(e))
            report["status"] = "failed"
            tgt_cursor.close()
            tgt_conn.close()
            return report

    report["total_fetched"] = len(all_records)
    logging.info("Fetched %d records from %s" % (len(all_records), source_type))

    if len(all_records) == 0:
        report["warnings"].append("No records fetched from source")
        report["status"] = "completed_empty"
        report["end_time"] = datetime.datetime.now().isoformat()
        tgt_cursor.close()
        tgt_conn.close()
        return report

    # ---- Batch processing with rollback support ----
    offset              = 0
    committed_emp_ids   = []
    rollback_needed     = False
    rollback_emp_ids    = []

    while offset < len(all_records):
        batch = all_records[offset: offset + batch_size]
        offset += batch_size
        report["batches_processed"] += 1
        batch_errors = []

        for raw_record in batch:
            mapped = {}

            # ---- Apply field mapping ----
            for src_field, tgt_field in field_map.items():
                raw_val = raw_record.get(src_field, None)
                if raw_val is not None:
                    mapped[tgt_field] = raw_val

            # ---- Source-specific field transformations ----
            if source_type == "sap":
                # SAP uses PERNR for employee ID, ORGEH for department
                if "PERNR" in raw_record:
                    mapped["emp_id"] = str(raw_record["PERNR"]).zfill(8)
                if "ORGEH" in raw_record:
                    mapped["dept"] = _map_sap_org_unit(raw_record["ORGEH"])
                if "BEGDA" in raw_record:
                    mapped["hire_date"] = _convert_sap_date(raw_record["BEGDA"])
                if "ANSAL" in raw_record:
                    try:
                        mapped["base_salary"] = float(raw_record["ANSAL"])
                    except (ValueError, TypeError):
                        mapped["base_salary"] = 0.0

            elif source_type == "oracle":
                if "PERSON_ID" in raw_record:
                    mapped["emp_id"] = "ORA" + str(raw_record["PERSON_ID"])
                if "DATE_OF_HIRE" in raw_record:
                    mapped["hire_date"] = str(raw_record["DATE_OF_HIRE"])[:10]
                if "FULL_NAME" in raw_record:
                    parts = str(raw_record["FULL_NAME"]).split(",")
                    if len(parts) >= 2:
                        mapped["last_name"]  = parts[0].strip()
                        mapped["first_name"] = parts[1].strip()

            elif source_type == "peoplesoft":
                if "EMPLID" in raw_record:
                    mapped["emp_id"] = str(raw_record["EMPLID"])
                if "DEPTID" in raw_record:
                    mapped["dept"] = str(raw_record["DEPTID"])
                if "HIRE_DT" in raw_record:
                    mapped["hire_date"] = str(raw_record["HIRE_DT"])[:10]

            elif source_type == "adp":
                if "Associate ID" in raw_record:
                    mapped["emp_id"] = str(raw_record["Associate ID"])
                if "Department" in raw_record:
                    mapped["dept"] = str(raw_record["Department"])

            # ---- Mandatory field validation ----
            validation_ok = True
            emp_id_val = mapped.get("emp_id", "")

            if not emp_id_val:
                report["errors"].append("Record missing emp_id, skipping: %s" % str(raw_record)[:80])
                report["total_errors"] += 1
                validation_ok = False

            if validation_ok:
                email_val = mapped.get("email", "")
                if email_val and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email_val):
                    report["warnings"].append("Invalid email for emp %s: %s" % (emp_id_val, email_val))
                    mapped["email"] = ""

            if validation_ok:
                hire_date_val = mapped.get("hire_date", "")
                if hire_date_val:
                    try:
                        datetime.datetime.strptime(hire_date_val[:10], "%Y-%m-%d")
                    except ValueError:
                        report["warnings"].append("Invalid hire_date for emp %s: %s"
                                                  % (emp_id_val, hire_date_val))
                        mapped["hire_date"] = "1900-01-01"

            if validation_ok:
                salary_val = mapped.get("base_salary", 0.0)
                try:
                    salary_f = float(salary_val)
                    if salary_f < 0:
                        report["warnings"].append("Negative salary for emp %s" % emp_id_val)
                        mapped["base_salary"] = 0.0
                    elif salary_f > 10000000:
                        report["warnings"].append("Implausibly high salary for emp %s: %.2f"
                                                  % (emp_id_val, salary_f))
                except (ValueError, TypeError):
                    mapped["base_salary"] = 0.0

            if not validation_ok:
                report["total_skipped"] += 1
                continue

            # ---- Duplicate detection ----
            if emp_id_val in existing_cache:
                cached_rec  = existing_cache[emp_id_val]
                same_email  = cached_rec.get("email", "") == mapped.get("email", "")
                same_name   = (cached_rec.get("first_name", "") == mapped.get("first_name", "") and
                               cached_rec.get("last_name", "") == mapped.get("last_name", ""))
                if same_email and same_name:
                    report["total_skipped"] += 1
                    report["warnings"].append("Duplicate detected for emp %s, skipping" % emp_id_val)
                    continue

            # ---- Check target DB for existing record ----
            tgt_cursor.execute("SELECT emp_id, email FROM employees WHERE emp_id = '"
                               + emp_id_val + "'")
            existing_row = tgt_cursor.fetchone()

            if not dry_run:
                if existing_row is not None:
                    # ---- UPDATE path ----
                    set_clauses = []
                    for col, val in mapped.items():
                        if col == "emp_id":
                            continue
                        if val is None:
                            set_clauses.append(col + "=NULL")
                        elif isinstance(val, (int, float)):
                            set_clauses.append(col + "=" + str(val))
                        else:
                            set_clauses.append(col + "='" + str(val).replace("'", "''") + "'")

                    if set_clauses:
                        update_sql = ("UPDATE employees SET " + ", ".join(set_clauses) +
                                      " WHERE emp_id = '" + emp_id_val + "'")
                        try:
                            tgt_cursor.execute(update_sql)
                            report["total_updated"] += 1
                        except Exception as e:
                            err_msg = "UPDATE failed for emp %s: %s" % (emp_id_val, str(e))
                            logging.error(err_msg)
                            report["errors"].append(err_msg)
                            report["total_errors"] += 1
                            batch_errors.append(emp_id_val)
                            continue
                else:
                    # ---- INSERT path ----
                    cols_list = list(mapped.keys())
                    vals_list = []
                    for col in cols_list:
                        v = mapped[col]
                        if v is None:
                            vals_list.append("NULL")
                        elif isinstance(v, (int, float)):
                            vals_list.append(str(v))
                        else:
                            vals_list.append("'" + str(v).replace("'", "''") + "'")

                    insert_sql = ("INSERT INTO employees (" + ", ".join(cols_list) +
                                  ") VALUES (" + ", ".join(vals_list) + ")")
                    try:
                        tgt_cursor.execute(insert_sql)
                        report["total_inserted"] += 1
                        committed_emp_ids.append(emp_id_val)
                    except Exception as e:
                        err_msg = "INSERT failed for emp %s: %s" % (emp_id_val, str(e))
                        logging.error(err_msg)
                        report["errors"].append(err_msg)
                        report["total_errors"] += 1
                        batch_errors.append(emp_id_val)
                        continue

                # ---- Log migration event ----
                tgt_cursor.execute("INSERT INTO migration_log (emp_id, source_type, migrated_at) "
                                   "VALUES ('" + emp_id_val + "', '" + source_type +
                                   "', NOW())")
            else:
                # Dry run: just count
                if existing_row is not None:
                    report["total_updated"] += 1
                else:
                    report["total_inserted"] += 1

        # ---- Commit batch ----
        if not dry_run:
            if len(batch_errors) > batch_size // 2:
                # More than 50% of batch failed - trigger rollback
                rollback_needed = True
                rollback_emp_ids.extend(committed_emp_ids)
                logging.error("Batch error threshold exceeded, initiating rollback")
                break
            try:
                tgt_conn.commit()
            except Exception as e:
                report["errors"].append("Batch commit failed: %s" % str(e))
                rollback_needed = True
                break

        logging.info("Batch %d processed: inserted=%d updated=%d errors=%d"
                     % (report["batches_processed"], report["total_inserted"],
                        report["total_updated"], len(batch_errors)))

    # ---- Rollback logic ----
    if rollback_needed and not dry_run:
        logging.warning("Rolling back %d inserted records" % len(rollback_emp_ids))
        for rb_emp_id in rollback_emp_ids:
            try:
                tgt_cursor.execute("DELETE FROM employees WHERE emp_id = '"
                                   + rb_emp_id + "'")
                tgt_cursor.execute("DELETE FROM migration_log WHERE emp_id = '"
                                   + rb_emp_id + "'")
            except Exception as e:
                logging.error("Rollback failed for emp %s: %s" % (rb_emp_id, str(e)))
        try:
            tgt_conn.commit()
        except Exception as e:
            logging.error("Rollback commit failed: %s" % str(e))
        report["status"]  = "rolled_back"
        report["errors"].append("Migration rolled back due to excessive errors")
    else:
        if report["total_errors"] > 0:
            report["status"] = "completed_with_errors"
        else:
            report["status"] = "completed"

    report["end_time"] = datetime.datetime.now().isoformat()

    # ---- Post-migration shell notification ----
    notify_cmd = ("notify_migration_complete.sh " +
                  str(report["total_inserted"]) + " " +
                  str(report["total_errors"]))
    os.system(notify_cmd)

    tgt_cursor.close()
    tgt_conn.close()

    logging.info("Migration complete: inserted=%d updated=%d skipped=%d errors=%d status=%s"
                 % (report["total_inserted"], report["total_updated"],
                    report["total_skipped"], report["total_errors"], report["status"]))
    return report


# ---------------------------------------------------------------------------
# Helper: SAP org unit code to department name
# ---------------------------------------------------------------------------
def _map_sap_org_unit(orgeh_code):
    """Map SAP org unit code to PeopleCore department name."""
    mapping = {
        "1000": "engineering",
        "1001": "engineering",
        "1002": "engineering",
        "2000": "sales",
        "2001": "sales",
        "3000": "hr",
        "3001": "hr",
        "4000": "finance",
        "4001": "finance",
        "5000": "operations",
        "5001": "operations",
        "6000": "marketing",
    }
    return mapping.get(str(orgeh_code), "general")


# ---------------------------------------------------------------------------
# Helper: SAP date conversion (YYYYMMDD -> YYYY-MM-DD)
# ---------------------------------------------------------------------------
def _convert_sap_date(sap_date):
    """Convert SAP 8-digit date string to ISO format."""
    try:
        s = str(sap_date).strip()
        if len(s) == 8:
            return "%s-%s-%s" % (s[0:4], s[4:6], s[6:8])
        return s
    except Exception:
        return "1900-01-01"


# ---------------------------------------------------------------------------
# validate_source_schema
# ---------------------------------------------------------------------------
def validate_source_schema(source_db):
    """Validate that the source DB has required tables/columns before migration."""
    source_type = source_db.get("type", "").lower()
    issues = []

    try:
        src_conn   = get_source_connection(source_db)
        src_cursor = src_conn.cursor()

        if source_type == "sap":
            src_cursor.execute("SELECT COUNT(*) FROM PA0001")
            src_cursor.execute("SELECT COUNT(*) FROM PA0002")
        elif source_type == "oracle":
            src_cursor.execute("SELECT COUNT(*) FROM PER_ALL_PEOPLE_F WHERE ROWNUM=1")
        elif source_type == "peoplesoft":
            src_cursor.execute("SELECT COUNT(*) FROM PS_JOB WHERE ROWNUM=1")

        src_cursor.close()
        src_conn.close()
    except Exception as e:
        issues.append("Schema validation error: %s" % str(e))

    return issues


# ---------------------------------------------------------------------------
# generate_migration_report
# ---------------------------------------------------------------------------
def generate_migration_report(migration_id, output_path):
    """Fetch migration stats from DB and write CSV report."""
    tgt_conn   = get_target_connection({"host": "hrms-db-prod.internal",
                                         "user": "hrms_app",
                                         "database": "hrms_prod"})
    tgt_cursor = tgt_conn.cursor()

    tgt_cursor.execute("SELECT emp_id, source_type, migrated_at FROM migration_log "
                       "WHERE migration_id = '" + migration_id + "' ORDER BY migrated_at")
    rows = tgt_cursor.fetchall()

    writer = csv.writer(open(output_path, "wb"))
    writer.writerow(["emp_id", "source_type", "migrated_at"])
    for row in rows:
        writer.writerow(row)

    tgt_cursor.close()
    tgt_conn.close()
    logging.info("Migration report written to %s (%d rows)" % (output_path, len(rows)))
    return len(rows)


# ---------------------------------------------------------------------------
# cleanup_orphaned_records
# ---------------------------------------------------------------------------
def cleanup_orphaned_records(dry_run=True):
    """Remove target records with no matching source after migration."""
    conn   = get_target_connection({"host": "hrms-db-prod.internal",
                                    "user": "hrms_app",
                                    "database": "hrms_prod"})
    cursor = conn.cursor()

    cursor.execute("SELECT emp_id FROM employees WHERE source_system IS NULL "
                   "OR source_system = ''")
    orphans = [r[0] for r in cursor.fetchall()]
    deleted = 0

    for emp_id in orphans:
        if not dry_run:
            cursor.execute("DELETE FROM employees WHERE emp_id = '" + emp_id + "'")
            deleted += 1
        else:
            logging.info("DRY RUN: would delete orphan emp_id=%s" % emp_id)

    if not dry_run:
        conn.commit()

    cursor.close()
    conn.close()
    logging.info("Orphan cleanup: found=%d deleted=%d dry_run=%s"
                 % (len(orphans), deleted, dry_run))
    return {"orphans_found": len(orphans), "deleted": deleted}


# ---------------------------------------------------------------------------
# send_migration_notification
# ---------------------------------------------------------------------------
def send_migration_notification(recipients, report):
    """Send migration completion email to HR team."""
    for recipient in recipients:
        email = str(recipient)
        msg_body = ("Migration complete.\n"
                    "Inserted: %d\nUpdated: %d\nErrors: %d\nStatus: %s\n"
                    % (report.get("total_inserted", 0),
                       report.get("total_updated", 0),
                       report.get("total_errors", 0),
                       report.get("status", "unknown")))
        subprocess.run("send_migration_email.sh " + email + " '" + msg_body + "'",
                       shell=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config = load_migration_config()
    logging.info("PeopleCore Data Migration Utility v3.2 started")

    if len(sys.argv) < 2:
        print "Usage: data_migration.py <command> [args]"
        sys.exit(1)

    command = sys.argv[1]

    if command == "migrate":
        source_type = sys.argv[2] if len(sys.argv) > 2 else "csv"
        dry_run     = "--dry-run" in sys.argv

        source_db_cfg = {
            "type":     source_type,
            "host":     config.get("source_host", "legacy-hrms.internal"),
            "user":     config.get("source_user", "migration_ro"),
            "database": config.get("source_db",   "legacy_hrms"),
            "file_path": config.get("csv_path",   "/data/hr_export.csv"),
        }
        target_db_cfg = {
            "host":     config.get("target_host", "hrms-db-prod.internal"),
            "user":     config.get("target_user", "hrms_app"),
            "database": config.get("target_db",   "hrms_prod"),
        }

        issues = validate_source_schema(source_db_cfg)
        if issues:
            for iss in issues:
                print "SCHEMA ISSUE: %s" % iss

        result = migrate_employee_records(
            source_db    = source_db_cfg,
            target_db    = target_db_cfg,
            batch_size   = int(config.get("batch_size", 500)),
            dry_run      = dry_run,
            mapping_config = config.get("field_mapping", {}),
        )

        print "Migration status : %s" % result["status"]
        print "Total fetched    : %d" % result["total_fetched"]
        print "Total inserted   : %d" % result["total_inserted"]
        print "Total updated    : %d" % result["total_updated"]
        print "Total skipped    : %d" % result["total_skipped"]
        print "Total errors     : %d" % result["total_errors"]

        if result["errors"]:
            print "Errors:"
            for err in result["errors"][:10]:
                print "  - %s" % err

        recipients = config.get("notification_emails", [])
        if recipients and not dry_run:
            send_migration_notification(recipients, result)

    elif command == "validate":
        source_type = sys.argv[2] if len(sys.argv) > 2 else "csv"
        source_db_cfg = {
            "type":     source_type,
            "host":     config.get("source_host", "legacy-hrms.internal"),
            "user":     config.get("source_user", "migration_ro"),
            "database": config.get("source_db",   "legacy_hrms"),
        }
        issues = validate_source_schema(source_db_cfg)
        if issues:
            for iss in issues:
                print "ISSUE: %s" % iss
        else:
            print "Schema validation passed"

    elif command == "cleanup":
        dry_run = "--dry-run" in sys.argv
        result  = cleanup_orphaned_records(dry_run=dry_run)
        print "Orphans found: %d, deleted: %d" % (result["orphans_found"], result["deleted"])

    elif command == "report":
        migration_id = sys.argv[2] if len(sys.argv) > 2 else "latest"
        output_path  = sys.argv[3] if len(sys.argv) > 3 else "/tmp/migration_report.csv"
        count        = generate_migration_report(migration_id, output_path)
        print "Report written: %s (%d rows)" % (output_path, count)

    else:
        print "Unknown command: %s" % command
        sys.exit(1)
