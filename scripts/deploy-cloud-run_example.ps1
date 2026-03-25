param(
    [string]$Region = "europe-west3",
    [string]$ServiceName = "adtracker",
    [string]$ImageName = "adtracker"
)

$ErrorActionPreference = "Stop"

$ProjectId = "<your-project-id>" # TODO: Update this to your project ID
$RuntimeServiceAccount = "adtracker-run-sa@$ProjectId.iam.gserviceaccount.com"
$Image = "gcr.io/$ProjectId/$ImageName"
$Secrets = "APP_PASSWORD=APP_PASSWORD:latest,GOOGLE_SHEET_ID=GOOGLE_SHEET_ID:latest,META_ACCESS_TOKEN=META_ACCESS_TOKEN:latest,META_APP_ID=META_APP_ID:latest,META_APP_SECRET=META_APP_SECRET:latest,TIKTOK_ACCESS_TOKEN=TIKTOK_ACCESS_TOKEN:latest,TIKTOK_CLIENT_KEY=TIKTOK_CLIENT_KEY:latest,TIKTOK_CLIENT_SECRET=TIKTOK_CLIENT_SECRET:latest"

Write-Host "Setting active project to $ProjectId..." -ForegroundColor Cyan
gcloud config set project $ProjectId | Out-Host

Write-Host "Configuring Docker auth for gcr.io..." -ForegroundColor Cyan
gcloud auth configure-docker gcr.io --quiet | Out-Host

Write-Host "Building image $Image..." -ForegroundColor Cyan
gcloud builds submit --tag $Image | Out-Host

$deployArgs = @(
    "run", "deploy", $ServiceName,
    "--image", $Image,
    "--region", $Region,
    "--platform", "managed",
    "--service-account", $RuntimeServiceAccount,
    "--set-secrets", $Secrets,
    "--allow-unauthenticated"
)

Write-Host "Deploying Cloud Run service $ServiceName..." -ForegroundColor Cyan
gcloud @deployArgs | Out-Host

Write-Host "Fetching deployed URL..." -ForegroundColor Cyan
$serviceUrl = gcloud run services describe $ServiceName --region $Region --format="value(status.url)"

Write-Host "Deployment complete." -ForegroundColor Green
Write-Host "Service URL: $serviceUrl" -ForegroundColor Green
Write-Host "This service is public. APP_PASSWORD should remain configured to protect the app." -ForegroundColor Yellow
