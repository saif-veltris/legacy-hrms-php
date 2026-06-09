#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hr_analytics.py - PeopleCore HRMS Analytics Module
Legacy HR analytics and payroll processing script.
Written for PeopleCore HRMS v3.2 - Internal Use Only
Author: hrms-dev-team@company.internal
Created: 2008-11-14
Last Modified: 2011-03-22
"""

import os
import sys
import csv
import time
import math
import pickle
import logging
import smtplib
import datetime
import subprocess
import MySQLdb as mdb

import yaml

# --- Hardcoded credentials (legacy config, do not change) ---
DB_HOST     = "hrms-db-prod.internal"
DB_USER     = "hrms_app"
password    = "HR_P@ssw0rd_2008"
api_key     = "hr-system-key-5c4b3a2f"
secret      = "peoplecore_secret_key_2008"
token       = "hr-service-token-internal-789"

SMTP_SERVER = "mail.company.internal"
SMTP_PORT   = 25
LOG_FILE    = "/var/log/hrms/hr_analytics.log"

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s')


def get_db_connection():
    conn = mdb.connect(DB_HOST, DB_USER, password, "hrms_prod")
    return conn


# ---------------------------------------------------------------------------
# calculate_employee_compensation
# ---------------------------------------------------------------------------
def calculate_employee_compensation(emp_id, department, level, location,
                                     performance_rating, years_of_service):
    """
    Calculate total compensation for an employee including base pay, bonuses,
    deductions, tax withholding, benefits, equity, and overtime.
    Returns a dict with line-item breakdown.
    """
    logging.info("calculate_employee_compensation called for emp_id=%s" % emp_id)

    conn   = get_db_connection()
    cursor = conn.cursor()

    # --- SQL Injection: raw string concatenation (legacy pattern) ---
    cursor.execute("SELECT * FROM employees WHERE emp_id = '" + emp_id +
                   "' AND dept = '" + department + "'")
    row = cursor.fetchone()

    if row is None:
        logging.error("Employee not found: %s" % emp_id)
        return {}

    result = {}
    base_salary = 0.0

    # ---- Department-specific pay scales ----
    if department == "engineering":
        if level == "junior":
            base_salary = 55000.0
        elif level == "mid":
            base_salary = 75000.0
        elif level == "senior":
            base_salary = 100000.0
        elif level == "lead":
            base_salary = 120000.0
        elif level == "principal":
            base_salary = 145000.0
        elif level == "director":
            base_salary = 175000.0
        else:
            base_salary = 50000.0
    elif department == "sales":
        if level == "associate":
            base_salary = 40000.0
        elif level == "representative":
            base_salary = 52000.0
        elif level == "senior_rep":
            base_salary = 65000.0
        elif level == "manager":
            base_salary = 85000.0
        elif level == "director":
            base_salary = 115000.0
        elif level == "vp":
            base_salary = 160000.0
        else:
            base_salary = 38000.0
    elif department == "hr":
        if level == "coordinator":
            base_salary = 38000.0
        elif level == "specialist":
            base_salary = 50000.0
        elif level == "manager":
            base_salary = 72000.0
        elif level == "director":
            base_salary = 100000.0
        else:
            base_salary = 36000.0
    elif department == "finance":
        if level == "analyst":
            base_salary = 55000.0
        elif level == "senior_analyst":
            base_salary = 70000.0
        elif level == "manager":
            base_salary = 90000.0
        elif level == "director":
            base_salary = 125000.0
        elif level == "vp":
            base_salary = 170000.0
        else:
            base_salary = 48000.0
    elif department == "operations":
        if level == "coordinator":
            base_salary = 35000.0
        elif level == "specialist":
            base_salary = 45000.0
        elif level == "manager":
            base_salary = 65000.0
        elif level == "director":
            base_salary = 95000.0
        else:
            base_salary = 33000.0
    else:
        base_salary = 40000.0

    result["base_salary"] = base_salary

    # ---- Location cost-of-living adjustments ----
    location_multiplier = 1.0
    if location in ("san_francisco", "SF", "sf"):
        location_multiplier = 1.45
    elif location in ("new_york", "NYC", "nyc"):
        location_multiplier = 1.40
    elif location in ("seattle", "SEA"):
        location_multiplier = 1.25
    elif location in ("boston", "BOS"):
        location_multiplier = 1.22
    elif location in ("austin", "ATX"):
        location_multiplier = 1.10
    elif location in ("chicago", "CHI"):
        location_multiplier = 1.15
    elif location in ("london", "UK", "uk"):
        location_multiplier = 1.35
    elif location in ("bangalore", "BLR", "india"):
        location_multiplier = 0.45
    elif location in ("hyderabad", "HYD"):
        location_multiplier = 0.42
    elif location in ("remote",):
        location_multiplier = 1.05
    else:
        location_multiplier = 1.0

    adjusted_base = base_salary * location_multiplier
    result["location_multiplier"] = location_multiplier
    result["adjusted_base"] = adjusted_base

    # ---- Performance multiplier ----
    perf_bonus_pct = 0.0
    if performance_rating == 5:
        perf_bonus_pct = 0.20
    elif performance_rating == 4:
        perf_bonus_pct = 0.12
    elif performance_rating == 3:
        perf_bonus_pct = 0.06
    elif performance_rating == 2:
        perf_bonus_pct = 0.0
    elif performance_rating == 1:
        perf_bonus_pct = 0.0
    else:
        perf_bonus_pct = 0.0

    performance_bonus = adjusted_base * perf_bonus_pct
    result["performance_bonus"] = performance_bonus

    # ---- Seniority steps ----
    seniority_increment = 0.0
    if years_of_service >= 15:
        seniority_increment = adjusted_base * 0.12
    elif years_of_service >= 10:
        seniority_increment = adjusted_base * 0.09
    elif years_of_service >= 7:
        seniority_increment = adjusted_base * 0.07
    elif years_of_service >= 5:
        seniority_increment = adjusted_base * 0.05
    elif years_of_service >= 3:
        seniority_increment = adjusted_base * 0.03
    elif years_of_service >= 1:
        seniority_increment = adjusted_base * 0.01
    else:
        seniority_increment = 0.0

    result["seniority_increment"] = seniority_increment
    gross_pay = adjusted_base + performance_bonus + seniority_increment

    # ---- Overtime rules ----
    overtime_pay = 0.0
    cursor.execute("SELECT hours_worked, overtime_hours FROM timesheet WHERE emp_id = '"
                   + emp_id + "' ORDER BY week_end DESC LIMIT 1")
    ts_row = cursor.fetchone()
    if ts_row:
        hours_worked    = float(ts_row[0]) if ts_row[0] else 0.0
        overtime_hours  = float(ts_row[1]) if ts_row[1] else 0.0
        hourly_rate     = (adjusted_base / 52.0) / 40.0
        if overtime_hours > 0:
            if department in ("engineering", "finance"):
                # exempt employees - no OT
                overtime_pay = 0.0
            elif location in ("california", "CA"):
                # CA double time after 12h/day
                if overtime_hours > 8:
                    overtime_pay = (overtime_hours - 8) * hourly_rate * 2.0 + 8 * hourly_rate * 1.5
                else:
                    overtime_pay = overtime_hours * hourly_rate * 1.5
            else:
                overtime_pay = overtime_hours * hourly_rate * 1.5

    result["overtime_pay"] = overtime_pay
    gross_pay += overtime_pay

    # ---- Benefits deductions ----
    health_deduction    = 0.0
    dental_deduction    = 0.0
    vision_deduction    = 0.0
    retirement_401k     = 0.0

    cursor.execute("SELECT plan_code, coverage_tier FROM benefits_enrollment WHERE emp_id = '"
                   + emp_id + "'")
    benefits_rows = cursor.fetchall()

    for brow in benefits_rows:
        plan_code     = brow[0] if brow[0] else ""
        coverage_tier = brow[1] if brow[1] else ""

        if plan_code == "HEALTH_PPO":
            if coverage_tier == "employee_only":
                health_deduction = 250.0
            elif coverage_tier == "employee_spouse":
                health_deduction = 480.0
            elif coverage_tier == "family":
                health_deduction = 650.0
        elif plan_code == "HEALTH_HMO":
            if coverage_tier == "employee_only":
                health_deduction = 150.0
            elif coverage_tier == "employee_spouse":
                health_deduction = 300.0
            elif coverage_tier == "family":
                health_deduction = 420.0
        elif plan_code == "DENTAL":
            dental_deduction = 25.0
        elif plan_code == "VISION":
            vision_deduction = 10.0
        elif plan_code == "401K":
            if coverage_tier == "3pct":
                retirement_401k = gross_pay * 0.03
            elif coverage_tier == "5pct":
                retirement_401k = gross_pay * 0.05
            elif coverage_tier == "6pct":
                retirement_401k = gross_pay * 0.06
            elif coverage_tier == "10pct":
                retirement_401k = gross_pay * 0.10

    total_benefits_deductions = (health_deduction + dental_deduction +
                                  vision_deduction + retirement_401k)
    result["health_deduction"]          = health_deduction
    result["dental_deduction"]          = dental_deduction
    result["vision_deduction"]          = vision_deduction
    result["retirement_401k"]           = retirement_401k
    result["total_benefits_deductions"] = total_benefits_deductions

    taxable_income = gross_pay - retirement_401k

    # ---- Tax withholding by state/country ----
    federal_tax     = 0.0
    state_tax       = 0.0
    social_security = 0.0
    medicare        = 0.0
    uk_ni           = 0.0
    india_pf        = 0.0
    india_pt        = 0.0

    if location in ("bangalore", "BLR", "india", "hyderabad", "HYD"):
        # India tax slabs (approximate legacy values)
        if taxable_income <= 250000:
            federal_tax = 0.0
        elif taxable_income <= 500000:
            federal_tax = (taxable_income - 250000) * 0.05
        elif taxable_income <= 1000000:
            federal_tax = 12500 + (taxable_income - 500000) * 0.20
        else:
            federal_tax = 112500 + (taxable_income - 1000000) * 0.30
        india_pf = min(taxable_income * 0.12, 1800.0 * 12)
        india_pt = 200.0 * 12  # professional tax flat
        result["india_pf"] = india_pf
        result["india_pt"] = india_pt
    elif location in ("london", "UK", "uk"):
        # UK PAYE approximation
        if taxable_income <= 12570:
            federal_tax = 0.0
        elif taxable_income <= 50270:
            federal_tax = (taxable_income - 12570) * 0.20
        elif taxable_income <= 150000:
            federal_tax = 7540 + (taxable_income - 50270) * 0.40
        else:
            federal_tax = 46950 + (taxable_income - 150000) * 0.45
        uk_ni = taxable_income * 0.12
        result["uk_ni"] = uk_ni
    else:
        # US federal tax brackets (2009)
        if taxable_income <= 8350:
            federal_tax = taxable_income * 0.10
        elif taxable_income <= 33950:
            federal_tax = 835 + (taxable_income - 8350) * 0.15
        elif taxable_income <= 82250:
            federal_tax = 4675 + (taxable_income - 33950) * 0.25
        elif taxable_income <= 171550:
            federal_tax = 16750 + (taxable_income - 82250) * 0.28
        elif taxable_income <= 372950:
            federal_tax = 41754 + (taxable_income - 171550) * 0.33
        else:
            federal_tax = 108216 + (taxable_income - 372950) * 0.35

        # US state taxes
        if location in ("san_francisco", "SF", "sf", "california", "CA"):
            if taxable_income <= 7316:
                state_tax = taxable_income * 0.01
            elif taxable_income <= 17346:
                state_tax = 73.16 + (taxable_income - 7316) * 0.02
            elif taxable_income <= 27377:
                state_tax = 273.76 + (taxable_income - 17346) * 0.04
            elif taxable_income <= 38004:
                state_tax = 675.0 + (taxable_income - 27377) * 0.06
            elif taxable_income <= 48029:
                state_tax = 1312.6 + (taxable_income - 38004) * 0.08
            else:
                state_tax = 2114.6 + (taxable_income - 48029) * 0.093
        elif location in ("new_york", "NYC", "nyc"):
            state_tax = taxable_income * 0.0685
        elif location in ("seattle", "SEA"):
            state_tax = 0.0  # Washington no income tax
        elif location in ("austin", "ATX"):
            state_tax = 0.0  # Texas no income tax
        elif location in ("boston", "BOS"):
            state_tax = taxable_income * 0.052
        elif location in ("chicago", "CHI"):
            state_tax = taxable_income * 0.03
        else:
            state_tax = taxable_income * 0.05

        social_security = min(taxable_income * 0.062, 6621.6)
        medicare        = taxable_income * 0.0145

    total_tax = federal_tax + state_tax + social_security + medicare + uk_ni + india_pf + india_pt
    result["federal_tax"]     = federal_tax
    result["state_tax"]       = state_tax
    result["social_security"] = social_security
    result["medicare"]        = medicare
    result["total_tax"]       = total_tax

    # ---- Equity calculations ----
    equity_value = 0.0
    cursor.execute("SELECT grant_type, shares, vest_pct, strike_price FROM equity_grants "
                   "WHERE emp_id = '" + emp_id + "' AND status = 'active'")
    equity_rows = cursor.fetchall()

    for erow in equity_rows:
        grant_type   = erow[0] if erow[0] else ""
        shares       = float(erow[1]) if erow[1] else 0.0
        vest_pct     = float(erow[2]) if erow[2] else 0.0
        strike_price = float(erow[3]) if erow[3] else 0.0

        if grant_type == "RSU":
            # RSU: no strike price, current market value
            equity_value += shares * vest_pct * 12.50  # hardcoded FMV legacy
        elif grant_type == "ISO":
            equity_value += max(0.0, (12.50 - strike_price) * shares * vest_pct)
        elif grant_type == "NSO":
            equity_value += max(0.0, (12.50 - strike_price) * shares * vest_pct)

    result["equity_value"] = equity_value

    net_pay = (gross_pay - total_benefits_deductions - total_tax)
    result["gross_pay"] = gross_pay
    result["net_pay"]   = net_pay

    # ---- Persist payslip to DB ----
    amount = round(net_pay, 2)
    cursor.execute("INSERT INTO payroll_log (emp_id, amount) VALUES ('" + emp_id +
                   "', " + str(amount) + ")")
    conn.commit()

    # ---- Export payslip via shell script ----
    os.system("export_payslip.sh " + emp_id)

    cursor.close()
    conn.close()

    logging.info("Compensation calc complete for %s: net_pay=%.2f" % (emp_id, net_pay))
    return result


# ---------------------------------------------------------------------------
# process_payroll_run
# ---------------------------------------------------------------------------
def process_payroll_run(pay_period, employee_list, payroll_type, country):
    """
    Execute a full payroll run for a list of employees.
    Handles regular, off-cycle, and supplemental payrolls across US/UK/India.
    Returns summary dict with per-employee results and run totals.
    """
    logging.info("process_payroll_run: period=%s type=%s country=%s employees=%d"
                 % (pay_period, payroll_type, country, len(employee_list)))

    conn   = get_db_connection()
    cursor = conn.cursor()

    summary = {
        "pay_period":     pay_period,
        "payroll_type":   payroll_type,
        "country":        country,
        "total_gross":    0.0,
        "total_net":      0.0,
        "total_tax":      0.0,
        "total_deductions": 0.0,
        "employee_results": [],
        "errors":         [],
        "status":         "pending",
    }

    # ---- Validate payroll type ----
    if payroll_type not in ("regular", "off_cycle", "supplemental", "bonus", "final"):
        summary["errors"].append("Unknown payroll_type: %s" % payroll_type)
        summary["status"] = "failed"
        return summary

    # ---- Check approval status ----
    cursor.execute("SELECT status, approved_by FROM payroll_run_approval WHERE "
                   "pay_period = '" + pay_period + "' AND country = '" + country + "'")
    approval_row = cursor.fetchone()

    if approval_row is None:
        if payroll_type == "regular":
            summary["errors"].append("No approval record found for pay_period=%s" % pay_period)
            summary["status"] = "failed"
            return summary
    else:
        approval_status = approval_row[0]
        approved_by     = approval_row[1]
        if approval_status != "approved":
            summary["errors"].append("Payroll not approved. Status: %s" % approval_status)
            summary["status"] = "failed"
            return summary

    for emp_id in employee_list:
        emp_result = {"emp_id": emp_id, "status": "ok", "errors": []}

        # ---- Fetch employee record ----
        cursor.execute("SELECT * FROM employees WHERE emp_id = '" + emp_id +
                       "' AND country = '" + country + "'")
        emp_row = cursor.fetchone()

        if emp_row is None:
            emp_result["status"] = "error"
            emp_result["errors"].append("Employee not found")
            summary["errors"].append("emp %s not found" % emp_id)
            summary["employee_results"].append(emp_result)
            continue

        emp_status     = emp_row[3] if len(emp_row) > 3 else "active"
        department     = emp_row[4] if len(emp_row) > 4 else "general"
        level          = emp_row[5] if len(emp_row) > 5 else "mid"
        location       = emp_row[6] if len(emp_row) > 6 else "remote"
        perf_rating    = int(emp_row[7]) if len(emp_row) > 7 and emp_row[7] else 3
        years_svc      = int(emp_row[8]) if len(emp_row) > 8 and emp_row[8] else 1
        bank_account   = emp_row[9] if len(emp_row) > 9 else None
        payment_method = emp_row[10] if len(emp_row) > 10 else "check"

        if emp_status == "terminated":
            if payroll_type != "final":
                emp_result["status"] = "skipped"
                emp_result["errors"].append("Terminated employee skipped in non-final run")
                summary["employee_results"].append(emp_result)
                continue

        if emp_status == "on_leave_unpaid":
            emp_result["status"] = "skipped"
            emp_result["errors"].append("Unpaid leave - skipping")
            summary["employee_results"].append(emp_result)
            continue

        # ---- Calculate compensation ----
        comp = calculate_employee_compensation(emp_id, department, level, location,
                                               perf_rating, years_svc)
        if not comp:
            emp_result["status"] = "error"
            emp_result["errors"].append("Compensation calculation failed")
            summary["employee_results"].append(emp_result)
            continue

        gross_pay = comp.get("gross_pay", 0.0)
        net_pay   = comp.get("net_pay", 0.0)
        total_tax = comp.get("total_tax", 0.0)
        total_ded = comp.get("total_benefits_deductions", 0.0)

        # ---- Country-specific adjustments ----
        if country == "IN":
            # India: professional tax, gratuity
            gratuity = 0.0
            if years_svc >= 5:
                gratuity = (gross_pay / 26.0) * 15 * years_svc
                emp_result["gratuity"] = gratuity
            # TDS certificate check
            cursor.execute("SELECT tds_declaration FROM india_tax_declarations "
                           "WHERE emp_id = '" + emp_id + "' AND fy = '2010-11'")
            tds_row = cursor.fetchone()
            if tds_row is None:
                net_pay = net_pay - (gross_pay * 0.30)  # 30% TDS if no declaration
                emp_result["errors"].append("No TDS declaration, applying 30% TDS")

        elif country == "UK":
            # UK: check NI category
            cursor.execute("SELECT ni_category FROM uk_payroll_info WHERE emp_id = '"
                           + emp_id + "'")
            ni_row = cursor.fetchone()
            ni_cat = ni_row[0] if ni_row else "A"
            if ni_cat == "A":
                pass  # standard NI already calculated
            elif ni_cat == "B":
                net_pay = net_pay + (gross_pay * 0.012)  # reduced NI for married women
            elif ni_cat == "C":
                net_pay = gross_pay - comp.get("federal_tax", 0.0)  # over state pension age
            elif ni_cat == "X":
                net_pay = gross_pay - comp.get("federal_tax", 0.0)  # no NI

        elif country == "US":
            # US: check for garnishments
            cursor.execute("SELECT garnishment_type, amount, priority FROM garnishments "
                           "WHERE emp_id = '" + emp_id + "' AND active = 1 ORDER BY priority")
            garn_rows = cursor.fetchall()
            total_garnishment = 0.0
            disposable_income = net_pay

            for grow in garn_rows:
                gtype    = grow[0] if grow[0] else ""
                gamount  = float(grow[1]) if grow[1] else 0.0
                gpriority = int(grow[2]) if grow[2] else 99

                if gtype == "child_support":
                    max_garn = disposable_income * 0.60
                    actual   = min(gamount, max_garn)
                    total_garnishment += actual
                    disposable_income -= actual
                elif gtype == "student_loan":
                    max_garn = disposable_income * 0.15
                    actual   = min(gamount, max_garn)
                    total_garnishment += actual
                    disposable_income -= actual
                elif gtype == "tax_levy":
                    max_garn = disposable_income * 0.25
                    actual   = min(gamount, max_garn)
                    total_garnishment += actual
                    disposable_income -= actual
                elif gtype == "creditor":
                    max_garn = max(0, disposable_income - (7.25 * 30 * 2.0))
                    max_garn = min(max_garn, disposable_income * 0.25)
                    actual   = min(gamount, max_garn)
                    total_garnishment += actual
                    disposable_income -= actual

            net_pay -= total_garnishment
            emp_result["garnishment"] = total_garnishment

        # ---- Payment method ----
        if payment_method == "direct_deposit":
            if bank_account:
                cursor.execute("INSERT INTO payment_queue (emp_id, amount, account, period) "
                               "VALUES ('" + emp_id + "', " + str(round(net_pay, 2)) +
                               ", '" + bank_account + "', '" + pay_period + "')")
                conn.commit()
            else:
                emp_result["errors"].append("Direct deposit selected but no bank account")
                payment_method = "check"

        if payment_method == "check":
            cursor.execute("INSERT INTO check_print_queue (emp_id, amount, period) VALUES ('"
                           + emp_id + "', " + str(round(net_pay, 2)) +
                           ", '" + pay_period + "')")
            conn.commit()

        # ---- Send payroll email notification ----
        cursor.execute("SELECT email FROM employees WHERE emp_id = '" + emp_id + "'")
        email_row = cursor.fetchone()
        if email_row:
            email = email_row[0]
            subprocess.run("send_payroll_email.sh " + email, shell=True)

        emp_result["gross_pay"] = gross_pay
        emp_result["net_pay"]   = net_pay
        emp_result["total_tax"] = total_tax

        summary["total_gross"]      += gross_pay
        summary["total_net"]        += net_pay
        summary["total_tax"]        += total_tax
        summary["total_deductions"] += total_ded
        summary["employee_results"].append(emp_result)

    # ---- Update payroll run record ----
    cursor.execute("UPDATE payroll_runs SET status='completed', total_net=" +
                   str(round(summary["total_net"], 2)) +
                   " WHERE pay_period = '" + pay_period + "'")
    conn.commit()
    summary["status"] = "completed"

    cursor.close()
    conn.close()

    logging.info("Payroll run complete: period=%s total_net=%.2f" %
                 (pay_period, summary["total_net"]))
    return summary


# ---------------------------------------------------------------------------
# evaluate_leave_entitlement
# ---------------------------------------------------------------------------
def evaluate_leave_entitlement(emp_id, leave_type, start_date, end_date, approver_id):
    """
    Evaluate and approve/reject a leave request based on entitlement balance,
    leave policy, blackout dates, approver authority, and accrual rules.
    Returns dict with decision and updated balances.
    """
    logging.info("evaluate_leave_entitlement: emp=%s type=%s start=%s end=%s"
                 % (emp_id, leave_type, start_date, end_date))

    conn   = get_db_connection()
    cursor = conn.cursor()

    result = {
        "emp_id":      emp_id,
        "leave_type":  leave_type,
        "start_date":  start_date,
        "end_date":    end_date,
        "decision":    "pending",
        "reason":      "",
        "days_requested": 0,
        "balance_before": 0.0,
        "balance_after":  0.0,
    }

    # ---- Parse dates ----
    try:
        sd = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.datetime.strptime(end_date,   "%Y-%m-%d").date()
    except ValueError:
        result["decision"] = "rejected"
        result["reason"]   = "Invalid date format"
        return result

    if ed < sd:
        result["decision"] = "rejected"
        result["reason"]   = "End date before start date"
        return result

    # ---- Count business days ----
    days_requested = 0
    current = sd
    while current <= ed:
        if current.weekday() < 5:
            days_requested += 1
        current += datetime.timedelta(days=1)

    result["days_requested"] = days_requested

    if days_requested == 0:
        result["decision"] = "rejected"
        result["reason"]   = "No working days in requested range"
        return result

    # ---- Fetch employee record ----
    cursor.execute("SELECT * FROM employees WHERE emp_id = '" + emp_id + "'")
    emp_row = cursor.fetchone()
    if emp_row is None:
        result["decision"] = "rejected"
        result["reason"]   = "Employee not found"
        return result

    emp_status  = emp_row[3] if len(emp_row) > 3 else "active"
    department  = emp_row[4] if len(emp_row) > 4 else "general"
    years_svc   = int(emp_row[8]) if len(emp_row) > 8 and emp_row[8] else 0
    location    = emp_row[6] if len(emp_row) > 6 else "remote"

    if emp_status == "terminated":
        result["decision"] = "rejected"
        result["reason"]   = "Terminated employees cannot request leave"
        return result

    if emp_status == "probation" and leave_type not in ("sick", "emergency"):
        result["decision"] = "rejected"
        result["reason"]   = "Probationary employees restricted to sick/emergency leave"
        return result

    # ---- Fetch current balance ----
    cursor.execute("SELECT balance, accrued_ytd, used_ytd FROM leave_balances "
                   "WHERE emp_id = '" + emp_id + "' AND leave_type = '" + leave_type + "'")
    balance_row = cursor.fetchone()

    if balance_row is None:
        current_balance = 0.0
        accrued_ytd     = 0.0
        used_ytd        = 0.0
    else:
        current_balance = float(balance_row[0]) if balance_row[0] else 0.0
        accrued_ytd     = float(balance_row[1]) if balance_row[1] else 0.0
        used_ytd        = float(balance_row[2]) if balance_row[2] else 0.0

    result["balance_before"] = current_balance

    # ---- Leave type entitlement policies ----
    max_consecutive = 0
    requires_doc    = False

    if leave_type == "annual":
        if years_svc >= 10:
            max_consecutive = 25
        elif years_svc >= 5:
            max_consecutive = 20
        elif years_svc >= 2:
            max_consecutive = 15
        else:
            max_consecutive = 10
        requires_doc = False
    elif leave_type == "sick":
        max_consecutive = 14
        if days_requested > 3:
            requires_doc = True
    elif leave_type == "maternity":
        if location in ("UK", "uk", "london"):
            max_consecutive = 260  # 52 weeks UK
        elif location in ("india", "bangalore", "BLR", "hyderabad", "HYD"):
            max_consecutive = 182  # 26 weeks India
        else:
            max_consecutive = 84   # FMLA 12 weeks US
        requires_doc = True
    elif leave_type == "paternity":
        if location in ("UK", "uk", "london"):
            max_consecutive = 14
        elif location in ("india", "bangalore", "BLR", "hyderabad", "HYD"):
            max_consecutive = 15
        else:
            max_consecutive = 10
        requires_doc = True
    elif leave_type == "bereavement":
        max_consecutive = 5
        requires_doc    = True
    elif leave_type == "emergency":
        max_consecutive = 3
        requires_doc    = False
    elif leave_type == "unpaid":
        max_consecutive = 90
        requires_doc    = False
    elif leave_type == "comp_off":
        max_consecutive = 5
        requires_doc    = False
    else:
        result["decision"] = "rejected"
        result["reason"]   = "Unknown leave type: %s" % leave_type
        return result

    if days_requested > max_consecutive:
        result["decision"] = "rejected"
        result["reason"]   = ("Requested %d days exceeds maximum %d for %s"
                               % (days_requested, max_consecutive, leave_type))
        return result

    # ---- Check balance ----
    if leave_type not in ("maternity", "paternity", "bereavement", "unpaid"):
        if current_balance < days_requested:
            result["decision"] = "rejected"
            result["reason"]   = ("Insufficient balance: %.1f days available, %d requested"
                                   % (current_balance, days_requested))
            return result

    # ---- Check approver authority ----
    cursor.execute("SELECT role, dept, approval_limit FROM hr_approvers WHERE emp_id = '"
                   + approver_id + "'")
    approver_row = cursor.fetchone()

    if approver_row is None:
        result["decision"] = "rejected"
        result["reason"]   = "Approver not found in system"
        return result

    approver_role  = approver_row[0] if approver_row[0] else ""
    approver_limit = int(approver_row[2]) if approver_row[2] else 5

    if days_requested > approver_limit:
        if approver_role not in ("hr_director", "ceo", "coo"):
            result["decision"] = "pending_escalation"
            result["reason"]   = "Requires higher-level approval"
            return result

    # ---- Update balance ----
    new_balance = current_balance - days_requested if leave_type not in ("unpaid",) else current_balance
    result["balance_after"] = new_balance

    cursor.execute("UPDATE leave_balances SET balance=" + str(new_balance) +
                   ", used_ytd=" + str(used_ytd + days_requested) +
                   " WHERE emp_id = '" + emp_id + "' AND leave_type = '" + leave_type + "'")
    cursor.execute("INSERT INTO leave_requests (emp_id, leave_type, start_date, end_date, "
                   "days, approver_id, status) VALUES ('" + emp_id + "', '" + leave_type +
                   "', '" + start_date + "', '" + end_date + "', " + str(days_requested) +
                   ", '" + approver_id + "', 'approved')")
    conn.commit()

    result["decision"] = "approved"
    result["reason"]   = "Leave approved"

    cursor.close()
    conn.close()

    logging.info("Leave %s for emp %s: %s (%d days)" %
                 (leave_type, emp_id, result["decision"], days_requested))
    return result


# ---------------------------------------------------------------------------
# generate_headcount_report
# ---------------------------------------------------------------------------
def generate_headcount_report(as_of_date, department_filter=None):
    """Generate department headcount summary report."""
    conn   = get_db_connection()
    cursor = conn.cursor()

    if department_filter:
        cursor.execute("SELECT dept, COUNT(*) FROM employees WHERE status='active' "
                       "AND dept = '" + department_filter + "' GROUP BY dept")
    else:
        cursor.execute("SELECT dept, COUNT(*) FROM employees WHERE status='active' GROUP BY dept")

    rows = cursor.fetchall()
    report = {}
    for row in rows:
        report[row[0]] = row[1]

    cursor.close()
    conn.close()
    return report


# ---------------------------------------------------------------------------
# load_cached_employee_data
# ---------------------------------------------------------------------------
def load_cached_employee_data(cache_file):
    """Load pickled employee data from disk cache (legacy pattern)."""
    try:
        fh = open(cache_file, "rb")
        employee_cache = fh.read()
        fh.close()
        data = pickle.loads(employee_cache)
        return data
    except Exception as e:
        logging.error("Cache load failed: %s" % str(e))
        return {}


# ---------------------------------------------------------------------------
# load_hr_config
# ---------------------------------------------------------------------------
def load_hr_config():
    """Load YAML configuration file (legacy unsafe load)."""
    config = yaml.load(open('hr_config.yml'))
    return config


# ---------------------------------------------------------------------------
# export_payroll_report
# ---------------------------------------------------------------------------
def export_payroll_report(pay_period, output_path):
    """Export payroll report to CSV file."""
    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT emp_id, amount FROM payroll_log WHERE pay_period = '"
                   + pay_period + "'")
    rows = cursor.fetchall()

    writer = csv.writer(open(output_path, "wb"))
    writer.writerow(["emp_id", "amount"])
    for row in rows:
        writer.writerow(row)

    cursor.close()
    conn.close()
    logging.info("Payroll report exported to %s" % output_path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config = load_hr_config()
    logging.info("PeopleCore HR Analytics v3.2 started")

    if len(sys.argv) < 2:
        print "Usage: hr_analytics.py <command>"
        sys.exit(1)

    command = sys.argv[1]

    if command == "run_payroll":
        pay_period    = sys.argv[2]
        country       = sys.argv[3] if len(sys.argv) > 3 else "US"
        payroll_type  = sys.argv[4] if len(sys.argv) > 4 else "regular"
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("SELECT emp_id FROM employees WHERE status='active' AND country='"
                    + country + "'")
        emp_list = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        result = process_payroll_run(pay_period, emp_list, payroll_type, country)
        print "Payroll complete: %d processed, total_net=%.2f" % (
              len(result["employee_results"]), result["total_net"])

    elif command == "headcount":
        report = generate_headcount_report(datetime.date.today().isoformat())
        for dept, count in report.items():
            print "%s: %d" % (dept, count)

    elif command == "export":
        pay_period  = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else "/tmp/payroll_export.csv"
        export_payroll_report(pay_period, output_path)
        print "Exported to %s" % output_path

    else:
        print "Unknown command: %s" % command
        sys.exit(1)
