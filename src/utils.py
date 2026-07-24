import os
from pathlib import Path
import json
from shapely.geometry import Polygon
from poly import PolySemantic

from datetime import datetime, timedelta
 

def load_env_vars(env_path=None):
    """
    Carga variables de entorno desde un archivo .env (formato KEY=VALUE) sin dependencias externas.
    Si env_path es None, busca en el cwd.
    """
    import os
    if env_path is None:
        env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value
 
def category_parse(number):
    import deduplicator as dd
    number = int(number)
    #classes = ["person", "car", "truck", "bus", "motor", "bike", "rider", "traffic light", "traffic sign", "train"]
    return {0: dd.Categories.C_person,
            1: dd.Categories.C_car,
            3: dd.Categories.C_bus,
            4: dd.Categories.C_motorbike,
            5: dd.Categories.C_bycicle}.get(number, None)


def pixel2GPS(x, y):
    import pymap3d as pm
    lat, lon, _ = pm.enu2geodetic(x, y, 0, 44.655540, 10.934315, 0)
    return lat, lon

def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
    
def find_main_file():
    print(globals())
    print('----------------')
    Path(__file__).resolve()
    if ("__file__") not in globals():
        __file__ = "/root/smartcity-compss/main.py"
    return (os.path.dirname(__file__))


def classNames(classInt):
    return {0: 'Person',
            1: 'Car',
            3: 'Bus',
            4: 'Motorbike',
            5: 'Bike'}.get(classInt, None)

def find_files_by_strings(folder_path, string1, string2):
    matching_files = []
    # Iterate through each file in the folder
    for filename in os.listdir(folder_path):
        # Check if both strings are present in the file name
        if string1 in filename and string2 in filename:
            print(f'Found active pmat {filename}')
            # If both strings are present, add the file to the list
            matching_files.append(os.path.join(folder_path, filename))
        else:
            print(f'Not found {string1} and {string2} in {filename}')
    return matching_files



def getPolysRoi(json_path):
    with open(json_path) as f:
        data = json.load(f)

    poly_list = []
    region_id_counter = 1

    for img_id, img_data in data["_via_img_metadata"].items():
        for region in img_data["regions"]:
            shape = region["shape_attributes"]
            site_type = region["region_attributes"].get("type", None)

            if shape["name"] == "polygon":
                x = shape["all_points_x"]
                y = shape["all_points_y"]
                polygon = Polygon(zip(x, y))

                obj = PolySemantic(
                    polygon,              # geometría
                    region_id_counter,    # ID incremental global
                    site_type             # tipo (bikeLane, road, etc.)
                )
                poly_list.append(obj)
                region_id_counter += 1  # incrementa el contador

    return poly_list

def save_results(results, exp_dir, CAM_ID):
    
    # now_minus_1m = datetime.now() - timedelta(minutes=1)
    folder_path = os.path.join(exp_dir, 
                               datetime.now().strftime("%Y%m%d"), 
                               datetime.now().strftime("%H%M"),
                               CAM_ID)
    
    os.makedirs(folder_path, exist_ok=True)
    res_file = os.path.join(folder_path, "tracklets.txt")

    print(f" - Saving to {res_file}")
    with open(res_file, 'w') as f:
        f.writelines(results)
    print(f" - Saved results to {res_file}")
    return folder_path
    
    
def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # no hace un send real, solo establece conexión para conocer la IP local
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1" 