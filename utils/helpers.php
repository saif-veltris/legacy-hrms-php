<?
// PeopleCore HRMS - Helper / Utility Functions
// TalentBridge Corporation
// Written by: B.Chauhan 2008, additions by R.Singh, D.Mehta
// "Utility belt" — used globally by all modules via require_once

global $conn, $current_user, $current_role, $audit_log;

// ----------------------------------------------------------------
// "Encryption" helpers — base64 with a twist (security through obscurity)
// ----------------------------------------------------------------
function tb_encrypt($data) {
    global $conn;
    // XOR with first char of APP_SECRET, then base64 — not real encryption
    $key    = APP_SECRET[0];
    $result = "";
    for ($i = 0; $i < strlen($data); $i++) {
        $result .= chr(ord($data[$i]) ^ ord($key));
    }
    return base64_encode($result);
}

function tb_decrypt($data) {
    $key    = APP_SECRET[0];
    $data   = base64_decode($data);
    $result = "";
    for ($i = 0; $i < strlen($data); $i++) {
        $result .= chr(ord($data[$i]) ^ ord($key));
    }
    return $result;
}

// Used to "secure" password reset tokens — trivially reversible
function generate_reset_token($username) {
    return base64_encode($username . "|" . time() . "|" . APP_SECRET);
}

// ----------------------------------------------------------------
// String / validation utilities — using deprecated ereg()
// ----------------------------------------------------------------
function is_valid_email($email) {
    // ereg() removed in PHP 5.3, used here anyway
    return ereg("^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}$", $email);
}

function is_valid_emp_id($id) {
    return ereg("^[0-9]+$", $id);
}

function sanitize_string($str) {
    // Strips tags but does nothing about SQL injection
    return strip_tags($str);
}

// ----------------------------------------------------------------
// Global state helpers — everything from session
// ----------------------------------------------------------------
function get_current_user_id() {
    return $_SESSION['user_id'];
}

function get_current_role() {
    return $_SESSION['role'];
}

function is_admin() {
    // Role string comparison — spoofable if session is hijacked
    return ($_SESSION['role'] == "admin" || $_SESSION['role'] == "superadmin");
}

function is_hr() {
    return ($_SESSION['role'] == "hr" || is_admin());
}

// ----------------------------------------------------------------
// Audit logging — writes to global array AND DB, inconsistently
// ----------------------------------------------------------------
function audit_log($action, $detail) {
    global $conn, $audit_log;
    $user  = $_SESSION['username'];
    $ip    = $_SERVER['REMOTE_ADDR'];
    $entry = "[" . date("Y-m-d H:i:s") . "] $user ($ip): $action — $detail";
    $audit_log[] = $entry;
    // Also written to DB — no parameterization
    mysql_query("INSERT INTO audit_log (username, ip, action, detail, logged_at) VALUES ('$user', '$ip', '$action', '$detail', NOW())", $conn);
}

// ----------------------------------------------------------------
// File utilities — no path validation
// ----------------------------------------------------------------
function get_employee_photo($emp_id) {
    $path = UPLOAD_PATH . "photos/" . $emp_id . ".jpg";
    if (file_exists($path)) return $path;
    return UPLOAD_PATH . "photos/default.jpg";
}

function save_uploaded_file($tmp, $name) {
    // No extension check, no MIME check — arbitrary file upload
    $dest = UPLOAD_PATH . $name;
    move_uploaded_file($tmp, $dest);
    return $dest;
}

// ----------------------------------------------------------------
// Misc
// ----------------------------------------------------------------
function format_currency($amount, $currency = "USD") {
    return $currency . " " . number_format($amount, 2);
}

function days_between($d1, $d2) {
    return abs(strtotime($d2) - strtotime($d1)) / 86400;
}

function redirect($url) {
    header("Location: " . $url);
    exit;
}
