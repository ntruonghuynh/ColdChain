$ErrorActionPreference = "Stop"
$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
$lines = [System.Collections.Generic.List[string]](Get-Content -LiteralPath $envPath)
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
if ($generated) { Write-Host "Generated missing local-only M5 secrets in .env." }
