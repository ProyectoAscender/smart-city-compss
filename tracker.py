from pycompss.api.parameter import *
from pycompss.api.task import task
from pycompss.api.api import compss_barrier, compss_wait_on
from pycompss.api.constraint import constraint

# from dataclay.api import init, finish
# from dataclay.exceptions.exceptions import DataClayException

from datetime import datetime
from socket import timeout
#from utils import pixel2GPS
import paho.mqtt.client as mqtt
from lib import track
#from lib import deduplicator as dd
import socket
import os
import json
import re 

from os import listdir
from os.path import isfile, join


import pandas as pd
from geopandas import GeoDataFrame
from shapely import geometry
import numpy as np

NUM_ITERS = 1000
NUM_ITERS_POLLUTION = 25
SNAP_PER_FEDERATION = 15
N = 5
NUM_ITERS_FOR_CLEANING = 10000
CD_PROC = 0

pollution_file_name = "pollution.csv"
roi_file_path = "/root/data/florencia/batoni/roi/"
#roi_path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'mydata.json'))

def getRoi(roi_path):
    df = pd.read_csv(roi_path)
    # Extracting types of polygons
    region_attributes_list = []
    for attribute in df.region_attributes.values:
        attribute = attribute.replace('{', '').replace('}', '').split(',')
        this_row = {}
        for a in attribute:
            a = a.replace('"', '')
            a = a.split(':')
            try:
                try:
                    this_row.update({str(a[0]) : int(a[1])})
                except:
                    this_row.update({str(a[0]) : str(a[1])})
            except:
                this_row.update({str(a[0]) : ''})
        region_attributes_list.append(this_row)
    # Extracting polygons points ang creating polygon geometries
    polys = []
    for attribute in df.region_shape_attributes.values:
        js = json.loads(attribute)
        polys.append(geometry.Polygon(list(zip(js["all_points_x"],js["all_points_y"] ))))
    # Inseting both into geoDataframe
    # pd.DataFrame(region_attributes_list).replace(r'^\s*$', np.nan, regex=True)
    gdf = GeoDataFrame(pd.DataFrame(region_attributes_list),geometry=polys)
    #gdf.astype({"trafficLight": pd.Int8Dtype()}, errors='raise') 
    # Using same index as V(GG)IA
    gdf.reset_index(inplace=True)
    gdf = gdf.rename(columns = {'index':'id','type':'class'})
    gdf['id'] = gdf['id'] + 1
    return gdf

@task(returns=3, list_boxes=IN, trackers=IN, cur_index=IN, init_point=IN)
def execute_tracking(list_boxes, trackers, cur_index, init_point):
    a, b, c = track.track2(list_boxes, trackers, cur_index, init_point)
    return a, b, c


@task(returns=7,)
def receive_boxes(socket_ip, dummy):
    import struct
    import time
    import traceback

    socket_port = 5559
    if ":" in socket_ip:
        socket_ip, socket_port = socket_ip.split(":")
        socket_port = int(socket_port)

    message = b""
    cam_id = None   
    timestamp = None
    boxes = None    
    box_coords = None
    init_point = None
    no_read = True
    frame_number = -1

    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    serverSocket.sendto(b"A", (socket_ip, socket_port))

    double_size = unsigned_long_size = 8
    int_size = float_size = 4
    boxes = []

    while no_read:
        try:
            no_read = False
            message, address = serverSocket.recvfrom(16000)

            flag = len(message) > 0
            # This flag serves to know if the video has ended
            cam_id = struct.unpack_from("i", message[1:1 + int_size])[0]
            timestamp = struct.unpack_from("Q", message[1 + int_size:1 + int_size + unsigned_long_size])[0]
            box_coords = []
            lat, lon = struct.unpack_from("dd", message[1 + int_size + unsigned_long_size:1 + int_size + unsigned_long_size
                                                                                        + double_size * 2])
            #   // box_vector: x,y,w,h (resized)
            #     // coords: north,east (convertToMeters (unresized)) 
            #     // bo0xCoords: 4 esquinas coordenadas (convertedToGeo (unresized))
            #     // corrdsGeo: NO se usa
            #     collectBoxInfo(cam->detNN->batchDetected, box_vector, coords, coordsGeo, boxCoords, scale_x, scale_y, *cam);
            #     unsigned int size;
            #     char *data = prepareMessageUDP(box_vector, coords, boxCoords, n_frame, cam->id,
            #                                    cam->adfGeoTransform[3], cam->adfGeoTransform[0], // pasamos pto.ref
            #                                    &size, scale_x, scale_y);
            # print(range(1 + int_size + unsigned_long_size + double_size * 2, len(message),
            #                     double_size * 10 + int_size + 1 + float_size * 4))
            init_point = (lat, lon)
            for offset in range(1 + int_size + unsigned_long_size + double_size * 2, len(message),
                                double_size * 10 + int_size + 1 + float_size * 4):
                north, east, frame_number, obj_class = struct.unpack_from('ddIc', message[
                                                                                offset:offset + double_size * 2 + int_size + 1])
                x, y, w, h = struct.unpack_from('ffff', message[offset + double_size * 2 + int_size + 1:offset + double_size * 2
                                                                                + int_size + 1 + float_size * 4])
                
                boxes.append(track.obj_m(north, east, frame_number, ord(obj_class), int(w), int(h), int(x), int(y), 0.0))

                lat_ur, lon_ur, lat_lr, lon_lr, lat_ll, lon_ll, lat_ul, lon_ul = struct.unpack_from('dddddddd', message[
                                                                                offset + double_size * 2 + int_size + 1 +
                                                                                float_size * 4:])
                                                                                
                box_coords.append((lat_ur, lon_ur, lat_lr, lon_lr, lat_ll, lon_ll, lat_ul, lon_ul))
        except socket.error as e:
            no_read = True
            traceback.print_exc()

    serverSocket.close()
    # box_coords: 4 esquinas coordenadas
    # boxes: track.obj_m -> modules.cpp de tracker_CLASS/bsc 
    return cam_id, timestamp, boxes, dummy, box_coords, init_point, frame_number


@constraint(AppSoftware="xavier")
@task(trackers_list=COLLECTION_IN, cam_ids=COLLECTION_IN, foo_dedu=INOUT, frames=COLLECTION_IN)
def deduplicate(trackers_list, cam_ids, foo_dedu, frames):
    return_message = dd.compute_deduplicator(trackers_list, cam_ids, frames,False)
    return return_message, foo_dedu

@task(returns = 1, kb = IN)
def getResistenzaStatus(kb):
    
    if (kb.traffic_lights[(11.1831603045325, 43.75873372968)].status == 'Red'):
        vehLights = {'G3': False} # RED
    else:
        vehLights = {'G3': True} # GREEN, YELLOW
    
    if (kb.traffic_lights[(11.1828671784974, 43.758755396189)].status == 'Red'):
        pedLights = {'G1': False} # RED
    else:
        pedLights = {'G1': True} # GREEN, YELLOW

    if (kb.traffic_lights[(11.1829760293935, 43.7588197766266)].status == 'Red'):
        pedLights.update({'G2': False})  # RED
    else:
        pedLights.update({'G2': True}) # GREEN, YELLOW

def getBatoniStatus(kb):
    # if (kb.traffic_lights[(11.2207382614911, 43.7742463147471)].status == 'Red'):
    #     pedLights = {'G1': False} # RED
    # else:
    #     pedLights = {'G1': True} # GREEN, YELLOW

    # if (kb.traffic_lights[(11.2206499502015, 43.7738802024861)].status == 'Red'):
    #     vehLights = {'G2': False} # RED
    # else:
    #     vehLights = {'G2': True} # GREEN, YELLOW

    # if (kb.traffic_lights[(11.2207907492102, 43.7742967899821)].status == 'Red'):
    #     vehLights.update({'G3': False}) # RED
    # else:
    #     vehLights.update({'G3': True}) # GREEN, YELLOW

    # if (kb.traffic_lights[(11.220725796009, 43.7740533935107)].status == 'Red'):
    #     vehLights.update({'G4': False}) # RED
    # else:
    #     vehLights.update({'G4': True}) # GREEN, YELLOW

    # if (kb.traffic_lights[(11.2207265880488, 43.773954106717)].status == 'Red'):
    #     pedLights.update({'G5': False}) # RED
    # else:
    #     pedLights.update({'G5': True}) # GREEN, YELLOW

    # if (kb.traffic_lights[(11.220785713538,43.7739671264712)].status == 'Red'):
    #     pedLights.update({'G6': False})  # RED
    # else:
    #     pedLights.update({'G6': True}) # GREEN, YELLOW

    # if (kb.traffic_lights[(11.2209194201504, 43.7740884279256)].status == 'Red'):
    #     pedLights.update({'G7': False})  # RED
    # else:
    #     pedLights.update({'G7': True}) # GREEN, YELLOW
    pedLights = {'G1': False} 
    vehLights = {'G2': True}
    vehLights.update({'G3': True})
    vehLights.update({'G4': True})
    pedLights.update({'G5': False})
    pedLights.update({'G6': False})
    pedLights.update({'G7': False})
    # print({'pedLights': pedLights, 'vehLights': vehLights, 'tramApproach':True})
    return {'pedLights': pedLights, 'vehLights': vehLights, 'tramApproach':True}


def getResistenzaStatus2(current_frame):
    # filename = './' + str(id_cam) + '_' + str(NUM_ITERS) + '_states.in'
    filename = './status.log'

    df = pd.read_csv(filename, names = ['id_cam','frame','pedLightG1','pedLightG2','vehLightG3','tramState'])
    q = df.loc[df.frame == current_frame]
    vehLights = {'G3': q['vehLightG3'].values}     
    pedLights = {'G1': q['pedLightG1'].values, 'G2': q['pedLightG2'].values} # RED
    return {'pedLights': pedLights, 'vehLights': vehLights, 'tramApproach':q['tramState'].values[0]}

@task(returns=2,id_cam=IN, timestamp = IN, info_for_deduplicator=IN,polys=IN, kb=IN, areaState=IN)
def semantic_analysis(id_cam,timestamp, info_for_deduplicator, polys, kb, areaState):
    # Alert list will contains binary alert value for inserting into csv
    # from CityNS.classes import Alert
    alertList = []    
    alertInfo = []
    alarmTime = 10000
    area = 'batoni'
    carQueueLength = 0
    alertQueueFlag = False
    # All polys are passed to all cameras in dictionary. Here we select the correct one
    polys = polys[str(id_cam)]



    # Inspect if every box is in a polygon
    for i, box in enumerate(info_for_deduplicator):
        cl = box[2]
        speed = box[3]
        yaw = box[4]  # info_for_deduplicator[i][4]
        trackId = box[5]
        pixel_x = box[6]  # OR list_boxes[tracker.idx].x  # pixels[tracker.idx][0]
        pixel_y = box[7]  # pixels[tracker.idx][1]
        pixel_w = box[8]  # OR list_boxes[tracker.idx].x  # pixels[tracker.idx][0]
        pixel_h = box[9]
        alertList.append(0)
        alertInfo.append([0, 0, 0, 0, 0])
        alertFlag = False


        if (cl == 0):
            for j, pol in enumerate(polys['pedPolys'].geometry.to_list()):
                inOut = pol.contains(geometry.Point(pixel_x + pixel_w/2, pixel_y + pixel_h))
                if (inOut):                 
                # Pedestrians in tramway when tram is nearby
                    if(polys['pedPolys'].loc[j,'class'] in ['tramway', 'railcross'] and areaState['tramApproach']):#and kb.tram_in_station):
                        alert_category , severity  = 'pedestrianOnRoad' , 'critical'
                        description = 'Pedestrians in tramway when tram is nearby'
                        alertFlag = True
                        alertList[-1] = 1
                        alertInfo[-1] = [1, alert_category, severity, description, str(id_cam) + '_' + str(trackId)]

                # Pedestrians in car path               
                    elif(polys['pedPolys'].loc[j,'class'] == 'road'):
                        alert_category , severity  = 'pedestrianOnRoad' , 'high'
                        description =  'Pedestrians in car path '
                        alertFlag = True
                        alertList[-1] = 2
                        alertInfo[-1] = [2, alert_category, severity, description, str(id_cam) + '_' + str(trackId)]


                # Pedestrians crossing cross
                    elif(polys['pedPolys'].loc[j,'class'] in ['pedCross', 'pedTramCross']):
                        if not areaState['pedLights'][str(polys['pedPolys'].loc[j,'trafficLight'])]: # and traffic light is red
                            alert_category , severity  = 'pedestrianOnRoad' , 'high' 
                            description =  'Pedestrian crossing with red traffic light'
                            alertFlag = True
                            alertList[-1] = 3
                            alertInfo[-1] = [3, alert_category, severity, description, str(id_cam) + '_' + str(trackId)]

                    else:
                        alertFlag = False

                        
        elif (cl in [1,2,3,4]):
            for j, pol in enumerate(polys['vehPolys'].geometry.to_list()):
                inOut = pol.contains(geometry.Point(pixel_x + pixel_w/2, pixel_y + pixel_h))
                if (inOut):
                # Car in railcross with red light when tram is nearby
                    if(polys['vehPolys'].loc[j,'class'] == 'railcross'): #and kb.tram_in_station):
                        if (not areaState['vehLights'][str(polys['vehPolys'].loc[j,'trafficLight'])] and  areaState['tramApproach']): 
                            alert_category , severity  = 'hazardOnRoad' , 'critical'
                            description =  'Vehicle in railcross when tram is nearby and light is red'
                            alertFlag = True
                            alertList[-1] = 4
                            alertInfo[-1] = [4, alert_category, severity, description, str(id_cam) + '_' + str(trackId)]

                    # Cars stopping late
                    elif(polys['vehPolys'].loc[j,'class'] == 'afterStop'):
                         if not areaState['vehLights'][str(polys['vehPolys'].loc[j,'trafficLight'])]: # and traffic light is red
                            alert_category , severity  = 'hazardOnRoad', 'critical'
                            description =  'Vehicle between stop and railway with red light'
                            alertFlag = True
                            alertList[-1] = 6
                            alertInfo[-1] = [6, alert_category, severity, description, str(id_cam) + '_' + str(trackId)]


                        # if areaState['vehLights']['0' + str(polys['vehPolys'].loc[j,'trafficLight'])]:#and kb.tram_in_station):
                        #     alert_category , severity  = 'trafficJam', 'informational'
                        #     description =  'Cars approaching but green light '
                        #     alertFlag = True
                        #     data = carQueueLength
                    else:
                        alertFlag = False

                    # Cars approach
                    if(polys['vehPolys'].loc[j,'class'] == 'queue'):
                        carQueueLength += 1
                        # Cars approach towards railway but red light   
                        if (carQueueLength > 2):        
                            alert_category , severity  = 'trafficJam', 'informational'
                            description =  'Vehicle queue of length ' + str(carQueueLength)
                            alertQueueFlag = True
                            data = carQueueLength
                            alertList[-1] = 5
                            alertInfo[-1] = [5, alert_category, severity, description, str(id_cam) + '_' + str(trackId)]

        # Any alertFlag send Alert.
        if (alertFlag):
            print(f'**ALERT: cam id:{id_cam}'\
                  f' -- {area} {severity} {description}'\
                  f' -- {info_for_deduplicator[i][0]}, {info_for_deduplicator[i][1]} | timeLapse = {alarmTime}')                          
            # alert = Alert(  id = str(id_cam) + '_' +  str(trackId), 
            #                 source = id_cam,
            #                 alert_category = alert_category, 
            #                 severity= severity, 
            #                 longitude = info_for_deduplicator[i][1],
            #                 latitude = info_for_deduplicator[i][0],
            #                 area = area, 
            #                 description = description,
            #                 timestamp = datetime.utcfromtimestamp(timestamp / 1000),
            #                 valid_from = datetime.utcfromtimestamp(timestamp / 1000),
            #                 valid_to = datetime.utcfromtimestamp((timestamp + alarmTime) / 1000))
            # alert.make_persistent()
            # alert.send_to_mqtt()
            # alert.send_to_kafka("dataclay", "batoni")     
    # AlertQueueFlag only triggers Alarm  when all the boxes has been computed
    if (alertQueueFlag):
            print(f'**ALERT: cam id: trafficJam_ {str(data)}'\
                  f' -- {area} {severity} {description}'\
                  f' -- 11.1831603045325, 43.75873372968 | timeLapse = {alarmTime}')                          
            # alert = Alert(  id = 'trafficJam_' + str(data) , 
            #                 source = id_cam,
            #                 alert_category = alert_category, 
            #                 severity= severity, 
            #                 longitude = 11.1831603045325, #  posicion semaforo vehiculos
            #                 latitude = 43.75873372968,
            #                 area = area, 
            #                 description = description,
            #                 #data = data,
            #                 timestamp = datetime.utcfromtimestamp(timestamp / 1000),
            #                 valid_from = datetime.utcfromtimestamp(timestamp / 1000),
            #                 valid_to = datetime.utcfromtimestamp((timestamp + alarmTime) / 1000))
            # alert.make_persistent()
            # alert.send_to_mqtt() 
            # alert.send_to_kafka("dataclay", "batoni")  


    return alertList,alertInfo




# info_for_deduplicator: lat, lon, t.cl, velocity, yaw, t.id, pixel_x, pixel_y, pixel_w, pixel_h
# output visuzlizer: 'cam_id frame timestamp category lat lon geohash speed yaw obj_id x y w h frame_tp timestamp_last_tp TPlat TPlon TPts'.split()

def writef_deduplicated(info_deduplicated, iteration):
    import pygeohash as pgh
    import os

    filename = "20936-20937.in"
    if not os.path.exists(filename):
        f = open(filename, "w+")
        f.close()
    ts = info_deduplicated[0]
    info = info_deduplicated[1]
    frame = info[0][11]
    with open(filename, "a+") as f:
        # for i, tracker in enumerate([t for t in trackers if t.traj[-1].frame == iteration]):
        for i, box in enumerate(info):
            id_cam = info[i][0]
            lat = info[i][5]  # round(info_for_deduplicator[i][0], 14)
            lon = info[i][6]  # round(info_for_deduplicator[i][1], 14)
            geohash = pgh.encode(lat, lon, precision=7)
            cl = info[i][2]
            speed = info[i][3]
            yaw = info[i][4]  # info_for_deduplicator[i][4]
            trackId = info[i][1]
            pixel_x = info[i][7]  # OR list_boxes[tracker.idx].x  # pixels[tracker.idx][0]
            pixel_y = info[i][8]  # pixels[tracker.idx][1]
            pixel_w = info[i][9]  # OR list_boxes[tracker.idx].x  # pixels[tracker.idx][0]
            pixel_h = info[i][10]
            f.write(f"{id_cam} {iteration} {ts} {cl} {lat} {lon} {geohash} {speed} {yaw} {id_cam}_{trackId} {pixel_x} {pixel_y} {pixel_w} {pixel_h}\n")

@task(id_cam=IN, frame = IN, areaState = IN)
def writef_state(id_cam, frame, areaState,initTime):

    import os
    filename = './' + str(id_cam) + '_' + initTime + '_' + str(NUM_ITERS) + '_states.in'
    if not os.path.exists(filename):
        f = open(filename, "w+")
        f.close()
    with open(filename, "a+") as f:
        f.write(f"{id_cam} {frame} {int(areaState['pedLights']['G1'])} {int(areaState['vehLights']['G2'])} {int(areaState['vehLights']['G3'])} {int(areaState['vehLights']['G4'])} {int(areaState['pedLights']['G5'])} {int(areaState['pedLights']['G6'])} {int(areaState['pedLights']['G7'])} {int(areaState['tramApproach'])}\n")


@task(id_cam=IN, frame = IN, areaState = IN)
def writef_alerts(id_cam, frame, alertInfo,initTime):

    import os
    filename = './' + str(id_cam) + '_' + initTime + '_' +  str(NUM_ITERS) + '_alarm.in'
    if not os.path.exists(filename):
        f = open(filename, "w+")
        f.close()
    for i in range(len(alertInfo)):
        with open(filename, "a+") as f:
            # alertInfo -> [alert type, alert_category, severity, description, alertId]
            f.write(f"{frame}; {int(alertInfo[i][0])};{alertInfo[i][1]}; {alertInfo[i][2]};{alertInfo[i][3]};{alertInfo[i][4]}\n")



@task(id_cam=IN, ts = IN, iteration = IN, info_for_deduplicator=IN,alertList = IN)
def writef(id_cam, ts, iteration, info_for_deduplicator, alertList, initTime):
    import pygeohash as pgh
    import os
    filename = './' + str(id_cam) + '_' + initTime + '_' +  str(NUM_ITERS) + '.in'
    if not os.path.exists(filename):
        f = open(filename, "w+")
        f.close()
    with open(filename, "a+") as f:
        # for i, tracker in enumerate([t for t in trackers if t.traj[-1].frame == iteration]):
        for i, box in enumerate(info_for_deduplicator):
            lat = info_for_deduplicator[i][0]  # round(info_for_deduplicator[i][0], 14)
            lon = info_for_deduplicator[i][1]  # round(info_for_deduplicator[i][1], 14)
            geohash = pgh.encode(lat, lon, precision=7)
            cl = info_for_deduplicator[i][2]
            speed = info_for_deduplicator[i][3]
            yaw = info_for_deduplicator[i][4]  # info_for_deduplicator[i][4]
            trackId = info_for_deduplicator[i][5]
            pixel_x = info_for_deduplicator[i][6]  # OR list_boxes[tracker.idx].x  # pixels[tracker.idx][0]
            pixel_y = info_for_deduplicator[i][7]  # pixels[tracker.idx][1]
            pixel_w = info_for_deduplicator[i][8]  # OR list_boxes[tracker.idx].x  # pixels[tracker.idx][0]
            pixel_h = info_for_deduplicator[i][9]
            inOut = alertList[i]
            # if (inOut):
            #     print(f'Alert of writef for {trackId}')
        
            f.write(f"{id_cam} {iteration} {ts} {cl} {lat} {lon} {geohash} {speed} {yaw} {id_cam}_{trackId} {pixel_x} {pixel_y} {pixel_w} {pixel_h} {inOut}\n")

def writef3(id_cam, ts, frame, list_boxes, info_for_deduplicator, box_coords): 
    pred_info2 = np.zeros((len(list_boxes),11)) 
    long = np.zeros(len(list_boxes)) 
    lat = np.zeros(len(list_boxes)) 
    for i, box in enumerate(list_boxes):
        #   new => pred_info [0: fr_num x1 ][1-4: dect_xyxy x4 ][5: score x1 ][6: type_obj x1 ][7: id_obj x1 ][8-9: dect_middle x2 ][10: vel x1 ]
        pred_info2[i,:] = np.concatenate(([frame],
                                    [list_boxes[i].x],
                                    [list_boxes[i].y],
                                    [(list_boxes[i].x + list_boxes[i].w)],
                                    [(list_boxes[i].y + list_boxes[i].h)],
                                    [0.5],
                                    [classReassign(info_for_deduplicator[i][2])],
                                    [i],
                                    [(list_boxes[i].x + list_boxes[i].w / 2) /1280],
                                    [(list_boxes[i].y + list_boxes[i].h / 2) /720 ],
                                    [0]
                                  ), axis=0) # (num_pred, 11)
        lat[i]=info_for_deduplicator[i][0]
        long[i] = info_for_deduplicator[i][1]
        ## Compute ts : ts=fr_num*fps + fr_num ; start by 0 s
    ts = (pred_info2[:, 0]/8).reshape(-1, 1) # (num_pred, 1)
    pred_info_ts = np.concatenate((ts, pred_info2[:, 1:]), axis=1) # (num_pred, 11) # change first column of fr_num for ts 
    ## Converting the detections to a dataframe 
    pred_df = pd.DataFrame(pred_info_ts, columns = ['ts','dect_xyxy_1', 'xyxy_2', 'xyxy_3', 'xyxy_4', 'score', 'type_obj', 'id_obj', 'dect_middle_1', 'middle_2', 'vel'])
    pred_df['dect_lonlan_1'] =long
    pred_df['lonlan_2'] = lat   # (num_pred, 1)
    pred_df['fr_num'] = frame
    pred_df['cam_id'] = 0 # (num_pred, 1)
    pred_df['video_id'] = '/root/data/videos/Interurban_cams/0/C31S 15_10_2021 12_00_00 (UTC+02_00).avi'
    
    path_out = '/root/data/bsc_json'
    
    # name_json = f'{pred_info[:, 0][0].astype(int):05d}.json'
    name_json = f'{frame:05d}.json'

    ## create folder if it doesnt exist
    if not os.path.exists(path_out):
        os.makedirs(path_out)

    ## Write json
    path_all = os.path.join(path_out, name_json)
    pred_df.to_json(path_all, orient='values') 



@constraint(AppSoftware="xavier")
@task(returns=1, trackers_list=COLLECTION_IN, count=IN, kb=IN)
def persist_info_accumulated(trackers_list, count, kb):
    from CityNS.classes import EventsSnapshot
    snapshot_alias = "events_" + str(count)
    snapshot = EventsSnapshot(snapshot_alias, print_federated_events=True, trigger_modena_tp=False)
    snapshot.make_persistent()
    for trackers in trackers_list:
        snapshot.add_events_from_trackers(trackers, kb)  # create events inside dataclay
    return snapshot


@constraint(AppSoftware="xavier")
@task(returns=1, trackers=IN, count=IN, kb=IN, with_pollution=IN)
def persist_info(trackers, count, kb, with_pollution):
    classes = ["person", "car", "truck", "bus", "motor", "bike", "rider", "traffic light", "traffic sign", "train",
               "class11", "class12", "class13", "class14", "class15", "class16", "class17", "class18","class19",
               "class20", "class21", "class22", "class23", "class24", "class25", "class26", "class27", "class28",
               "class29", "class30", "class31"]
    from CityNS.classes import EventsSnapshot
    snapshot_alias = "events_" + str(count)
    snapshot = EventsSnapshot(snapshot_alias, print_federated_events=True, trigger_modena_tp=False)
    snapshot.make_persistent()
    snapshot.add_events_from_trackers(trackers, kb)  # create events inside dataclay
    # if with_pollution:
    #     if not os.path.exists(pollution_file_name):
    #         with open(pollution_file_name, "w") as f:
    #             f.write("VehID, LinkID, Time, Vehicle_type, Av_link_speed\n")
    #     for index, ev in enumerate(trackers[1]):
    #         if classes[ev[2]] in ["car", "bus"]:
    #             obj_type = (classes[ev[2]]).title()
    #         elif classes[ev[2]] in ["class20", "class30", "class31"]:
    #             obj_type = "car"
    #         elif classes[ev[2]] == "truck":
    #             obj_type = "HDV"
    #         else:
    #             continue
    #         with open(pollution_file_name, "a") as f:
    #             f.write(f"{ev[0]}_{ev[1]}, {ev[0]}, {trackers[0]}, {obj_type}, {ev[3]}\n")  # TODO: average link speed
    return snapshot


@constraint(AppSoftware="xavier")
@task(snapshot=IN, backend_to_federate=IN)
def federate_info(snapshot, backend_to_federate):
    snapshot.federate_to_backend(backend_to_federate)


@task(snapshots=COLLECTION_IN, backend_to_federate=IN)
def federate_info_accumulated(snapshots, backend_to_federate):
    for snapshot in snapshots:
        snapshot.federate_to_backend(backend_to_federate)


@task(kb=IN, foo=INOUT)
def remove_objects_from_dataclay(kb, foo):
    kb.remove_old_snapshots_and_objects(int(datetime.now().timestamp() * 1000), True)
    return foo


# @constraint(AppSoftware="phemlight") # to be executed in Cloud. Remove it otherwise
@constraint(AppSoftware="xavier")
@task(foo=INOUT)
def analyze_pollution(foo):
    a = 'oquesea'
    b = pollution_file_name
    c = 'stream.csv'
    os.system(
        f"scp {pollution_file_name} esabate@192.168.7.32:/m/home/esabate/pollutionMap/phemlight-r/in/ && rm {pollution_file_name}")
    os.system(f"ssh esabate@192.168.7.32 nohup bash dockerScripts/phemlightCommand.sh  {a} {b} {c} &>/dev/null & ")
    return foo


# @task() # for my scheduler
@task(is_replicated=True)
def init_task():
    import uuid
    from CityNS.classes import DKB, Event, Object, EventsSnapshot
    kb = DKB()
    kb.make_persistent("FAKE_" + str(uuid.uuid4()))
    # kb.get_objects_from_dkb()
    snap = EventsSnapshot("FAKE_SNAP_" + str(uuid.uuid4()))
    snap.make_persistent("FAKE_SNAP_" + str(uuid.uuid4()))
    snap.snap_alias
    event = Event()
    event.make_persistent("FAKE_EVENT_" + str(uuid.uuid4()))
    obj = Object("FAKE_OBJ_" + str(uuid.uuid4()), "FAKE")
    obj.make_persistent("FAKE_OBJ_" + str(uuid.uuid4()))
    obj.get_events_history(20)


@constraint(AppSoftware="nvidia")
@task(returns=3, trackers_list=IN, tracker_indexes=IN, cur_index=IN)
def boxes_and_track(socket_ip, trackers_list, tracker_indexes, cur_index):
    _, _, list_boxes, _ = receive_boxes(socket_ip, 0)
    return execute_tracking(list_boxes, trackers_list, tracker_indexes, cur_index)


def execute_trackers(socket_ips, with_dataclay, kb):
    import uuid
    import time
    import sys
    import os
    #from dataclay.api import register_dataclay, get_external_backend_id_by_name

    trackers_list = [[]] * len(socket_ips)
    cur_index = [0] * len(socket_ips)
    info_for_deduplicator = [0] * len(socket_ips)
    snapshots = list()  # accumulate snapshots
    cam_ids = [0] * len(socket_ips)
    timestamps = [0] * len(socket_ips)
    deduplicated_trackers_list = []  # TODO: accumulate trackers
    box_coords = [0] * len(socket_ips)
    frames = [0] * len(socket_ips)
    polys = [0] *  len(socket_ips)

    # Get camera-edge id existing in roi files names
    allCameraRoiPaths = [f for f in listdir(roi_file_path) if isfile(join(roi_file_path, f))]
    roiFileNames = [s for s in allCameraRoiPaths if re.findall("\-(.*?)\-.*.csv",s)]
    print(f' ------------  {listdir(roi_file_path)}')
    print(f' ------------  {roiFileNames}'  )
    polys = {}
    # Get gdf roi polygons for each camera, and append with key to same dictionay.
    # This cannot be append to list with arbitrary order, could not be same order as receive boxes
    for i, roiFileName in enumerate(roiFileNames):
        cameraEdgeId = re.findall("\-(.*?)\-.*.csv", roiFileName)[0]
        gdfPolys = getRoi(roi_file_path + roiFileName)  

        polys.update({cameraEdgeId : {'vehPolys': gdfPolys[gdfPolys['class'].isin(["queue", "road", "railcross", "afterStop"])].reset_index(drop=True),
                                    'pedPolys': gdfPolys[gdfPolys['class'].isin(["road", "pedCross", "railcross", "pedTramCross", "tramway"])].reset_index(drop=True)}
        })

    # Initialize state of trafficlights and NGAP tramway

    #federation_ip, federation_port = "192.168.7.32", 11034  # TODO: change port accordingly
    #dataclay_to_federate = register_dataclay(federation_ip, federation_port)
    #external_backend_id = get_external_backend_id_by_name("DS1", dataclay_to_federate)

    i = 0
    reception_dummies = [0] * len(socket_ips)
    start_time = time.time()
    initTime = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    foo_dedu = foo = None
    while i < NUM_ITERS:
        print(i)

        # readScenarioState: trafficLights, tram NGAP
        areaState = getBatoniStatus(kb)
        # print(areaState)

        for index, socket_ip in enumerate(socket_ips):
            cam_ids[index], timestamps[index], list_boxes, reception_dummies[index], box_coords[index], init_point, frames[index] = \
                                receive_boxes(socket_ip, reception_dummies[index])
            trackers_list[index], cur_index[index], info_for_deduplicator[index] = execute_tracking(list_boxes,
                                                                                                    trackers_list[index],
                                                                                                    cur_index[index],
                                                                                                     init_point)

            # areaState = getResistenzaStatus2(frames[index])
        # info_deduplicated, foo_dedu = deduplicate(info_for_deduplicator, cam_ids, foo_dedu, frames)
            alertsList,alertInfo = semantic_analysis(cam_ids[index], timestamps[index], info_for_deduplicator[index] , polys, kb, areaState)
            writef(cam_ids[index], timestamps[index], frames[index], info_for_deduplicator[index], alertsList,initTime)
            writef_state(cam_ids[index],frames[index], areaState,initTime)
            writef_alerts(cam_ids[index],frames[index], alertInfo, initTime)
        # writef_deduplicated(info_deduplicated, i)  # or frames appended inside info_for_dedu in tracking
        """# TODO: accumulate trackers
        if i != 0 and (i+1) % N == 0:
            snapshot = persist_info_accumulated(deduplicated_trackers_list, i, kb)
            deduplicated_trackers_list.clear() 
        """
        # frames[0] not correct when more than one camera. It should be passed in info_for_deduplicator and returned in deduplicated_trackers
        #snapshot = persist_info(deduplicated_trackers, i, kb, with_pollution)
        """
        snapshots.append(snapshot)
        if i != 0 and (i+1) % SNAP_PER_FEDERATION == 0:
            federate_info_accumulated(snapshots, dataclay_to_federate)
        """
        #federate_info(snapshot, external_backend_id)
        i += 1
        # if i != 0 and i % NUM_ITERS_POLLUTION == 0 and with_pollution:
        #     print("Executing pollution")
        #     foo = analyze_pollution(foo)
        # if i != 0 and i % NUM_ITERS_FOR_CLEANING == 0:
        #     # compss_barrier()
        #     # delete objects based on timestamps
        #     foo = remove_objects_from_dataclay(kb, foo)
    print('last barrier')
    compss_barrier()
    end_time = time.time()
    print("Exec Inner Time: " + str(end_time - start_time))
    print("Exec Inner Time per Iteration: " + str((end_time - start_time) / NUM_ITERS))

def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def main():
    import argparse	
    import sys
    import time
    import zmq
		
    # Parse arguments to accept variable number of "IPs:Ports"
    parser = argparse.ArgumentParser()
    parser.add_argument("tkdnn_ips", nargs='+')
    parser.add_argument("--mqtt_wait", nargs='?', const=True, type=str2bool, default=False)  # True as default
    parser.add_argument("--with_dataclay", nargs='?', const=True, type=str2bool, default=False)  # True as default
    args = parser.parse_args()
    
    # if (args.with_dataclay):
    #     # Initialize dataclay
    #     init()
    #     # Load dataclay DKB class
    #     from CityNS.classes import DKB

        # initialize all computing units in all workers
        # num_cus = 8
        # for i in range(num_cus):
        #     init_task()
    compss_barrier()
    print(f"Init task completed {datetime.now()}")
    #input("Press enter to continue...")

    # if (args.with_dataclay):
    #     #Dataclay KB generation
    #     try:
    #         print('kb initiated right')
    #         kb = DKB.get_by_alias("DKB")
    #     except DataClayException:
    #         kb = DKB()
    #         kb.make_persistent("DKB")
    # else:
    kb = None

    ### ACK TO START WORKFLOW AT tkDNN ###
    for socket_ip in args.tkdnn_ips:
        if ":" not in socket_ip:
            socket_ip += ":5559"
        context = zmq.Context()
        sink = context.socket(zmq.REQ)
        sink.connect(f"tcp://{socket_ip}")
        sink.send_string("")
        sink.close()
        context.term()

    execute_trackers(args.tkdnn_ips, args.with_dataclay, kb)




    print("Exiting Application...")
    #finish()


if __name__ == "__main__":
    main()

