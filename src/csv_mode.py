import csv
import itertools
import os
import shutil
import subprocess
import sys

from src import utils


def expand_env_path(path_value):
    if not path_value:
        return path_value
    return os.path.expanduser(os.path.expandvars(path_value))


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_data_path(data_path):
    expanded_path = expand_env_path(data_path)
    if os.path.isabs(expanded_path):
        return expanded_path
    return os.path.join(_project_root(), "data", expanded_path)


def _resolve_local_data_path(data_path):
    expanded_path = expand_env_path(data_path)
    if os.path.isabs(expanded_path):
        return expanded_path
    return os.path.join(_project_root(), expanded_path)


def _derive_area_root(data_path, city, area):
    normalized = os.path.normpath(data_path)
    path_parts = normalized.split(os.sep)

    if "logs" in path_parts:
        logs_index = path_parts.index("logs")
        return os.sep.join(path_parts[:logs_index]) or os.sep

    return os.path.join("data", city, area)


def _resolve_area_asset_path(area_root, subdir, env_path_key, env_name_key, default_name):
    explicit_path = os.environ.get(env_path_key)
    if explicit_path:
        return expand_env_path(explicit_path)

    file_name = os.environ.get(env_name_key, default_name)
    file_name = expand_env_path(file_name)
    if os.path.isabs(file_name):
        return file_name

    return os.path.join(area_root, subdir, file_name)


def _ls_f_names(dir_path):
    result = subprocess.run(
        ["ls", "-f", dir_path],
        check=True,
        capture_output=True,
        text=True,
    )
    return [name for name in result.stdout.splitlines() if name not in {".", ".."}]


def _env_bool(*keys, default=False):
    truthy = {"1", "true", "t", "yes", "y", "on"}
    falsy = {"0", "false", "f", "no", "n", "off"}

    for key in keys:
        value = os.environ.get(key)
        if value is None:
            continue
        normalized = str(value).strip().lower()
        if normalized in truthy:
            return True
        if normalized in falsy:
            return False

    return default


def _sync_path(src_path, dst_path, is_dir):
    if is_dir and os.path.isdir(dst_path):
        print(f"[csv_mode] Skip (exists): {dst_path}")
        return
    if not is_dir and os.path.isfile(dst_path):
        print(f"[csv_mode] Skip (exists): {dst_path}")
        return

    print(f"[csv_mode] Sync {'dir' if is_dir else 'file'}: {src_path} -> {dst_path}")
    os.makedirs(dst_path if is_dir else os.path.dirname(dst_path), exist_ok=True)

    if shutil.which("rsync"):
        if is_dir:
            cmd = ["rsync", "-a", "--delete", f"{src_path}/", f"{dst_path}/"]
        else:
            cmd = ["rsync", "-a", src_path, dst_path]
        subprocess.run(cmd, check=True)
        return

    if is_dir:
        shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
    else:
        shutil.copy2(src_path, dst_path)


def load_csv_mode_config(default_fps):
    utils.load_env_vars()

    cam_id = os.environ.get("CAM_ID", "0003")
    city = os.environ.get("CITY", "city")
    area = os.environ.get("AREA", "area")
    source_data_path = _resolve_data_path(os.environ.get("DATA_PATH", "data/city/area"))
    local_data_path = _resolve_local_data_path(
        os.environ.get("LOCAL_DATA_PATH", f"data_cache/{city}/{area}/logs/airurban/{cam_id}/")
    )
    source_area_root = _derive_area_root(source_data_path, city, area)
    local_area_root = _derive_area_root(local_data_path, city, area)

    config = {
        "CAM_ID": cam_id,
        "MULTICAST": int(os.environ.get("MULTICAST", 0)),
        "NEVEREND": False,
        "NUM_ITERS": int(os.environ.get("FRAMES_TO_PROCESS", 1000)),
        "CAM_HEIGHT": int(os.environ.get("CAM_HEIGHT", 1080)),
        "CAM_WIDTH": int(os.environ.get("CAM_WIDTH", 1920)),
        "CSV_REALTIME": _env_bool("csv_realtime", "CSV_REALTIME", default=False),
        "DATA_PATH": local_data_path,
        "SOURCE_DATA_PATH": source_data_path,
        "CITY": city,
        "AREA": area,
        "ROI_PATH": _resolve_area_asset_path(
            local_area_root, "roi", "ROI_PATH", "ROI", f"{area.lower()}_{cam_id}.json"
        ),
        "PMAT_PATH": _resolve_area_asset_path(
            local_area_root, "pmat", "PMAT_PATH", "PMAT", f"{cam_id}_ACTIVE.txt"
        ),
        "SOURCE_ROI_PATH": _resolve_area_asset_path(
            source_area_root, "roi", "ROI_PATH", "ROI", f"{area.lower()}_{cam_id}.json"
        ),
        "SOURCE_PMAT_PATH": _resolve_area_asset_path(
            source_area_root, "pmat", "PMAT_PATH", "PMAT", f"{cam_id}_ACTIVE.txt"
        ),
        "FPS": int(os.environ.get("FPS", default_fps)),
    }
    print(f"[csv_mode] Source data path: {config['SOURCE_DATA_PATH']}")
    print(f"[csv_mode] Local data path: {config['DATA_PATH']}")
    print(f"[csv_mode] CSV_DAY: {os.environ.get('CSV_DAY', '').strip() or '(none)'}")
    print(f"[csv_mode] CSV_HOURS: {os.environ.get('CSV_HOURS', '').strip() or '(interactive/all)'}")
    return config


def resolve_csv_scan_path(data_path, require_exists=True):
    csv_day = os.environ.get("CSV_DAY", "").strip()
    if not csv_day:
        return data_path

    csv_day = expand_env_path(csv_day)
    if os.path.isabs(csv_day):
        scan_path = csv_day
    else:
        scan_path = os.path.join(data_path, csv_day)

    if require_exists and not os.path.isdir(scan_path):
        raise FileNotFoundError(
            f"No existe la carpeta del dia '{csv_day}' en {scan_path}"
        )

    return scan_path


def select_csv_hours(source_data_path):
    print(f"[csv_mode] Resolving source scan path from: {source_data_path}")
    source_scan_path = resolve_csv_scan_path(source_data_path)
    print(f"[csv_mode] Source scan path: {source_scan_path}")
    hour_dirs = _find_hour_dirs(source_scan_path)
    print(f"[csv_mode] Hours found: {hour_dirs}")
    selected_hours = _prompt_csv_hours(hour_dirs)
    print(f"[csv_mode] Selected hours: {selected_hours}")
    return selected_hours, source_scan_path


def _cache_complete(csv_config, selected_hours, local_day_path) -> bool:
    """Return True if all required files already exist in the local cache."""
    cam_id = csv_config["CAM_ID"]
    for hour_name in selected_hours:
        tracklets = os.path.join(local_day_path, hour_name, cam_id, "tracklets.txt")
        if not os.path.isfile(tracklets):
            return False
    utm_path = os.path.join(os.path.dirname(csv_config["PMAT_PATH"]), "origin_coordinates_utm.txt")
    return (
        os.path.isfile(csv_config["PMAT_PATH"])
        and os.path.isfile(csv_config["ROI_PATH"])
        and os.path.isfile(utm_path)
    )


def sync_csv_inputs(csv_config, selected_hours):
    local_day_path = resolve_csv_scan_path(csv_config["DATA_PATH"], require_exists=False)

    if _cache_complete(csv_config, selected_hours, local_day_path):
        print("[csv_mode] All data already in cache — skipping sync")
        return

    source_day_path = resolve_csv_scan_path(csv_config["SOURCE_DATA_PATH"])
    print(f"[csv_mode] Syncing selected hours from {source_day_path} to {local_day_path}")
    os.makedirs(local_day_path, exist_ok=True)
    for hour_name in selected_hours:
        _sync_path(
            os.path.join(source_day_path, hour_name),
            os.path.join(local_day_path, hour_name),
            is_dir=True,
        )

    print("[csv_mode] Syncing PMAT, UTM origin and ROI")
    _sync_path(csv_config["SOURCE_PMAT_PATH"], csv_config["PMAT_PATH"], is_dir=False)
    _sync_path(csv_config["SOURCE_ROI_PATH"], csv_config["ROI_PATH"], is_dir=False)
    src_utm = os.path.join(os.path.dirname(csv_config["SOURCE_PMAT_PATH"]), "origin_coordinates_utm.txt")
    dst_utm = os.path.join(os.path.dirname(csv_config["PMAT_PATH"]), "origin_coordinates_utm.txt")
    _sync_path(src_utm, dst_utm, is_dir=False)
    print("[csv_mode] Sync complete")


def prepare_csv_groups(data_path, selected_hours):
    cam_id = os.environ.get("CAM_ID", "0003")
    scan_path = resolve_csv_scan_path(data_path, require_exists=False)
    selected_tracklets_paths = [
        os.path.join(scan_path, hour_name, cam_id, "tracklets.txt")
        for hour_name in selected_hours
    ]

    print(f"[csv_mode] Local scan path: {scan_path}")
    print(f"[csv_mode] Tracklets files: {selected_tracklets_paths}")
    rows = _iter_selected_csv_rows(selected_tracklets_paths)
    groups = itertools.groupby(rows, key=lambda row: row[1])
    return selected_hours, selected_tracklets_paths, groups, scan_path


def _find_hour_dirs(data_path):
    hour_dirs = []

    if not os.path.isdir(data_path):
        raise FileNotFoundError(f"DATA_PATH no existe o no es un directorio: {data_path}")

    print(f"[csv_mode] Listing hour directories in {data_path}")
    for name in _ls_f_names(data_path):
        entry_path = os.path.join(data_path, name)
        if not os.path.isdir(entry_path):
            continue

        hour_dirs.append(name)

    if not hour_dirs:
        raise FileNotFoundError(f"No se han encontrado carpetas-hora dentro de {data_path}")

    return hour_dirs


def _parse_hour_selection(selection_text, available_hours):
    normalized = (selection_text or "").strip()
    if not normalized or normalized.lower() in {"all", "todas", "todo"}:
        return list(available_hours)

    selected_hours = []
    seen = set()

    for raw_token in normalized.split(","):
        token = raw_token.strip()
        if not token:
            continue

        if "-" in token:
            start_hour, end_hour = [part.strip() for part in token.split("-", 1)]
            if start_hour not in available_hours or end_hour not in available_hours:
                raise ValueError(f"Rango invalido '{token}'. Usa horas exactas de la lista mostrada.")

            start_idx = available_hours.index(start_hour)
            end_idx = available_hours.index(end_hour)
            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx

            for hour in available_hours[start_idx:end_idx + 1]:
                if hour not in seen:
                    selected_hours.append(hour)
                    seen.add(hour)
            continue

        if token not in available_hours:
            raise ValueError(f"Hora invalida '{token}'. Usa horas exactas de la lista mostrada.")

        if token not in seen:
            selected_hours.append(token)
            seen.add(token)

    if not selected_hours:
        raise ValueError("No se ha seleccionado ninguna hora valida.")

    return selected_hours


def _prompt_csv_hours(available_hours):
    non_interactive_selection = os.environ.get("CSV_HOURS", "").strip()
    if non_interactive_selection:
        return _parse_hour_selection(non_interactive_selection, available_hours)

    if not sys.stdin.isatty():
        return available_hours

    while True:
        selection = input("Horas a ejecutar [Enter = todas]: ")
        try:
            return _parse_hour_selection(selection, available_hours)
        except ValueError as exc:
            print(f"Seleccion no valida: {exc}")


def _iter_selected_csv_rows(csv_paths):
    for csv_path in csv_paths:
        print(f"[csv_mode] Opening tracklets file: {csv_path}")
        with open(csv_path, "r", buffering=1 << 20) as csv_file:
            for row in csv.reader(csv_file):
                if not row or row[0].startswith("#"):
                    continue

                try:
                    int(row[1])
                    float(row[2])
                    float(row[5])
                    float(row[6])
                    float(row[7])
                    float(row[8])
                    float(row[9])
                    int(float(row[10]))
                except (IndexError, ValueError):
                    continue

                yield row
