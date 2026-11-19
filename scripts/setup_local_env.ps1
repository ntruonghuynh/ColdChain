$ErrorActionPreference = "Stop"
$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
$lines = [System.Collections.Generic.List[string]](Get-Content -LiteralPath $envPath)
$projectIndex = -1
for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].StartsWith("COMPOSE_PROJECT_NAME=")) { $projectIndex = $i; break } }
$templateProject = "coldchain-demo-template"
$project = if ($projectIndex -ge 0) { $lines[$projectIndex].Substring("COMPOSE_PROJECT_NAME=".Length).Trim() } else { "" }
if ([string]::IsNullOrWhiteSpace($project) -or $project -eq $templateProject) {
  $namespaceBytes = New-Object byte[] 6
  $namespaceRng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $namespaceRng.GetBytes($namespaceBytes)
  $namespaceSuffix = [BitConverter]::ToString($namespaceBytes).Replace("-", "").ToLowerInvariant()
  $project = "coldchain-demo-$namespaceSuffix"
  if ($projectIndex -ge 0) { $lines[$projectIndex] = "COMPOSE_PROJECT_NAME=$project" } else { $lines.Add("COMPOSE_PROJECT_NAME=$project") }
  $namespaceRng.Dispose()
} else {
  $namespaceSuffix = ($project -replace "[^a-zA-Z0-9_.-]+", "-").Trim(".-")
  if ($namespaceSuffix.Length -gt 48) { $namespaceSuffix = $namespaceSuffix.Substring(0, 48) }
}
$imageTemplates = [ordered]@{
  BACKEND_IMAGE = "coldchain-backend:demo-template"
  BACKEND_TEST_IMAGE = "coldchain-backend:test-demo-template"
  CHAIN_IMAGE = "coldchain-chain:demo-template"
  FRONTEND_IMAGE = "coldchain-frontend:demo-template"
}
foreach ($key in $imageTemplates.Keys) {
  $index = -1
  for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].StartsWith("$key=")) { $index = $i; break } }
  $template = $imageTemplates[$key]
  $current = if ($index -ge 0) { $lines[$index].Substring($key.Length + 1) } else { "" }
  if ($index -lt 0 -or $current -eq $template) {
    $image = $template.Substring(0, $template.LastIndexOf(":"))
    $tag = $template.Substring($template.LastIndexOf(":") + 1).Replace("demo-template", $namespaceSuffix)
    if ($index -lt 0) { $lines.Add("$key=$image`:$tag") } else { $lines[$index] = "$key=$image`:$tag" }
  }
}
$keys = @("POSTGRES_PASSWORD", "JWT_SECRET", "AUDIT_SIGNING_KEY", "SHIPPER_DEMO_PASSWORD", "CARRIER_DEMO_PASSWORD", "QUALITY_DEMO_PASSWORD", "WAREHOUSE_DEMO_PASSWORD", "ADMIN_DEMO_PASSWORD")
$generated = $false
foreach ($key in $keys) {
  $index = -1
  for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].StartsWith("$key=")) { $index = $i; break } }
  $size = if ($key -in @("JWT_SECRET", "AUDIT_SIGNING_KEY")) { 32 } else { 24 }
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $bytes = New-Object byte[] $size
  $rng.GetBytes($bytes)
  $hex = [BitConverter]::ToString($bytes).Replace("-", "")
  $rng.Dispose()
  if ($index -lt 0) {
    $lines.Add("$key=$hex")
    $generated = $true
  } else {
    $value = $lines[$index].Substring($key.Length + 1)
    $invalidJwt = $key -eq "JWT_SECRET" -and ($value -eq "change-me-local-only" -or $value.Length -lt 32)
    if ([string]::IsNullOrWhiteSpace($value) -or $invalidJwt) {
      $lines[$index] = "$key=$hex"
      $generated = $true
    }
  }
}
[IO.File]::WriteAllLines($envPath, $lines)
if ($generated) { Write-Host "Generated missing local-only secrets in .env." }
Write-Host "Configured unique local Compose project and image tags in .env."
