import align from "../../../backend/app/geometry/align.py?raw";
import clientDispatch from "../../../backend/app/client_dispatch.py?raw";
import conventional from "../../../backend/app/geometry/conventional.py?raw";
import exportPy from "../../../backend/app/geometry/export.py?raw";
import importVector from "../../../backend/app/geometry/import_vector.py?raw";
import models from "../../../backend/app/models.py?raw";
import pack from "../../../backend/app/geometry/pack.py?raw";
import panel from "../../../backend/app/geometry/panel.py?raw";
import regions from "../../../backend/app/geometry/regions.py?raw";
import score from "../../../backend/app/geometry/score.py?raw";
import serde from "../../../backend/app/serde.py?raw";
import validate from "../../../backend/app/geometry/validate.py?raw";

/** Python geometry modules loaded into the browser engine. */
export const PY_SOURCES: Record<string, string> = {
  "app/__init__.py": "",
  "app/models.py": models,
  "app/serde.py": serde,
  "app/client_dispatch.py": clientDispatch,
  "app/geometry/__init__.py": "",
  "app/geometry/align.py": align,
  "app/geometry/conventional.py": conventional,
  "app/geometry/export.py": exportPy,
  "app/geometry/import_vector.py": importVector,
  "app/geometry/pack.py": pack,
  "app/geometry/panel.py": panel,
  "app/geometry/regions.py": regions,
  "app/geometry/score.py": score,
  "app/geometry/validate.py": validate,
};
