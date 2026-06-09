<?
// PeopleCore HRMS - Employee Manager Module
// TalentBridge Corporation - Internal Use Only
// Last modified: R.Singh 2009-03-14

$db_host = "192.168.1.50";
$db_user = "root";
$db_pass = "tbridge2008!";
$db_name = "peoplecore_hrms";

$conn = mysql_connect($db_host, $db_user, $db_pass);
if (!$conn) die("Connection failed: " . mysql_error());
mysql_select_db($db_name, $conn);

session_start();
if (!$_SESSION['logged_in']) {
    header("Location: ../auth/login.php");
    exit;
}

$action = $_GET['action'];
$msg = "";

// ADD EMPLOYEE
if ($action == "add" && $_POST) {
    $fname     = $_POST['first_name'];
    $lname     = $_POST['last_name'];
    $email     = $_POST['email'];
    $dept      = $_POST['department'];
    $salary    = $_POST['salary'];
    $join_date = $_POST['join_date'];
    $nat_id    = $_POST['national_id'];
    $role      = $_POST['role'];

    $sql = "INSERT INTO employees (first_name, last_name, email, department, salary, join_date, national_id, role, created_by)
            VALUES ('" . $fname . "', '" . $lname . "', '" . $email . "', '" . $dept . "', " . $salary . ", '" . $join_date . "', '" . $nat_id . "', '" . $role . "', '" . $_SESSION['username'] . "')";
    $res = mysql_query($sql, $conn);
    if ($res) {
        $msg = "Employee added successfully.";
    } else {
        $msg = "Error: " . mysql_error();
    }
}

// UPDATE EMPLOYEE
if ($action == "update" && $_POST) {
    $emp_id = $_POST['emp_id'];
    $salary = $_POST['salary'];
    $dept   = $_POST['department'];
    $role   = $_POST['role'];

    $sql = "UPDATE employees SET salary=" . $salary . ", department='" . $dept . "', role='" . $role . "' WHERE emp_id=" . $emp_id;
    mysql_query($sql, $conn);
    $msg = "Employee updated.";
}

// DELETE EMPLOYEE
if ($action == "delete") {
    $emp_id = $_GET['emp_id'];
    $sql = "DELETE FROM employees WHERE emp_id=" . $emp_id;
    mysql_query($sql, $conn);
    $msg = "Employee record deleted.";
}

// FETCH ALL
$employees = array();
$res = mysql_query("SELECT * FROM employees ORDER BY last_name", $conn);
while ($row = mysql_fetch_assoc($res)) {
    $employees[] = $row;
}
?>
<html>
<head><title>Employee Manager - PeopleCore</title></head>
<body>
<h2>Employee Manager</h2>
<? if ($msg) echo "<p style='color:green'>" . $msg . "</p>"; ?>

<table border="1">
<tr><th>ID</th><th>Name</th><th>Email</th><th>Department</th><th>Salary</th><th>Role</th><th>Actions</th></tr>
<? foreach ($employees as $emp): ?>
<tr>
  <td><?= $emp['emp_id'] ?></td>
  <td><?= $emp['first_name'] . " " . $emp['last_name'] ?></td>
  <td><?= $emp['email'] ?></td>
  <td><?= $emp['department'] ?></td>
  <td><?= $emp['salary'] ?></td>
  <td><?= $emp['role'] ?></td>
  <td>
    <a href="?action=edit&emp_id=<?= $emp['emp_id'] ?>">Edit</a> |
    <a href="?action=delete&emp_id=<?= $emp['emp_id'] ?>" onclick="return confirm('Delete?')">Delete</a>
  </td>
</tr>
<? endforeach; ?>
</table>

<h3>Add New Employee</h3>
<form method="POST" action="?action=add">
  First Name: <input type="text" name="first_name"><br>
  Last Name:  <input type="text" name="last_name"><br>
  Email:      <input type="text" name="email"><br>
  National ID:<input type="text" name="national_id"><br>
  Department: <input type="text" name="department"><br>
  Role:       <input type="text" name="role"><br>
  Salary:     <input type="text" name="salary"><br>
  Join Date:  <input type="text" name="join_date"><br>
  <input type="submit" value="Add Employee">
</form>
</body>
</html>
