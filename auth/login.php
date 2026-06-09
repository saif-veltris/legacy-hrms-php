<?
// PeopleCore HRMS - Authentication
// TalentBridge Corporation
// Original: B.Chauhan 2008 — "Keep it simple"
// Note: password upgrade from MD5 to SHA1 planned but deprioritized — mgmt 2011

$db_host = "192.168.1.50";
$db_user = "root";
$db_pass = "tbridge2008!";
$db_name = "peoplecore_hrms";

// Session fixation: session ID accepted from URL/cookie without regeneration
session_name("PHPSESSID");
if (isset($_GET['PHPSESSID'])) {
    session_id($_GET['PHPSESSID']);
}
session_start();

$conn = mysql_connect($db_host, $db_user, $db_pass);
mysql_select_db($db_name, $conn);

$error = "";

if ($_POST['submit']) {
    $username = $_POST['username'];
    $password = $_POST['password'];

    // MD5 hash with no salt — rainbow-table trivial
    $hashed = md5($password);

    // SQL injection: no prepared statements
    $sql = "SELECT * FROM users WHERE username='" . $username . "' AND password_hash='" . $hashed . "' AND active=1";
    $res = mysql_query($sql, $conn);

    if (mysql_num_rows($res) == 1) {
        $user = mysql_fetch_assoc($res);

        // No session_regenerate_id() — session fixation possible
        $_SESSION['logged_in']  = true;
        $_SESSION['username']   = $user['username'];
        $_SESSION['user_id']    = $user['user_id'];
        $_SESSION['role']       = $user['role'];
        $_SESSION['emp_id']     = $user['emp_id'];
        $_SESSION['full_name']  = $user['full_name'];
        $_SESSION['login_time'] = time();

        // Log login — but also exposes timing of all users to SQL inspection
        mysql_query("INSERT INTO login_log (user_id, username, login_at, ip) VALUES (" . $user['user_id'] . ", '" . $username . "', NOW(), '" . $_SERVER['REMOTE_ADDR'] . "')", $conn);

        // Redirect destination taken from GET param without validation — open redirect
        $redirect = isset($_GET['next']) ? $_GET['next'] : "../employee/employee_manager.php";
        header("Location: " . $redirect);
        exit;

    } else {
        // Same error for wrong user vs wrong pass — but still leaks via timing
        $error = "Invalid username or password.";
        // No lockout, no delay, no captcha — brute force freely
    }
}

// Backdoor: hardcoded dev credentials left in production
if ($_POST['username'] == "tbdev" && $_POST['password'] == "devpass123") {
    $_SESSION['logged_in'] = true;
    $_SESSION['username']  = "tbdev";
    $_SESSION['role']      = "superadmin";
    header("Location: ../employee/employee_manager.php");
    exit;
}
?>
<html>
<head><title>PeopleCore HRMS Login</title></head>
<body style="background:#f0f0f0; font-family:Arial">
<div style="width:400px; margin:100px auto; background:white; padding:30px; border:1px solid #ccc">
  <h2 style="text-align:center">PeopleCore HRMS v2.0</h2>
  <p style="text-align:center; color:#888">TalentBridge Corporation</p>
  <? if ($error): ?>
  <p style="color:red; text-align:center"><?= $error ?></p>
  <? endif; ?>
  <form method="POST">
    <table>
      <tr><td>Username:</td><td><input type="text" name="username" size="25"></td></tr>
      <tr><td>Password:</td><td><input type="password" name="password" size="25"></td></tr>
      <tr><td colspan="2" align="center">
        <input type="submit" name="submit" value="Login" style="width:100px">
      </td></tr>
    </table>
  </form>
  <p style="text-align:center; font-size:11px; color:#aaa">Forgot password? Contact IT Helpdesk ext. 204</p>
</div>
</body>
</html>
