param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [Parameter(Mandatory = $true)]
  [string]$ServiceName,

  [Parameter(Mandatory = $false)]
  [string]$Region = "us-central1",

  [Parameter(Mandatory = $false)]
  [string]$SessionId = "",

  [Parameter(Mandatory = $false)]
  [string]$Lookback = "30m"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/4] Resolving Cloud Run service URL and active revision..."
$serviceJson = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format json | ConvertFrom-Json
$serviceUrl = $serviceJson.status.url
$revision = $serviceJson.status.latestReadyRevisionName

if (-not $serviceUrl -or -not $revision) {
  throw "Could not resolve service URL or revision for service '$ServiceName'."
}

Write-Host "Service URL: $serviceUrl"
Write-Host "Revision: $revision"

Write-Host "[2/4] Verifying HTTPS endpoint responds..."
try {
  $response = Invoke-WebRequest -Uri $serviceUrl -Method GET -MaximumRedirection 0 -ErrorAction Stop
  $httpsStatus = [int]$response.StatusCode
} catch {
  if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
    $httpsStatus = [int]$_.Exception.Response.StatusCode
  } else {
    throw
  }
}
Write-Host "HTTPS status: $httpsStatus"

Write-Host "[3/4] Building log filter for canonical Epic 5 audit events..."
$baseFilter = @(
  'resource.type="cloud_run_revision"',
  ('resource.labels.service_name="' + $ServiceName + '"'),
  'jsonPayload.event_type=("session_started" OR "clinical_alert_stored" OR "safety.pivot.triggered" OR "dlp_redaction_applied" OR "dlp_redaction_discarded" OR "session_end" OR "session_end_idempotent")'
) -join " AND "

if ($SessionId) {
  $baseFilter = $baseFilter + ' AND jsonPayload.session_id="' + $SessionId + '"'
}

Write-Host "[4/4] Querying Cloud Logging (lookback: $Lookback)..."
$logsJson = gcloud logging read $baseFilter --project $ProjectId --freshness $Lookback --limit 50 --format json

$outputDir = Join-Path $PSScriptRoot "..\_bmad-output\implementation-artifacts"
$outputDir = (Resolve-Path $outputDir).Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputPath = Join-Path $outputDir ("epic5-evidence-" + $timestamp + ".json")

$evidence = [ordered]@{
  generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  project_id = $ProjectId
  region = $Region
  service_name = $ServiceName
  service_url = $serviceUrl
  latest_ready_revision = $revision
  https_status = $httpsStatus
  wss_base_url = ($serviceUrl -replace '^https://', 'wss://')
  logging_filter = $baseFilter
}

$evidenceJson = $evidence | ConvertTo-Json -Depth 12
$trimmedEvidenceJson = $evidenceJson.TrimEnd()
if ($trimmedEvidenceJson.EndsWith("}")) {
  $trimmedEvidenceJson = $trimmedEvidenceJson.Substring(0, $trimmedEvidenceJson.Length - 1)
}

$evidenceJsonWithLogs = @"
$trimmedEvidenceJson,
  "logs": $logsJson
}
"@
$evidenceJsonWithLogs | Set-Content -Path $outputPath -Encoding UTF8
Write-Host "Evidence file written: $outputPath"
