import os
import sys
from pathlib import Path

 
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


