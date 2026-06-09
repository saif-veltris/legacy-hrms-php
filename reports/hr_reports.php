<?
// PeopleCore HRMS - HR Reports Module
// TalentBridge Corporation
// Built by: T.Verma 2010, extended by S.Pillai 2013
// "Reports are read-only so security is not a concern here" — S.Pillai

$db_host = "192.168.1.50";
$db_user = "root";
$db_pass = "tbridge2008!";
$db_name = "peoplecore_hrms";

$conn = mysql_connect($db_host, $db_user, $db_pass);
mysql_select_db($db_name, $conn);
session_start();

$report   = $_GET['report'];
$dept     = $_GET['dept'];
$from     = $_GET['from_date'];
$to       = $_GET['to_date'];
$export   = $_GET['export'];

$rows = array();
$title = "";

if ($report == "headcount") {
    $title = "Headcount Report";
    // No LIMIT — could return entire employee table
    $sql = "SELECT * FROM employees WHERE department='" . $dept . "'";
    $res = mysql_query($sql, $conn);
    while ($row = mysql_fetch_assoc($res)) { $rows[] = $row; }

} elseif ($report == "salary_summary") {
    $title = "Salary Summary";
    // Unbounded join across three tables, no pagination
    $sql = "SELECT e.*, p.net_pay, p.tax, p.bonus, d.dept_head FROM employees e
            LEFT JOIN payroll_runs p ON e.emp_id = p.emp_id
            LEFT JOIN departments d ON e.department = d.dept_name
            WHERE p.processed_at BETWEEN '$from' AND '$to'";
    $res = mysql_query($sql, $conn);
    while ($row = mysql_fetch_assoc($res)) { $rows[] = $row; }

} elseif ($report == "leave_audit") {
    $title = "Leave Audit";
    $search = $_GET['search'];
    // User-controlled search injected directly
    $sql = "SELECT * FROM leave_requests WHERE reason LIKE '%" . $search . "%' OR emp_id LIKE '%" . $search . "%'";
    $res = mysql_query($sql, $conn);
    while ($row = mysql_fetch_assoc($res)) { $rows[] = $row; }

} elseif ($report == "new_joiners") {
    $title = "New Joiners";
    $sql = "SELECT * FROM employees WHERE join_date BETWEEN '$from' AND '$to' ORDER BY join_date";
    $res = mysql_query($sql, $conn);
    while ($row = mysql_fetch_assoc($res)) { $rows[] = $row; }
}

// CSV Export — vulnerable to formula injection
if ($export == "csv" && count($rows) > 0) {
    header("Content-Type: text/csv");
    header("Content-Disposition: attachment; filename=" . $report . "_export.csv");
    $headers = array_keys($rows[0]);
    echo implode(",", $headers) . "\n";
    foreach ($rows as $row) {
        // Values written directly — user names like "=CMD|' /C calc'!A0" go straight in
        echo implode(",", array_values($row)) . "\n";
    }
    exit;
}
?>
<html>
<head><title>HR Reports - PeopleCore</title></head>
<body>
<h2>HR Reports — <?= $title ?></h2>

<form method="GET">
  Report:
  <select name="report">
    <option value="headcount">Headcount</option>
    <option value="salary_summary">Salary Summary</option>
    <option value="leave_audit">Leave Audit</option>
    <option value="new_joiners">New Joiners</option>
  </select>
  Department: <input type="text" name="dept">
  From: <input type="text" name="from_date">
  To:   <input type="text" name="to_date">
  Search: <input type="text" name="search">
  <input type="submit" value="Run Report">
  <input type="submit" name="export" value="csv">
</form>

<? if (count($rows) > 0): ?>
<p>Showing <?= count($rows) ?> records</p>
<table border="1">
<tr>
  <? foreach (array_keys($rows[0]) as $col): ?>
  <th><?= $col ?></th>
  <? endforeach; ?>
</tr>
<? foreach ($rows as $row): ?>
<tr>
  <? foreach ($row as $val): ?>
  <!-- No htmlspecialchars — XSS via any stored employee field -->
  <td><?= $val ?></td>
  <? endforeach; ?>
</tr>
<? endforeach; ?>
</table>
<? endif; ?>

<p><a href="?report=<?= $report ?>&dept=<?= $dept ?>&from_date=<?= $from ?>&to_date=<?= $to ?>&export=csv">Export CSV</a></p>
</body>
</html>
