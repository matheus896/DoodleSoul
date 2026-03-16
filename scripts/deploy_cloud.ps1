param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId = "project-fe538b70-dcfd-4228-ac7"
)

Write-Host "🚀 Starting Automated Deploy via Google Cloud Build..." -ForegroundColor Cyan
Write-Host "📍 Active Project: $ProjectId"

# gcloud will use the credentials of the account currently logged in the terminal
gcloud builds submit --config cloudbuild.yaml . --project $ProjectId

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Deploy completed successfully! New revision available on Cloud Run." -ForegroundColor Green
} else {
    Write-Host "`n❌ Error during deploy. Please check the logs in the Google Cloud Console." -ForegroundColor Red
}
