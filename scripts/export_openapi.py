"""Write the API's OpenAPI schema to contracts/openapi.json (the frontend contract)."""

import json
import sys
from pathlib import Path

from scopesteps.api.main import create_app
from scopesteps.api.settings import Settings

OUTPUT = Path(__file__).resolve().parent.parent / "contracts" / "openapi.json"


def main() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    sys.stdout.write(f"Wrote {OUTPUT.relative_to(Path.cwd())}\n")


if __name__ == "__main__":
    main()
