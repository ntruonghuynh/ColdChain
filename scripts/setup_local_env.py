"""Create missing local-only M5 secrets and replace a weak JWT placeholder, without printing values."""

from pathlib import Path
import os
import secrets

ENV = Path(__file__).resolve().parents[1] / ".env"
SECRET_KEYS = (
    "POSTGRES_PASSWORD", "JWT_SECRET", "AUDIT_SIGNING_KEY", "SHIPPER_DEMO_PASSWORD", "CARRIER_DEMO_PASSWORD",
    "QUALITY_DEMO_PASSWORD", "WAREHOUSE_DEMO_PASSWORD", "ADMIN_DEMO_PASSWORD",
)


def ensure_secrets(env_path: Path = ENV) -> list[str]:
    lines = env_path.read_text(encoding="utf-8").splitlines()
    by_key = {line.split("=", 1)[0]: i for i, line in enumerate(lines) if "=" in line and not line.startswith("#")}
    generated = []
    for key in SECRET_KEYS:
        index = by_key.get(key)
        if index is None:
            lines.append(f"{key}={secrets.token_hex(32)}")
            generated.append(key)
            continue
        value = lines[index].split("=", 1)[1].strip()
        # The compose template historically used this non-empty JWT placeholder,
        # so treating only blank values as missing left login permanently disabled.
        # Replace only the JWT placeholder/weak value; preserve every valid secret,
        # especially AUDIT_SIGNING_KEY, so signed audit history remains verifiable.
        invalid_jwt = key == "JWT_SECRET" and (
            value == "change-me-local-only" or len(value) < 32
        )
        if not value or invalid_jwt:
            size = 32 if key in {"POSTGRES_PASSWORD", "JWT_SECRET", "AUDIT_SIGNING_KEY"} else 24
            lines[index] = f"{key}={secrets.token_hex(size)}"
            generated.append(key)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
    return generated


def main() -> None:
    generated = ensure_secrets()
    if generated:
        print("Generated missing local-only M5 secrets in .env (values redacted).")


if __name__ == "__main__":
    main()
