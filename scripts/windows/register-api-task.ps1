# Register a Windows Scheduled Task to run the API at logon (adjust paths).
# Run PowerShell as Administrator:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\windows\register-api-task.ps1

$Repo = "C:\path\to\Personal-Finance-OS"
$Python = "$Repo\.venv\Scripts\python.exe"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m uvicorn finance_api.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "PersonalFinanceAPI" -Action $Action -Trigger $Trigger -Principal $Principal -Force
