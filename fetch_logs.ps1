try {
    $runs = Invoke-RestMethod -Uri 'https://api.github.com/repos/afani-arba/noc-billing-pro/actions/runs?per_page=3'
    $runId = $runs.workflow_runs[0].id
    $jobs = Invoke-RestMethod -Uri "https://api.github.com/repos/afani-arba/noc-billing-pro/actions/runs/$runId/jobs"
    $jobId = $jobs.jobs[0].id
    $logUrl = "https://api.github.com/repos/afani-arba/noc-billing-pro/actions/jobs/$jobId/logs"
    Invoke-WebRequest -Uri $logUrl -OutFile 'e:\noc-billing-pro\github_logs.txt'
    Write-Host 'Success'
} catch {
    Write-Host "Error: $_"
}
